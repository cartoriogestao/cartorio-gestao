"""
Tabelionato de Notas — rotas do balcao.

O QUE ESTE MODULO ATENDE
    O que a serventia faz o dia inteiro: reconhecer firma e autenticar copia.
    No acervo sao 13.209 reconhecimentos e 3.539 autenticacoes contra 258 atos
    de livro — a tela tem de ser rapida nessas duas, e completa nas outras.

O CAMINHO DO BALCAO
    1. procura o cartao de autografo pelo nome ou pelo CPF
    2. confere a assinatura na tela, ao lado da que a pessoa acabou de fazer
    3. reconhece, e o sistema calcula o emolumento pela tabela do TJMA

    Nao havendo cartao, abre um ali mesmo — e o proximo atendimento cai no
    caso 1. E a diferenca entre um cadastro que cresce e um que se repete.

REGISTRADO A PARTIR DE create_app()
    Recebe os decoradores e utilitarios que ja existem, no mesmo padrao do RI
    e do caixa, para nao duplicar autenticacao nem auditoria.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

from flask import Response, abort, flash, redirect, render_template, request, url_for
import fraude as FR

import emolumentos as EMOL
import notas_anotacoes as NA
import notas_censec as NC
import censec_api as CAPI
import centrais_cred as CRED
import notas_inutilizacao as NI
import impressao_pdf as IPDF
import notas_livro as NL
import notas_familias as NF
import notas_modelos as NMOD
import notas_naturezas as NNAT
import ri_imagens as RIMG
import notas_partes as NP
import cadastro_biometria as CB
import ato_selado as AS
import etiqueta as ETQ
import notas_selo as NSELO
# AS TABELAS DA RECEITA MORAM NUM LUGAR SÓ. A DOI e a CTP
# usam as mesmas, e duplicá-las aqui as faria divergir no
# primeiro código que a Receita mudasse.
import modelos_da_casa as MODELOS
import notas_doi as NDOI
import ri_ctp as CTP
import caixa_depositos as DEP
import caixa_schema as CXC
import notas_teor as NT
import notas_teor_arquivo as TA
from storage import save_upload
from ri_modelos_atos import (campos_do_modelo, pendencias as pendencias_modelo,
                             preencher as preencher_modelo)
from ri_odt import (ESTILO_PAGINA_1, bloco_selo_odf, carimbo_do_selo_odf,
                    carimbo_da_certidao_odf, carimbo_compacto_odf, gerar_odt,
                    html_para_odf)
from caixa_schema import reais
import selo_no_papel as SNPAPEL
from notas_schema import (ATO_PEDE_ANOTACAO, CENTRAIS, CENTRAIS_COM_REMESSA,
                          ESPECIES_RECONHECIMENTO, ORIGENS_SINAL, SERVICOS,
                          SITUACOES_ATO, SITUACOES_REMESSA, TIPOS_ANOTACAO,
                          TIPOS_ATO,
                          TIPOS_AUTENTICACAO, TIPOS_LIVRO,
                          normalizar_nome_sinal, servico_do_reconhecimento,
                          texto_autenticacao, texto_da_etiqueta,
                          texto_reconhecimento, texto_reconhecimento_sinal)
from serventia import dados as dados_serventia
import modelos_motor_etiqueta as MOTOR_ETQ

POR_PAGINA = 40

# Onde estao as imagens de assinatura do E-Oficio. O banco guarda o caminho
# original em UNC (\\servidor\C11\Firmas\); quando a maquina que abre a tela
# nao enxerga esse compartilhamento, vale a pasta local equivalente.
#
# A PRIMEIRA DA LISTA E CALCULADA, E NAO ESCRITA AQUI: e
# `<archive_root>\eoficio\Firmas`, para onde o COPIAR_ARQUIVOS_EOFICIO trouxe
# as 3.644 assinaturas. Ver `pastas_firmas()`.
PASTAS_FIRMAS_PADRAO = (
    r"C:\ARPNET\C11\Firmas",
    r"\\servidor\C11\Firmas",
)


def _e_arquivo(p: Path) -> bool:
    """`is_file()` que nao derruba a tela quando o caminho e de rede."""
    try:
        return p.is_file()
    except OSError:
        return False


def _e_pasta(p: Path) -> bool:
    """`is_dir()` que nao derruba a tela quando o caminho e de rede.

    `Path.is_dir()` engole alguns erros do Windows e deixa outros passarem —
    `WinError 64 - o nome da rede nao esta mais disponivel` passa, e foi assim
    que uma pasta morta derrubou a copia inteira do acervo. Aqui o estrago
    seria pior: com o E-Oficio desligado, um `\\\\servidor\\...` gravado no banco
    transformaria a tela de assinaturas em erro 500, e nao em tela vazia.
    """
    try:
        return p.is_dir()
    except OSError:
        return False


# O traslado que fica com a parte.
#
# AQUI NAO SE MASCARA, E E DE PROPOSITO.
#     O recibo, o orcamento e o protocolo de recepcao sao papeis administrativos:
#     saem mascarados porque o CPF inteiro neles nao serve a nada. O traslado e
#     outra coisa — e a copia fiel de um ato publico, e a qualificacao completa
#     das partes E O ATO, exigida pelo art. 215, § 1º, do Codigo Civil. Mascarar
#     ali produziria um traslado que nao confere com o livro e que o banco ou o
#     cartorio de destino recusaria, alem de ser copia infiel de ato notarial.
#
#     A base legal para o dado sair inteiro e o art. 7º, II, da Lei 13.709/2018:
#     tratamento para cumprimento de obrigacao legal pelo controlador.
# **A PARTIR DA SEGUNDA PÁGINA** — pedido do oficial em 07/09/2026: a
# primeira página já traz Livro/Folha/Termo escrito no próprio corpo, entre
# o endereço da serventia e o rótulo do ato (ver `MODELO_TRASLADO`); repeti-
# lo também no cabeçalho de página duplicava a informação bem no topo dela.
# Da segunda página em diante não há mais aquele bloco no corpo, e por isso
# o cabeçalho de página passa a valer — mecanismo nativo do ODF, o mesmo da
# ficha do RI, ligado só a partir daqui por `gerar_odt(...,
# cabecalho_a_partir_da_pagina_2=True)`.
#
# **A FOLHA MOSTRA A PÁGINA ESPECÍFICA, E NÃO A JANELA** — «não a janela que
# a escritura está usando», ordem do oficial no mesmo dia. `#FOLHA_PAGINA#`
# vira campo de número de página em `gerar_odt` (o mesmo mecanismo do
# `#FICHA#` da ficha do RI), ajustado para começar no número gravado em
# `a.folha`. **É a página do PDF, e não a face do livro** — o sistema não
# sabe, ao montar o `.odt`, quantas páginas o LibreOffice vai desenhar; isso
# só se decide na conversão.
MODELO_TRASLADO_CABECALHO = """<table border="0" cols="5.3cm,5.3cm,5.4cm">
<tr><td><b>LIVRO {{ a.livro or '—' }}</b></td><td><b>FOLHA #FOLHA_PAGINA#</b></td><td><b>{% if a.termo %}TERMO {{ a.termo }}{% elif a.numero_ordem %}ORDEM {{ a.numero_ordem }}{% endif %}</b></td></tr>
</table>
"""

MODELO_TRASLADO = """@@BRASAO@@
<p align="center"><b>{{ sv.unit_name }}</b></p>
<p align="center">{{ sv.serventia_titulo }}: {{ sv.serventia_titular }}</p>
<p align="center">CNPJ {{ sv.serventia_cnpj }} — CNS {{ sv.ri_cns }} — Telefone {{ sv.serventia_telefone }}</p>
<p align="center">{{ sv.endereco_completo }}</p>
<table border="0" cols="5.3cm,5.3cm,5.4cm">
<tr><td><b>LIVRO {{ a.livro or '—' }}</b></td><td><b>FOLHA {{ a.folha or '—' }}{% if a.folha_final and a.folha_final != a.folha %} A {{ a.folha_final }}{% endif %}</b></td><td><b>{% if a.termo %}TERMO {{ a.termo }}{% elif a.numero_ordem %}ORDEM {{ a.numero_ordem }}{% endif %}</b></td></tr>
</table>
<p align="center"><b>{{ titulo_do_instrumento|upper }}</b></p>
<p></p>
@@TEOR@@
<p></p>
@@SELO@@
{% if anotacoes %}
<p><b>ANOTAÇÕES À MARGEM</b></p>
{% for n in anotacoes %}<p>{{ loop.index }}. {{ n.texto }}{% if n.selo %} (selo {{ n.selo }}){% endif %}</p>
{% endfor %}
{% endif %}
<p><small>Traslado extraído nesta data, conferido e achado conforme com o ato lavrado no
livro próprio desta Serventia{% if anotacoes %}, com as anotações constantes da margem
transcritas acima{% endif %}.</small></p>
<p>{{ sv.cidade_uf }}, {{ data_extenso }}.</p>
@@ASSINATURAS@@
"""

# O termo que vai para o LIVRO (instrumento), distinto do traslado da parte.
#
# Pedido 18/09/2026: «não tem opção de baixar o termo da escritura que vai no
# livro». O traslado (acima) é a via que SAI da casa — carimbo completo com QR.
# Este é o que fica no livro de papel: mesmo cabeçalho do traslado (brasão e serventia), mesmo teor e mesmas
# assinaturas dos comparecentes, e carimbo COMPACTO do selo (sem
# QR e sem link), na mesma regra do livro do RI (`carimbo_compacto_odf`, ordem
# do oficial em 16/09/2026). Sem a frase «Traslado extraído…» e sem as
# anotações à margem (estas se escrevem à margem do livro, depois).
MODELO_TERMO_LIVRO = """@@BRASAO@@
<p align="center"><b>{{ sv.unit_name }}</b></p>
<p align="center">{{ sv.serventia_titulo }}: {{ sv.serventia_titular }}</p>
<p align="center">CNPJ {{ sv.serventia_cnpj }} — CNS {{ sv.ri_cns }} — Telefone {{ sv.serventia_telefone }}</p>
<p align="center">{{ sv.endereco_completo }}</p>
<table border="0" cols="5.3cm,5.3cm,5.4cm">
<tr><td><b>LIVRO {{ a.livro or '—' }}</b></td><td><b>FOLHA {{ a.folha or '—' }}{% if a.folha_final and a.folha_final != a.folha %} A {{ a.folha_final }}{% endif %}</b></td><td><b>{% if a.termo %}TERMO {{ a.termo }}{% elif a.numero_ordem %}ORDEM {{ a.numero_ordem }}{% endif %}</b></td></tr>
</table>
<p align="center"><b>{{ titulo_do_instrumento|upper }}</b></p>
<p></p>
@@TEOR@@
<p></p>
@@SELO@@
<p></p>
<p></p>
<p></p>
@@ASSINATURAS@@
"""


def titulo_do_instrumento(ato: dict, *, nome_modelo: str | None = None) -> str:
    """Nome completo do instrumento no traslado/termo — uma linha só, em negrito.

    Não repetir «ESCRITURA PÚBLICA» sozinha e a natureza em outra linha: o
    cabeçalho leva o título inteiro (nome do modelo ou natureza composta).
    """
    tipo = (ato.get("tipo") or "").strip().upper()
    if tipo == "ESCRITURA":
        nome = (nome_modelo or "").strip()
        if nome:
            return nome
        nat = (ato.get("natureza") or "").strip()
        if nat:
            return f"Escritura pública de {nat.lower()}"
    if tipo in ("ATA", "ATA_USUCAPIAO"):
        nome = (nome_modelo or "").strip()
        if nome:
            return nome
    return TIPOS_ATO.get(ato.get("tipo") or "", ato.get("tipo") or "Ato")


def _titulos_para_limpar_do_teor(ato: dict, *, nome_modelo: str | None = None) -> list[str]:
    """Títulos que podem aparecer no cabeçalho e repetir no início do teor."""
    candidatos = [
        titulo_do_instrumento(ato, nome_modelo=nome_modelo),
        (nome_modelo or "").strip(),
        (ato.get("natureza") or "").strip(),
    ]
    vistos: set[str] = set()
    saida: list[str] = []
    for raw in candidatos:
        if not raw:
            continue
        chave = NT._norm_titulo(raw)
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(raw)
    return sorted(saida, key=len, reverse=True)


MODELO_CARTAO_FICHA = """\
<p align="center"><b>CARTÃO DE AUTÓGRAFO</b> — Ficha nº {{ numero }}</p>
<table border="1" cols="4.6cm,11.4cm">
<tr><td><b>Nome</b></td><td>{{ nome or "&#160;" }}</td></tr>
<tr><td><b>CPF / CNPJ</b></td><td>{{ documento or "&#160;" }}</td></tr>
<tr><td><b>Identidade</b></td><td>{{ identidade or "&#160;" }}</td></tr>
<tr><td><b>Nascimento</b></td><td>{{ nascimento or "&#160;" }}</td></tr>
<tr><td><b>Nacionalidade</b></td><td>{{ nacionalidade or "&#160;" }}</td></tr>
<tr><td><b>Naturalidade</b></td><td>{{ naturalidade or "&#160;" }}</td></tr>
<tr><td><b>Estado civil</b></td><td>{{ estado_civil or "&#160;" }}</td></tr>
<tr><td><b>Profissão</b></td><td>{{ profissao or "&#160;" }}</td></tr>
<tr><td><b>Filiação</b></td><td>{{ filiacao or "&#160;" }}</td></tr>
<tr><td><b>Endereço</b></td><td>{{ endereco or "&#160;" }}</td></tr>
<tr><td><b>Bairro / cidade</b></td><td>{{ bairro_cidade or "&#160;" }}</td></tr>
<tr><td><b>CEP</b></td><td>{{ cep or "&#160;" }}</td></tr>
<tr><td><b>Telefone</b></td><td>{{ telefone or "&#160;" }}</td></tr>
{% if conjuge %}<tr><td><b>Cônjuge</b></td><td>{{ conjuge }}</td></tr>{% endif %}
{% if como_assina %}<tr><td><b>Como assina</b></td><td>{{ como_assina }}</td></tr>{% endif %}
</table>
{% if somente_autenticidade %}<p><b>ESTE CARTÃO SÓ ADMITE RECONHECIMENTO POR AUTENTICIDADE.</b></p>{% endif %}
{% if bloqueado %}<p><b>CARTÃO BLOQUEADO.</b> {{ motivo_bloqueio }}</p>{% endif %}
@@SELO@@
<p><b>Autógrafos</b> — assino na presença do escrevente as formas com que firmo nesta serventia.</p>
<p><b>Assinatura por extenso</b> <span>(como o nome é assinado por inteiro)</span></p>
{{ espaco }}{{ linha }}
<p><b>Assinatura abreviada</b> <span>(a forma curta, se houver)</span></p>
{{ espaco }}{{ linha }}
<p><b>Rubrica</b> <span>(para folhas e vias)</span></p>
{{ espaco }}{{ linha }}
<table border="1" cols="8cm,8cm">
<tr><td><b>Fotografia</b></td><td><b>Impressão digital</b> (polegar direito)</td></tr>
{{ caixa_foto_digital_celulas }}
</table>
<p>{{ cidade_uf }}, {{ data_extenso }}.</p>
<p align="center">________________________________________________________________</p>
<p align="center">{{ nome }}</p>
<p align="center">o titular do cartão</p>
"""




def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    """Pendura as rotas do tabelionato no app ja construido."""

    def q(sql, params=()):
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            return list(con.execute(sql, params))

    def q1(sql, params=()):
        linhas = q(sql, params)
        return linhas[0] if linhas else None

    # Quem praticou o ato e em que funcao — implementacao unica, em `app.py`.
    #
    # ERA UMA COPIA LOCAL, E ESTAVA ERRADA.
    #     Lia `getattr(request, "usuario_nome", None)`, atributo que nada no
    #     sistema jamais definiu. Devolvia None em toda requisicao e caia na
    #     substituta do registro de imoveis: TODO reconhecimento de firma,
    #     autenticacao de copia e ato de livro saia com o nome dela e com a
    #     funcao "Escrevente", qualquer que fosse quem estivesse logado.
    #     Cadastrar a funcao na tela Usuarios nao adiantava nada.
    #
    #     A mesma copia existia em `caixa_web` e em `ri_web`, com o mesmo
    #     defeito. Agora e uma so, e vem de fora.
    usuario_nome = app.extensions["usuario_nome"]
    usuario_funcao = app.extensions["usuario_funcao"]
    usuario_papel = app.extensions["usuario_papel"]

    # O AUDITOR ve tudo e nao pratica ato.
    #
    # `roles_required` protege a ROTA, e a rota do ato precisa abrir para o
    # AUDITOR: conferir ato lavrado e o trabalho dele. Mas as acoes de POST
    # desta tela mudam o livro — e lancar no livro GASTA FOLHA E TERMO, que
    # nao voltam. Perfil de correicao nao consome numeracao de serventia.
    def somente_leitura() -> bool:
        return usuario_papel() == "AUDITOR"

    def pasta_firmas_do_acervo() -> Path:
        """`<archive_root>\\eoficio\\Firmas` — a cópia trazida do E-Ofício.

        É onde o `COPIAR_ARQUIVOS_EOFICIO` depositou as 3.644 assinaturas, e
        é caminho LOCAL: o serviço roda como SYSTEM, que não enxerga
        compartilhamento montado na sessão do usuário. Enquanto as imagens
        moravam em `\\\\servidor\\C11\\Firmas`, o caminho estava certo no banco,
        abria para quem estava logado, e mesmo assim o servidor não achava
        nenhuma. Foi exatamente o "nenhuma assinatura localizada".
        """
        raiz = Path(db.get_setting("archive_root", "").strip()
                    or (Path(db.db_path).parent / "arquivos"))
        return raiz / "eoficio" / "Firmas"

    def pastas_firmas() -> list[Path]:
        """Onde procurar a imagem da assinatura, em ordem de preferencia.

        A cópia local vem ANTES da configurada e das UNC: ela é a única que
        continua funcionando depois que o E-Ofício for desligado.
        """
        caminhos = [pasta_firmas_do_acervo()]
        configurada = (db.get_setting("nt_pasta_firmas", "") or "").strip()
        if configurada:
            caminhos.append(Path(configurada))
        caminhos += [Path(p) for p in PASTAS_FIRMAS_PADRAO]
        vistas: set[str] = set()
        ordenadas = []
        for p in caminhos:
            chave = str(p).rstrip("\\/").lower()
            if chave not in vistas and _e_pasta(p):
                vistas.add(chave)
                ordenadas.append(p)
        return ordenadas

    def emolumento_do_servico(codigo: int, quantidade: int = 1) -> dict:
        """Quanto custa, pela tabela do tribunal. Sem ninguém digitar valor.

        Devolve dicionário vazio quando a tabela ainda não foi importada — a
        tela mostra o ato sem o preço em vez de quebrar.
        """
        if not codigo:
            return {}
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            try:
                return EMOL.calcular_item(con, servico=codigo,
                                          quantidade=quantidade) or {}
            except Exception:                                  # noqa: BLE001
                return {}

    # =================================================== cartao de autografo

    @app.route("/notas/cartoes", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_cartoes():
        """Busca e cadastro do cartão de autógrafo."""
        if request.method == "POST" and request.form.get("acao") == "novo":
            dados = {k: request.form.get(k) for k in request.form}
            nome = (dados.get("nome") or "").strip()
            if not nome:
                flash("Informe o nome.", "danger")
                return redirect(url_for("notas_cartoes"))
            # Duplicata: avisa e só cria se o operador insistir.
            if not request.form.get("confirmar_duplicata"):
                with db.connect() as con:
                    iguais = NP.possivel_duplicata(con, nome, dados.get("documento"))
                if iguais:
                    nomes = ", ".join(f"{c['nome']} (nº {c['id']})" for c in iguais[:3])
                    flash(f"Já existe cartão para {nomes}. Se ainda assim for outra "
                          f"pessoa, marque a confirmação e grave de novo.", "warning")
                    return redirect(url_for("notas_cartoes", busca=nome))
            with db.transaction() as con:
                try:
                    novo = NP.criar_cartao(con, dados, db.now(), usuario_nome())
                except ValueError as erro:
                    flash(str(erro), "danger")
                    return redirect(url_for("notas_cartoes"))
            # O CARTAO SELA NA ABERTURA — `/selo/notas/cartao-assinatura`,
            # 2.667 usos medidos. O E-Oficio selava o cadastro do autografo
            # como qualquer outro ato, e o item e o 13.17.1.
            selado = selar_simples(
                "nt_cartoes", novo, servico=SERVICOS["CARTAO"],
                partes=[{"nome": nome, "documento": dados.get("documento")}])
            motivo_selo = motivo_da_falha_do_selo(selado)
            if motivo_selo:
                with db.transaction() as con:
                    con.execute("DELETE FROM nt_cartoes WHERE id=?", (novo,))
                audit("NT_CARTAO_NAO_ABERTO_SELO_FALHOU", "NT_CARTAO", novo,
                      {"nome": nome, "motivo": motivo_selo})
                flash("Cartão NÃO aberto: o selo de abertura não saiu. "
                      f"Motivo: {motivo_selo}. Corrija o problema do "
                      "selo e abra de novo — o cartão fica suspenso até o selo "
                      "sair (relato #77).",
                      "danger")
                return redirect(url_for("notas_cartoes", busca=nome))
            audit("NT_CARTAO_ABERTO", "NT_CARTAO", novo, {"nome": nome})

            # A FICHA ENTRA JUNTO, se o operador a escolheu no mesmo formulário.
            #
            # Abrir o cartão e anexar a digitalização são um gesto só no
            # balcão: a pessoa está ali, a ficha acabou de ser assinada e
            # digitalizada. Separar em duas telas é o tipo de passo que se
            # esquece — e cartão de autógrafo sem autógrafo não serve para
            # reconhecer nada por semelhança.
            entraram, recusas = _enviar_fichas(novo)
            recado = f"Cartão nº {novo} aberto para {nome}.{selado}"
            if entraram:
                recado += f" {entraram} ficha(s) digitalizada(s) guardada(s)."
            if recusas:
                recado += " " + " ".join(recusas)
            flash(recado, "warning" if recusas else "success")
            return redirect(url_for("notas_cartao", cartao_id=novo))

        busca = (request.args.get("busca") or "").strip()
        achados, aviso_busca = [], None
        if busca:
            if len(busca) < 3:
                aviso_busca = "Digite pelo menos três letras ou o CPF."
            else:
                with db.connect() as con:
                    achados = NP.buscar_cartoes(con, busca, limite=POR_PAGINA)
                for c in achados:
                    c["avisos"] = NP.avisos_do_cartao(c)
        # A ASSINATURA E DO CARTAO, e por isso o numero dela fica AQUI.
        #
        #   «Assinaturas digitalizadas deveria ser campo dos cartoes de
        #   assinatura, nao faz sentido mais esse campo para dividir e
        #   complicar a localizacao e o trabalho com as firmas» — o oficial,
        #   em 27/08/2026.
        #
        #   Ele esta certo sobre o LUGAR, e a tela de assinaturas nao e um
        #   campo: e o mutirao que traz os arquivos do E-Oficio para dentro.
        #   Entao ela sai do menu e passa a ser chamada daqui, com o numero
        #   ao lado — cartao sem autografo nao serve para reconhecer por
        #   semelhanca, e esse e o numero que diz quantos ainda faltam.
        resumo = q1("""SELECT COUNT(*) total,
                       COALESCE(SUM(CASE WHEN bloqueado=1 THEN 1 ELSE 0 END),0) bloqueados,
                       COALESCE(SUM(CASE WHEN ativo=0 THEN 1 ELSE 0 END),0) inativos,
                       COALESCE(SUM(CASE WHEN NOT EXISTS (
                           SELECT 1 FROM nt_cartao_imagens i
                            WHERE i.cartao_id = nt_cartoes.id) THEN 1 ELSE 0 END),0)
                           sem_assinatura
                       FROM nt_cartoes""")
        return render_template("notas_cartoes.html", busca=busca, achados=achados,
                               aviso_busca=aviso_busca, resumo=resumo)

    # ------------------------------------------- a ficha do cartao de autografo
    #
    # «Nao oferece um cartao de firma gerado para imprimir e dar para o usuario
    # assinar» — o oficial, em 27/08/2026.
    #
    # NAO HA PRECEDENTE A IMITAR, e isso foi medido: no E-Oficio a configuracao
    # de etiqueta do cartao de autografo esta em `0`, e o termo de presenca e o
    # livro de presenca estao os dois DESLIGADOS (`tbPropRFirma`). A ficha era
    # preenchida a mao num formulario pre-impresso comprado pronto.
    #
    # Entao o desenho e decisao da casa, e o criterio foi: **a ficha existe para
    # ser assinada e guardada**, e tudo o que ela mostra tem de servir a quem
    # depois vai CONFERIR uma assinatura contra ela.

    # ------------------------------------------- a ficha do cartao de autografo
    #
    # «Nao oferece um cartao de firma gerado para imprimir e dar para o usuario
    # assinar» — o oficial, em 27/08/2026.
    #
    # NAO HA PRECEDENTE A IMITAR, e isso foi medido: no E-Oficio a configuracao
    # de etiqueta do cartao de autografo esta em `0`, e o termo de presenca e o
    # livro de presenca estao os dois DESLIGADOS (`tbPropRFirma`). A ficha era
    # preenchida a mao num formulario pre-impresso comprado pronto.
    #
    # Entao o desenho e decisao da casa, e o criterio foi: **a ficha existe para
    # ser assinada e guardada**, e tudo o que ela mostra tem de servir a quem
    # depois vai CONFERIR uma assinatura contra ela.
    #
    # HIBRIDO (07/09/2026): o TEXTO editavel mora em `MODELO_CARTAO_FICHA`
    # (catalogo NOTAS_CARTAO_FICHA). O cabecalho da serventia fica em codigo
    # (decisao oficial: cabecalho fora dos elementos). Qualificacao (valores),
    # espaco/linha das tres assinaturas, foto/digital e selo/QR continuam
    # gerados aqui — o modelo nao recebe o HTML final montado com dados do cartao.

    # AS DUAS FUNCOES QUE MORAVAM AQUI FORAM APAGADAS em 31/08/2026, e o
    # motivo fica escrito porque a ausencia delas e que e a decisao.
    #
    #   `_quem_responde_pela_serventia` e `_titulo_de_quem_responde` nasceram
    #   para por a assinatura do delegatario no cartao de autografo — e isso
    #   era o AVESSO do relato #27. O oficial: «o oficial nao assina a ficha
    #   de assinatura, so o cliente».
    #
    #   Elas ficariam sem uso nenhum, e neste projeto peca pronta sem chamador
    #   e arma que alguem religa sem saber por que existia: ja aconteceu cinco
    #   vezes. A regra de quem responde pela serventia continua existindo onde
    #   ela e usada de verdade — na certidao do Registro de Imoveis.

    @app.route("/notas/cartoes/<int:cartao_id>/ficha")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_cartao_ficha(cartao_id):
        """A ficha do cartao, para imprimir e o cliente assinar. SO LE.

        POR QUE `.odt` E NAO UMA TELA PARA IMPRIMIR
            E papel que fica guardado e volta a ser consultado por anos. A
            forma e a dos outros documentos desta casa — termo de livro,
            certidao, comprovante de prenotacao —, e por isso abre no mesmo
            programa, imprime com a mesma margem e se arquiva do mesmo jeito.

        TRES ASSINATURAS, E NAO UMA. Quem confere por semelhanca precisa da
        forma por extenso, da abreviada e da rubrica: e com a rubrica que se
        assina folha de escritura, e ela nao se parece com a assinatura cheia.

        A FOTO E A DIGITAL TEM ESPACO MARCADO, mesmo quando ainda nao existem
        no sistema — a ficha e assinada NO BALCAO, com a pessoa presente, e e
        ali que a digital se colhe. Espaco em branco num papel que a pessoa
        esta assinando e o convite para preenche-lo; a mesma ficha sem os
        quadros so adiaria a coleta para um dia que nao chega.

        O DOCUMENTO SAI INTEIRO, e nao mascarado. Esta ficha NAO deixa a
        serventia: ela e arquivada aqui, e e contra ela que a firma se confere.
        Mascarar o CPF do proprio cartao de autografo tornaria a conferencia
        impossivel — e a regra da mascara existe para papel que SAI.
        """
        c = q1("SELECT * FROM nt_cartoes WHERE id=?", (cartao_id,))
        if not c:
            abort(404)
        sv = dados_serventia(db.get_settings)

        endereco = ", ".join(x for x in (
            (c["endereco"] or "").strip(),
            (c["endereco_numero"] or "").strip(),
            (c["endereco_complemento"] or "").strip()) if x)
        bairro_cidade = " — ".join(x for x in (
            " / ".join(y for y in ((c["bairro"] or "").strip(),
                                   (c["cidade"] or "").strip()) if y),
            (c["uf"] or "").strip()) if x)
        identidade = " ".join(x for x in ((c["rg"] or "").strip(),
                                          (c["rg_orgao"] or "").strip(),
                                          (c["rg_uf"] or "").strip()) if x)
        filiacao = " e ".join(
            x for x in ((c["pai"] or "").strip(),
                        (c["mae"] or "").strip()) if x)
        telefone = " / ".join(
            x for x in ((c["telefone"] or "").strip(),
                        (c["celular"] or "").strip()) if x)

        # Linha na largura util da lauda (16cm = tabela de qualificacao).
        # Espaco vertical *2: da pra assinar sem empurrar o nome p/ verso.
        # nbsp: <p></p> some colapsa no ODT e a 1a assinatura ficava sem espaco.
        # Linha so em <p>, sem tabela — a celula virava retangulo em volta do underline.
        # Cinco linhas deixam a pessoa desenvolver a assinatura natural, que
        # é o padrão usado depois na comparação por semelhança (relato #27).
        espaco = "<p> </p>" * 5
        linha = (
            "<p>________________________________________________________________</p>")

        selo_ab = (c["selo_abertura"] or "").strip()
        texto_selo = _texto_do_selo(selo_ab) if selo_ab else ""
        papel = (SNPAPEL.do_papel({"numero": selo_ab, "texto": texto_selo})
                 if selo_ab else {})
        if texto_selo:
            selo_para_quadro = texto_selo
        elif selo_ab:
            pedacos = [selo_ab]
            if papel.get("detalhe"):
                pedacos.append(papel["detalhe"])
            if papel.get("valores"):
                pedacos.append(papel["valores"])
            selo_para_quadro = " — ".join(pedacos)
        else:
            selo_para_quadro = ""

        imagens: dict = {}
        if selo_ab:
            png = None
            try:
                import io as _io
                import segno as _segno
                # O QR LEVA O ENDERECO DA CONSULTA DAQUELE SELO — 24/09/2026.
                # O token do aparelho saiu daqui: ele nao e link, e o portal
                # procura pelo numero. Ver `notas_selo`.
                try:
                    modelo_qr = modelo_do_qr()
                except Exception:
                    modelo_qr = NSELO.MODELO_PADRAO
                qr_texto = NSELO.conteudo(modelo_qr, selo_ab)
                if qr_texto:
                    qr = _segno.make(qr_texto, error="m")
                    buf = _io.BytesIO()
                    qr.save(buf, kind="png", scale=6, border=0)
                    png = buf.getvalue()
            except Exception:
                png = None
            img_nome = None
            if png:
                img_nome = "qr_abertura.png"
                imagens[img_nome] = (png, "image/png")
            valores = papel.get("valores") or ""
            if valores and texto_selo and "Total R$" in texto_selo:
                valores = ""
            # O CARIMBO E O MESMO DAS OUTRAS ATRIBUICOES — ordem do oficial
            # em 15/09/2026: «notas, certidao de inteiro teor do rcpn e livro
            # 3 tbm devem usar a mesma etiqueta nova aprovada aqui».
            #
            #   O rotulo agora vem DENTRO do carimbo, entao o paragrafo
            #   «Selo de abertura» que vinha em cima saiu: dois rotulos para o
            #   mesmo quadro e ruido num papel assinado.
            #
            #   E `valores` deixou de ser passado: o carimbo le a linha de
            #   valores da propria etiqueta, pela mesma `selo_no_papel.
            #   linha_de_valores` que esta tela ja consultava — passar os dois
            #   imprimia a conta duas vezes.
            selo_frag = carimbo_do_selo_odf(
                selo_para_quadro, img_nome, rotulo="SELO DE ABERTURA")
        else:
            selo_frag = html_para_odf(
                '<p><b>SEM SELO DE ABERTURA.</b> Anote o selo no cadastro '
                'antes de arquivar esta ficha.</p>',
                compacto=True)

        from jinja2.sandbox import SandboxedEnvironment
        env = SandboxedEnvironment(autoescape=False)
        with db.connect() as _c:
            _modelo = MODELOS.corpo_de(_c, "NOTAS_CARTAO_FICHA")
        html_corpo = env.from_string(_modelo).render(
            numero=c["numero"] or c["id"],
            nome=(c["nome"] or "").strip(),
            documento=(c["documento"] or "").strip(),
            identidade=identidade,
            nascimento=(fmt_date(c["nascimento"]) if c["nascimento"] else ""),
            nacionalidade=(c["nacionalidade"] or "").strip(),
            naturalidade=(c["naturalidade"] or "").strip(),
            estado_civil=(c["estado_civil"] or "").strip(),
            profissao=(c["profissao"] or "").strip(),
            filiacao=filiacao,
            endereco=endereco,
            bairro_cidade=bairro_cidade,
            cep=(c["cep"] or "").strip(),
            telefone=telefone,
            conjuge=(c["conjuge"] or "").strip(),
            como_assina=(c["como_assina"] or "").strip(),
            somente_autenticidade=bool(c["somente_autenticidade"]),
            bloqueado=bool(c["bloqueado"]),
            motivo_bloqueio=(c["motivo_bloqueio"] or "").strip(),
            espaco=espaco,
            linha=linha,
            cidade_uf=sv["cidade_uf"],
            data_extenso=_hoje_extenso(),
        )

        # Cabecalho fora do modelo (decisao oficial). Corpo = texto do catalogo
        # + fragmentos de estrutura/media injetados (selo/QR).
        html_cab = (
            f'<p align="center"><b>{sv["unit_name"]}</b><br/>'
            f'{sv["serventia_titulo"]}: {sv["serventia_titular"]}<br/>'
            f'CNS {sv["ri_cns"]} — {sv["endereco_completo"]}</p>')
        corpo = html_para_odf(html_cab, compacto=True)
        corpo += html_para_odf(
            html_corpo, compacto=True,
            fragmentos={"@@SELO@@": selo_frag})
        arquivo = gerar_odt(
            corpo,
            titulo=f"Cartão de autógrafo {c['numero'] or c['id']}",
            imagens=imagens or None)

        audit("NT_CARTAO_FICHA", "NT_CARTAO", cartao_id,
              {"nome": c["nome"]})
        nome = f"cartao-autografo-{c['numero'] or c['id']}.odt"
        return Response(arquivo,
                        mimetype="application/vnd.oasis.opendocument.text",
                        headers={"Content-Disposition":
                                 f'attachment; filename="{nome}"'})

    @app.route("/notas/cartoes/<int:cartao_id>", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_cartao(cartao_id):
        c = q1("SELECT * FROM nt_cartoes WHERE id=?", (cartao_id,))
        if not c:
            abort(404)

        if request.method == "POST":
            acao = request.form.get("acao")
            if acao == "bloquear":
                motivo = (request.form.get("motivo") or "").strip()
                if not motivo:
                    flash("Diga por que está bloqueando.", "danger")
                    return redirect(url_for("notas_cartao", cartao_id=cartao_id))
                with db.transaction() as con:
                    con.execute("""UPDATE nt_cartoes SET bloqueado=1, motivo_bloqueio=?,
                                   bloqueado_em=?, bloqueado_por=? WHERE id=?""",
                                (motivo, db.now(), usuario_nome(), cartao_id))
                audit("NT_CARTAO_BLOQUEADO", "NT_CARTAO", cartao_id, {"motivo": motivo})
                flash("Cartão bloqueado.", "success")
            elif acao == "desbloquear":
                with db.transaction() as con:
                    con.execute("""UPDATE nt_cartoes SET bloqueado=0, motivo_bloqueio=NULL,
                                   bloqueado_em=NULL, bloqueado_por=NULL WHERE id=?""",
                                (cartao_id,))
                audit("NT_CARTAO_DESBLOQUEADO", "NT_CARTAO", cartao_id, {})
                flash("Cartão desbloqueado.", "success")
            elif acao == "editar":
                campos = ("nome", "documento", "rg", "rg_orgao", "rg_uf", "nascimento",
                          "nacionalidade", "naturalidade", "estado_civil", "conjuge",
                          "profissao", "pai", "mae", "endereco", "endereco_numero",
                          "bairro", "cidade", "uf", "cep", "telefone", "celular",
                          "email", "como_assina", "observacao")
                valores, sets = [], []
                for campo in campos:
                    if campo not in request.form:
                        continue
                    v = (request.form.get(campo) or "").strip() or None
                    if campo in ("documento", "cep", "telefone", "celular"):
                        v = NP.so_digitos(v) or None
                    sets.append(f"{campo}=?")
                    valores.append(v)
                if sets:
                    nome = (request.form.get("nome") or c["nome"]).strip()
                    sets += ["nome_norm=?", "atualizado_em=?", "atualizado_por=?"]
                    valores += [NP.normalizar(nome), db.now(), usuario_nome()]
                    with db.transaction() as con:
                        con.execute(f"UPDATE nt_cartoes SET {', '.join(sets)} WHERE id=?",
                                    valores + [cartao_id])
                    audit("NT_CARTAO_EDITADO", "NT_CARTAO", cartao_id, {})
                    flash("Cartão atualizado.", "success")
            return redirect(url_for("notas_cartao", cartao_id=cartao_id))

        dados = dict(c)
        imagens = [dict(r) for r in q(
            """SELECT * FROM nt_cartao_imagens WHERE cartao_id=?
               ORDER BY favorita DESC, ordem""", (cartao_id,))]
        # Marca qual imagem o servidor consegue mesmo abrir: caminho gravado
        # que nao existe mais e informacao inutil na tela.
        #
        # PERGUNTA À MESMA FUNÇÃO QUE SERVE A IMAGEM, e não a uma busca própria.
        #     Esta linha varria só as pastas do E-Ofício. Enquanto toda
        #     assinatura vinha de lá, as duas respostas coincidiam. A ficha que
        #     o operador envia pela tela mora em `notas\firmas\<cartão>`, que
        #     não está nessa lista: ela seria gravada, apareceria no banco, a
        #     rota da imagem a serviria sem problema — e a tela diria
        #     "não foi encontrada nesta máquina", que é a mentira mais cara que
        #     uma tela pode contar sobre um arquivo que está lá.
        #
        #     Duas maneiras de responder a mesma pergunta divergem no dia em
        #     que uma delas aprende algo que a outra não aprendeu.
        for i in imagens:
            i["disponivel"] = _arquivo_da_assinatura(i) is not None
        recentes = q("""SELECT r.id, r.data, r.especie, r.selo
                        FROM nt_reconhecimentos r
                        JOIN nt_reconhecimento_partes p ON p.reconhecimento_id = r.id
                        WHERE p.cartao_id=? ORDER BY r.data DESC, r.id DESC LIMIT 15""",
                     (cartao_id,))
        atos = q("""SELECT a.id, a.tipo, a.data, a.livro, a.folha, p.qualificacao
                    FROM nt_atos a JOIN nt_ato_partes p ON p.ato_id = a.id
                    WHERE p.cartao_id=? ORDER BY a.data DESC LIMIT 15""", (cartao_id,))
        total_rec = q1("""SELECT COUNT(*) n FROM nt_reconhecimento_partes
                          WHERE cartao_id=?""", (cartao_id,))["n"]
        # GET so le. Foto e digital nao se colhem nesta rota — colher e
        # POST /notas/cartoes/<id>/foto. Pasta nao se cria aqui.
        with db.connect() as con_bio:
            bio = CB.estado(con_bio, cartao_id)
        return render_template("notas_cartao.html", c=dados, imagens=imagens,
                               avisos=NP.avisos_do_cartao(dados), recentes=recentes,
                               atos=atos, total_rec=total_rec,
                               faltando=NP.campos_faltantes(dados, "ATO"),
                               bio=bio,
                               # OS NOMES DOS DEDOS SAEM DO DOMINIO, e nao da
                               # tela: quem decide quais quatro a casa colhe e'
                               # `DEDOS_DA_CASA`, e uma lista escrita aqui
                               # divergiria dela no primeiro conserto.
                               dedos={d: CB.nome_do_dedo(d)
                                      for d in CB.DEDOS_DA_CASA},
                               doc_valido=NP.documento_valido(dados.get("documento")),
                               TIPOS_ATO=TIPOS_ATO)

    # ------------------------------------------- fotografia do cadastro
    #
    # A foto mora no DISCO, na mesma pasta das assinaturas do cartao
    # (`notas\\firmas\\{id}\\foto.jpg`). O banco so guarda o caminho.
    # Colher e POST. Mostrar e GET. GET nao grava nada.

    @app.route("/notas/cartoes/<int:cartao_id>/foto")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_cartao_foto(cartao_id):
        """A fotografia do cadastro, como esta no disco. SO LE.

        Nao colhe. Colher e o POST desta mesma URL. Sem foto, 404 — e 404
        nao cria arquivo nem linha.
        """
        try:
            with db.connect() as con:
                imgs = CB.imagens_do_cadastro(con, cartao_id)
        except CB.CadastroBioError:
            abort(404)
        foto = next((i for i in imgs if i["especie"] == CB.ESPECIE_FOTO), None)
        if not foto:
            abort(404)
        caminho = Path(foto["caminho"])
        if not _e_arquivo(caminho):
            abort(404)
        return Response(caminho.read_bytes(), mimetype="image/jpeg",
                        headers={"Cache-Control": "private, no-cache"})

    @app.route("/notas/cartoes/<int:cartao_id>/foto", methods=["POST"],
               endpoint="notas_cartao_foto_colher")
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_cartao_foto_colher(cartao_id):
        """Recebe o JPEG da webcam e grava no cadastro.

        O dominio escreve o arquivo e a linha. Esta rota so liga o POST ao
        `CB.colher_foto`, com a pasta das assinaturas do cartao. Erro de
        regra vira flash em portugues e volta para o GET, que nao grava.
        """
        if not q1("SELECT id FROM nt_cartoes WHERE id=?", (cartao_id,)):
            abort(404)
        arquivo = request.files.get("foto")
        dados = arquivo.read() if arquivo else b""
        try:
            with db.transaction() as con:
                CB.colher_foto(con, cartao_id, dados, db.now(),
                               usuario_nome(), pasta_assinaturas_internas())
        except CB.CadastroBioError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("notas_cartao", cartao_id=cartao_id))
        audit("NT_CADASTRO_FOTO", "NT_CARTAO", cartao_id, {})
        flash("Fotografia colhida.", "success")
        return redirect(url_for("notas_cartao", cartao_id=cartao_id))

    # ------------------------------------------------ a digital dos dedos
    #
    # **RELATO #39 do oficial**: «colher biometria de digital de dedos». O
    # dominio existia inteiro — `cadastro_biometria.colher_digital`, com os
    # quatro dedos da casa e o teste — e **nenhuma tela o chamava**; ele
    # estava declarado em `test_funcao_sem_tela.py` como orfao conhecido.
    #
    # **A CASA COLHE QUATRO DEDOS, e nao dez** — polegar e indicador de cada
    # mao. Quem escolheu foi o dominio, e a tela nao inventa um quinto.
    #
    # **E O APARELHO NAO E' ESTE SISTEMA.** O leitor de digital entrega uma
    # imagem; o que esta rota faz e' receber a imagem e guarda-la no cadastro.
    # Dizer que o sistema «le a digital» seria prometer driver que ele nao tem.

    @app.route("/notas/cartoes/<int:cartao_id>/digital/<int:dedo>")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_cartao_digital(cartao_id, dedo):
        """A digital de um dedo, como está no disco. **SÓ LÊ.**"""
        try:
            with db.connect() as con:
                imgs = CB.imagens_do_cadastro(con, cartao_id)
        except CB.CadastroBioError:
            abort(404)
        achada = next((i for i in imgs
                       if i["especie"] == CB.ESPECIE_DIGITAL
                       and int(i.get("dedo") or 0) == int(dedo)), None)
        if not achada:
            abort(404)
        caminho = Path(achada["caminho"])
        if not _e_arquivo(caminho):
            abort(404)
        return Response(caminho.read_bytes(), mimetype="image/png",
                        headers={"Cache-Control": "private, no-cache"})

    @app.route("/notas/cartoes/<int:cartao_id>/digital", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_cartao_digital_colher(cartao_id):
        """Recebe a imagem da digital e grava no cadastro. **ESCREVE.**

        **Recolher o mesmo dedo SUBSTITUI** — quem colhe de novo é porque a
        primeira saiu ruim, e guardar as duas faria a conferência ter de
        escolher entre elas.
        """
        if not q1("SELECT id FROM nt_cartoes WHERE id=?", (cartao_id,)):
            abort(404)
        try:
            dedo = int(request.form.get("dedo") or 0)
        except ValueError:
            dedo = 0
        arquivo = request.files.get("digital")
        dados = arquivo.read() if arquivo else b""
        try:
            with db.transaction() as con:
                CB.colher_digital(con, cartao_id, dedo, dados, db.now(),
                                  usuario_nome(), pasta_assinaturas_internas())
        except CB.CadastroBioError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("notas_cartao", cartao_id=cartao_id))
        audit("NT_CADASTRO_DIGITAL", "NT_CARTAO", cartao_id, {"dedo": dedo})
        flash(f"Digital do {CB.nome_do_dedo(dedo)} colhida.", "success")
        return redirect(url_for("notas_cartao", cartao_id=cartao_id))

    # Que formato o navegador desenha sozinho dentro de um <img>, e qual
    # precisa passar pelo Pillow antes.
    #
    # PORQUE A LISTA EXISTE, E NÃO UM `if jpg else png`.
    #     Era assim: `.jpg` virava `image/jpeg` e TODO O RESTO virava
    #     `image/png`. Das 3.637 assinaturas do acervo, 3.635 são JPG — o
    #     resto é uma GIF e um PDF, e os dois saíam rotulados como PNG. O PDF
    #     nem imagem é.
    #
    #     Dois arquivos em três mil e seiscentos não parece muito até ser o
    #     cartão da pessoa que está no balcão.
    MIME_NATIVO = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".jfif": "image/jpeg",
                   ".png": "image/png", ".gif": "image/gif", ".bmp": "image/bmp",
                   ".webp": "image/webp"}

    def _assinatura_para_baixar(caminho: Path, motivo: str) -> Response:
        """O arquivo como está no disco, para download.

        COM EXTENSÃO, E POR EXPERIÊNCIA.
            É a mesma lição das fichas do Registro de Imóveis: arquivo entregue
            sem extensão o Windows não associa a visualizador nenhum, e o
            operador vê "baixou um arquivo que não abre".
        """
        nome = caminho.name
        if "." not in nome or nome.rsplit(".", 1)[1].isdigit():
            nome += ".tif"
        tipo = MIME_NATIVO.get(caminho.suffix.lower(), "application/octet-stream")
        return Response(caminho.read_bytes(), mimetype=tipo,
                        headers={"Content-Disposition": f'attachment; filename="{nome}"',
                                 "X-Assinatura-Motivo": motivo})

    def _achar_ou_404(imagem_id: int):
        img = q1("SELECT * FROM nt_cartao_imagens WHERE id=?", (imagem_id,))
        if not img:
            abort(404)
        achado = _arquivo_da_assinatura(img)
        if achado is None:
            # Antes era `abort(404)` calado, e o operador via a imagem quebrada
            # sem saber se era o cartão, a rede ou o sistema. O registro no log
            # diz qual é, e a tela de Assinaturas digitalizadas diz o resto.
            app.logger.warning(
                "Assinatura %s não localizada: nome=%r caminho gravado=%r. "
                "Rode a tela Assinaturas digitalizadas.",
                imagem_id, img["nome_arquivo"], img["caminho"])
            abort(404)
        return img, achado

    @app.route("/notas/cartoes/imagem/<int:imagem_id>")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_cartao_imagem(imagem_id):
        """Serve a assinatura digitalizada, no formato que o navegador desenha.

        A imagem vive em disco, fora do banco: no E-Ofício ela está em
        \\\\servidor\\C11\\Firmas. Procuramos nas pastas conhecidas pelo nome do
        arquivo, porque o caminho UNC gravado pode não existir nesta máquina.

        O PARÂMETRO `w` É PARA A LUPA, E EXISTE POR UM MOTIVO PRÁTICO.
            A tela pede a miniatura pequena (`?w=520`) e a lupa pede a grande.
            Sem isso, a lista de cartões traria trinta assinaturas em tamanho
            cheio para desenhar cada uma em 44 pixels de altura — e a página do
            balcão demoraria a abrir por causa de imagem que ninguém está
            olhando ainda.

            Só encolhe: pedir 2200 de uma assinatura de 900 devolve os 900.
            Ampliar no servidor não acrescenta traço nenhum; quem amplia é a
            lupa, no navegador, que faz isso de graça.
        """
        _img, achado = _achar_ou_404(imagem_id)
        sufixo = achado.suffix.lower()

        if sufixo == ".pdf":
            # PDF não é imagem, e não adianta convertê-lo: o navegador abre PDF
            # melhor do que qualquer coisa que a gente fizesse aqui. A lupa
            # detecta que o <img> não carregou e oferece o botão de abrir.
            return Response(achado.read_bytes(), mimetype="application/pdf",
                            headers={"Content-Disposition":
                                     f'inline; filename="{achado.name}"',
                                     "Cache-Control": "private, max-age=600"})

        largura = request.args.get("w", type=int)
        nativo = sufixo in MIME_NATIVO
        if nativo and not largura:
            return Response(achado.read_bytes(), mimetype=MIME_NATIVO[sufixo],
                            headers={"Cache-Control": "private, max-age=600"})

        try:
            from PIL import Image
        except ImportError:
            if nativo:
                # Sem Pillow não dá para encolher, mas dá para entregar. Uma
                # imagem grande demais é muito melhor do que nenhuma.
                return Response(achado.read_bytes(), mimetype=MIME_NATIVO[sufixo],
                                headers={"Cache-Control": "private, max-age=600"})
            app.logger.warning(
                "Pillow ausente: a assinatura %s (%s) foi entregue para download "
                "em vez de aparecer na tela. Instale com: "
                "<runtime>\\Scripts\\python.exe -m pip install Pillow",
                imagem_id, achado.name)
            return _assinatura_para_baixar(achado, "pillow-ausente")

        import io as _io
        try:
            with Image.open(achado) as im:
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                if largura and im.width > largura:
                    im = im.resize((largura, int(im.height * largura / im.width)))
                buf = _io.BytesIO()
                im.save(buf, format="PNG", optimize=True)
        except (OSError, ValueError) as erro:
            # Arquivo corrompido, ou formato que o Pillow não reconhece. Antes
            # isto viraria erro 500 e derrubaria a tela inteira por causa de
            # UMA assinatura ruim, com as outras vinte na mesma página.
            app.logger.warning("Não consegui converter a assinatura %s (%s): %s",
                               imagem_id, achado, erro)
            return _assinatura_para_baixar(achado, "conversao-falhou")
        return Response(buf.getvalue(), mimetype="image/png",
                        headers={"Cache-Control": "private, max-age=3600"})

    @app.route("/notas/cartoes/imagem/<int:imagem_id>/original")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_cartao_imagem_original(imagem_id):
        """O arquivo digitalizado como ele é, sem conversão nenhuma.

        É o botão *Baixar* da lupa. Serve para anexar a assinatura numa
        resposta a ofício, ou para conferir num programa de imagem quando a
        dúvida é sobre o próprio traço — situações em que a versão convertida
        pela tela não é o que se quer.
        """
        _img, achado = _achar_ou_404(imagem_id)
        return _assinatura_para_baixar(achado, "pedido-pelo-operador")

    # ================================================ enviar a ficha do cartão

    # O que se aceita como digitalização da ficha de firma.
    #
    # O TIFF ESTÁ AQUI PORQUE O SCANNER DE MESA GRAVA TIFF sem avisar ninguém,
    # e recusar o arquivo que o equipamento da própria serventia produz é a
    # forma mais rápida de a tela nova nascer inútil. Ele entra, e a rota da
    # imagem converte para PNG na hora de mostrar.
    EXTENSOES_DA_FICHA = {".jpg", ".jpeg", ".jfif", ".png", ".gif", ".bmp",
                          ".webp", ".tif", ".tiff", ".pdf"}
    LIMITE_DA_FICHA = 25 * 1024 * 1024          # 25 MB por arquivo

    def _pdf_para_imagem(dados: bytes) -> bytes | None:
        """A primeira página do PDF virada imagem, ou None se não der.

        POR QUE CONVERTER, E NÃO SÓ GUARDAR O PDF
            A ficha de firma vale pelo que se faz com ela: ampliar, girar,
            inverter o contraste, pôr duas lado a lado. PDF dentro de um `<img>`
            não faz nada disso — o navegador abre numa aba e acabou.

            Convertido na entrada, o arquivo passa a se comportar como todos os
            outros e a lupa funciona igual. Guardamos o PDF original ao lado,
            que é o que a pessoa entregou.

        SEM O `pypdfium2` INSTALADO, DEVOLVE None E A VIDA SEGUE.
            O sistema roda em serventia, não em servidor de nuvem: uma
            biblioteca que falta não pode derrubar o envio da ficha. O PDF é
            guardado como está e a tela diz, em português, o que instalar para
            ele passar a ampliar.
        """
        try:
            import pypdfium2
        except ImportError:
            app.logger.info(
                "pypdfium2 ausente: a ficha em PDF foi guardada sem converter. "
                "Instale com: <runtime>\\Scripts\\python.exe -m pip install pypdfium2")
            return None
        import io as _io
        try:
            pdf = pypdfium2.PdfDocument(_io.BytesIO(dados))
            if len(pdf) == 0:
                return None
            # 200 DPI: acima disso o arquivo cresce sem o traço melhorar, e
            # ficha de firma é meia folha, não uma planta.
            imagem = pdf[0].render(scale=200 / 72).to_pil()
            buf = _io.BytesIO()
            imagem.save(buf, format="PNG", optimize=True)
            return buf.getvalue()
        except Exception as erro:                              # noqa: BLE001
            app.logger.warning("Não consegui converter o PDF da ficha: %s", erro)
            return None

    def _guardar_ficha(con, cartao_id: int, nome_enviado: str, dados: bytes,
                       data_coleta: str | None, favorita: bool) -> tuple[bool, str]:
        """Grava uma ficha no acervo do sistema. Devolve (deu certo, recado).

        DENTRO DO ACERVO, e não numa pasta qualquer: é a pasta que o backup já
        varre. Foi a mesma escolha feita para as fichas do Registro de Imóveis
        e para a cópia das assinaturas do E-Ofício, e vale repetir o motivo —
        digitalização que não entra no backup é digitalização que se perde na
        primeira troca de disco.
        """
        sufixo = Path(nome_enviado or "").suffix.lower()
        if sufixo not in EXTENSOES_DA_FICHA:
            return False, (f"{nome_enviado}: tipo não aceito. Envie a ficha em "
                           f"JPG, PNG ou PDF.")
        if not dados:
            return False, f"{nome_enviado}: arquivo vazio."
        if len(dados) > LIMITE_DA_FICHA:
            return False, (f"{nome_enviado}: {len(dados) / 1048576:.1f} MB é grande "
                           f"demais para uma ficha (o limite é 25 MB). Digitalize "
                           f"em 200 ou 300 DPI, que é o suficiente para firma.")

        aviso = ""
        if sufixo == ".pdf":
            convertido = _pdf_para_imagem(dados)
            if convertido:
                dados, sufixo = convertido, ".png"
            else:
                aviso = (" O PDF foi guardado como veio: falta o pypdfium2 no "
                         "servidor para convertê-lo em imagem, então ele abre "
                         "numa aba em vez de ampliar na lupa.")

        # DUPLICATA PELO CONTEÚDO, e não pelo nome do arquivo.
        #   `digitalizar001.jpg` é o nome que todo scanner dá. Conferir pelo
        #   nome deixaria passar a mesma ficha enviada duas vezes e recusaria
        #   duas fichas diferentes com o mesmo nome — errado dos dois lados.
        digest = hashlib.sha256(dados).hexdigest()
        igual = con.execute(
            "SELECT id FROM nt_cartao_imagens WHERE cartao_id=? AND sha256=?",
            (cartao_id, digest)).fetchone()
        if igual:
            return False, (f"{nome_enviado}: esta imagem já está neste cartão "
                           f"(nº {igual[0]}). Nada foi gravado em duplicidade.")

        pasta = pasta_assinaturas_internas() / str(cartao_id)
        pasta.mkdir(parents=True, exist_ok=True)
        proxima = (con.execute(
            "SELECT COALESCE(MAX(ordem), 0) + 1 FROM nt_cartao_imagens WHERE cartao_id=?",
            (cartao_id,)).fetchone()[0])
        nome = f"ficha-{cartao_id}-{proxima}{sufixo}"
        while (pasta / nome).exists():
            proxima += 1
            nome = f"ficha-{cartao_id}-{proxima}{sufixo}"
        alvo = pasta / nome
        alvo.write_bytes(dados)

        raiz = pasta_assinaturas_internas().parent.parent
        if favorita:
            con.execute("UPDATE nt_cartao_imagens SET favorita=0 WHERE cartao_id=?",
                        (cartao_id,))
        con.execute(
            """INSERT INTO nt_cartao_imagens
               (cartao_id, ordem, nome_arquivo, caminho, caminho_interno, sha256,
                bytes, favorita, data, copiado_em, criado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (cartao_id, proxima, nome, str(pasta),
             str(alvo.relative_to(raiz)), digest, len(dados),
             1 if favorita else 0, data_coleta or None, db.now(), db.now()))
        return True, f"{nome_enviado} guardada no cartão.{aviso}"

    def _enviar_fichas(cartao_id: int) -> tuple[int, list[str]]:
        """Percorre os arquivos do formulário. Devolve (quantas entraram, recusas).

        UM ARQUIVO RUIM NÃO DERRUBA OS OUTROS. Quem envia as três vias de uma
        vez e erra numa delas precisa que as duas boas entrem e que a recusa
        diga qual foi — e não perder as três com uma mensagem só.
        """
        arquivos = [f for f in request.files.getlist("ficha") if f and f.filename]
        if not arquivos:
            return 0, []
        data_coleta = (request.form.get("data_coleta") or "").strip() or None
        quer_favorita = request.form.get("favorita") == "1"
        entraram, recusas = 0, []
        with db.transaction() as con:
            tem_favorita = con.execute(
                "SELECT COUNT(*) FROM nt_cartao_imagens WHERE cartao_id=? AND favorita=1",
                (cartao_id,)).fetchone()[0]
            for n, fs in enumerate(arquivos):
                # A primeira ficha de um cartão que ainda não tem nenhuma vira
                # a favorita sozinha: é a que vai aparecer nas listas e no
                # balcão, e ninguém deveria precisar escolher o óbvio.
                favorita = (quer_favorita and n == 0) or (not tem_favorita and n == 0)
                ok, recado = _guardar_ficha(con, cartao_id, fs.filename,
                                            fs.read(), data_coleta, favorita)
                if ok:
                    entraram += 1
                    if favorita:
                        tem_favorita = 1
                else:
                    recusas.append(recado)
        if entraram:
            audit("NT_FICHA_ENVIADA", "NT_CARTAO", cartao_id,
                  {"quantas": entraram, "recusadas": len(recusas)})
        return entraram, recusas

    @app.route("/notas/cartoes/<int:cartao_id>/fichas", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_cartao_ficha_enviar(cartao_id):
        """Recebe a digitalização da ficha de firma e a guarda no cartão."""
        if not q1("SELECT id FROM nt_cartoes WHERE id=?", (cartao_id,)):
            abort(404)
        entraram, recusas = _enviar_fichas(cartao_id)
        if not entraram and not recusas:
            flash("Nenhum arquivo foi escolhido.", "warning")
        elif entraram:
            flash(f"{entraram} ficha(s) guardada(s) no cartão."
                  + (" " + " ".join(recusas) if recusas else ""),
                  "warning" if recusas else "success")
        else:
            flash(" ".join(recusas), "danger")
        return redirect(url_for("notas_cartao", cartao_id=cartao_id))

    @app.route("/notas/cartoes/imagem/<int:imagem_id>/gerir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_cartao_imagem_gerir(imagem_id):
        """Favorita, data da coleta e remoção — as três coisas que se faz depois.

        A REMOÇÃO APAGA A LINHA, MAS NÃO O ARQUIVO.
            Ficha de firma é peça de conferência de ato notarial. Errar o
            cartão ao enviar é comum e tem de ter conserto na tela; apagar do
            disco a digitalização de uma assinatura não tem conserto nenhum.
            A linha sai da tela, o arquivo fica no acervo, e a auditoria
            registra quem tirou e de onde — de modo que se for engano, se
            recupera.
        """
        img = q1("SELECT * FROM nt_cartao_imagens WHERE id=?", (imagem_id,))
        if not img:
            abort(404)
        cartao_id = img["cartao_id"]
        acao = request.form.get("acao")

        if acao == "favorita":
            with db.transaction() as con:
                con.execute("UPDATE nt_cartao_imagens SET favorita=0 WHERE cartao_id=?",
                            (cartao_id,))
                con.execute("UPDATE nt_cartao_imagens SET favorita=1 WHERE id=?",
                            (imagem_id,))
            audit("NT_FICHA_FAVORITA", "NT_CARTAO_IMAGEM", imagem_id,
                  {"cartao_id": cartao_id})
            flash("Esta via passou a ser a que aparece nas listas e no balcão.",
                  "success")

        elif acao == "data":
            nova = (request.form.get("data_coleta") or "").strip() or None
            with db.transaction() as con:
                con.execute("UPDATE nt_cartao_imagens SET data=? WHERE id=?",
                            (nova, imagem_id))
            audit("NT_FICHA_DATA", "NT_CARTAO_IMAGEM", imagem_id, {"data": nova})
            flash("Data da coleta anotada." if nova else "Data da coleta apagada.",
                  "success")

        elif acao == "remover":
            with db.transaction() as con:
                con.execute("DELETE FROM nt_cartao_imagens WHERE id=?", (imagem_id,))
                # Sem favorita, a próxima da fila assume — senão o cartão fica
                # com imagens e nenhuma delas aparecendo no balcão.
                if img["favorita"]:
                    proxima = con.execute(
                        "SELECT id FROM nt_cartao_imagens WHERE cartao_id=? "
                        "ORDER BY ordem LIMIT 1", (cartao_id,)).fetchone()
                    if proxima:
                        con.execute("UPDATE nt_cartao_imagens SET favorita=1 WHERE id=?",
                                    (proxima[0],))
            audit("NT_FICHA_REMOVIDA", "NT_CARTAO_IMAGEM", imagem_id,
                  {"cartao_id": cartao_id, "nome_arquivo": img["nome_arquivo"],
                   "caminho_interno": img["caminho_interno"],
                   "observacao": "linha removida; arquivo mantido no acervo"})
            flash(f"Imagem retirada do cartão. O arquivo continua guardado no "
                  f"acervo ({img['nome_arquivo']}) e a auditoria registrou a "
                  f"retirada — se foi engano, dá para recuperar.", "success")
        else:
            flash("Ação desconhecida.", "danger")
        return redirect(url_for("notas_cartao", cartao_id=cartao_id))

    def _arquivo_da_assinatura(img) -> Path | None:
        """Onde a assinatura está, na ordem em que vale a pena procurar.

        A CÓPIA DO PRÓPRIO SISTEMA VEM PRIMEIRO, e é o ponto todo.
            O E-Ofício grava o caminho como `\\\\servidor\\C11\\Firmas\\` — UNC.
            O serviço roda como SYSTEM, que não enxerga compartilhamento
            montado na sessão do usuário: o caminho está gravado, existe para
            quem está logado, e mesmo assim o servidor não abre.

            Foi assim que as 3.637 assinaturas ficaram invisíveis no sistema
            novo. Copiadas para dentro do acervo, o problema deixa de existir —
            e de quebra elas passam a entrar no backup.
        """
        interno = img["caminho_interno"] if "caminho_interno" in img.keys() else None
        if interno:
            p = pasta_assinaturas_internas().parent.parent / interno
            if _e_arquivo(p):
                return p
        nome = (img["nome_arquivo"] or "").strip()
        if not nome:
            return None
        for pasta in pastas_firmas():
            candidato = pasta / nome
            if _e_arquivo(candidato):
                return candidato
        if img["caminho"]:
            direto = Path(img["caminho"]) / nome
            if _e_arquivo(direto):
                return direto
        return None

    def pasta_assinaturas_internas() -> Path:
        """Onde o sistema guarda a sua cópia das assinaturas.

        Dentro da pasta de arquivos, que o backup já varre — a mesma escolha
        feita para as fichas do Registro de Imóveis.
        """
        raiz = Path(db.get_setting("archive_root", "").strip()
                    or (Path(db.db_path).parent / "arquivos"))
        destino = raiz / "notas" / "firmas"
        destino.mkdir(parents=True, exist_ok=True)
        return destino

    @app.route("/notas/assinaturas", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_assinaturas():
        """Localizar e trazer para dentro as assinaturas digitalizadas.

        Mesma tela que o Registro de Imóveis tem para as fichas, e pelo mesmo
        motivo: enquanto os arquivos moram na pasta do E-Ofício, eles não são
        nossos — e, sendo UNC, o servidor sequer os alcança.
        """
        # A cópia do acervo primeiro: é local, o serviço a enxerga, e
        # sobrevive ao desligamento do E-Ofício.
        raiz_padrao = (db.get_setting("nt_pasta_firmas", "") or "").strip() \
            or str(pasta_firmas_do_acervo())

        if request.method == "POST":
            acao = request.form.get("acao") or "resolver"
            nova = (request.form.get("raiz") or "").strip()
            if nova:
                db.set_settings({"nt_pasta_firmas": nova})
                raiz_padrao = nova
            raiz = Path(raiz_padrao)

            if acao == "resolver":
                # TODAS as pastas de busca, e não só a que está gravada na
                # configuração.
                #
                # ERA O DEFEITO. As 3.644 firmas já tinham vindo para o acervo,
                # e a tela continuava medindo o `\\servidor\C11\Firmas` morto —
                # respondendo "nenhuma assinatura localizada" com os arquivos
                # ali, no disco, ao lado. Medir uma pasta e responder sobre
                # todas é uma resposta que parece medição.
                candidatas = pastas_firmas()
                if _e_pasta(raiz) and not any(
                        str(p).lower() == str(raiz).lower() for p in candidatas):
                    candidatas.insert(0, raiz)
                if not candidatas:
                    flash(f"Nenhuma pasta de assinaturas abriu — nem a cópia do "
                          f"acervo em {pasta_firmas_do_acervo()}, nem {raiz}. O "
                          f"serviço roda como SYSTEM: caminho local funciona, "
                          f"unidade mapeada e \\\\servidor\\... não. Rode o "
                          f"COPIAR_ARQUIVOS_EOFICIO.cmd.", "danger")
                    return redirect(url_for("notas_assinaturas"))
                indice, arquivos, exemplos, abertas = RIMG.indexar_varias(candidatas)
                raiz = abertas[0]
                achadas = perdidas = 0
                perdidos: list[str] = []
                with db.transaction() as con:
                    con.row_factory = sqlite3.Row
                    for linha in con.execute(
                            "SELECT id, nome_arquivo FROM nt_cartao_imagens "
                            "WHERE nome_arquivo IS NOT NULL"):
                        caminho = RIMG.achar(linha["nome_arquivo"], indice)
                        if caminho:
                            con.execute("UPDATE nt_cartao_imagens SET caminho=? "
                                        "WHERE id=?", (str(Path(caminho).parent),
                                                       linha["id"]))
                            achadas += 1
                        else:
                            perdidas += 1
                            if len(perdidos) < 5:
                                perdidos.append(linha["nome_arquivo"])
                audit("NT_ASSINATURAS_RESOLVIDAS", "NT_CARTAO_IMAGEM", None,
                      {"raiz": str(raiz), "achadas": achadas, "perdidas": perdidas})
                if perdidas and not achadas:
                    flash(f"Nenhuma das {perdidas} assinaturas foi localizada em "
                          f"{raiz}, onde varri {arquivos} arquivo(s). No banco os "
                          f"nomes são como: {', '.join(perdidos)}. No disco são "
                          f"como: {', '.join(exemplos) or '(pasta vazia)'}. "
                          f"Não se parecendo, a pasta é outra.", "danger")
                else:
                    flash(f"{achadas} assinaturas localizadas de "
                          f"{achadas + perdidas}, entre {arquivos} arquivos.",
                          "success" if not perdidas else "warning")
                return redirect(url_for("notas_assinaturas"))

            if acao == "copiar":
                import shutil
                destino = pasta_assinaturas_internas()
                copiadas = ja_tinha = sem_origem = 0
                bytes_total = 0
                with db.transaction() as con:
                    con.row_factory = sqlite3.Row
                    for linha in con.execute(
                            """SELECT id, cartao_id, nome_arquivo, caminho,
                                      caminho_interno FROM nt_cartao_imagens
                               WHERE nome_arquivo IS NOT NULL"""):
                        rel = linha["caminho_interno"]
                        if rel and _e_arquivo(destino.parent.parent / rel):
                            ja_tinha += 1
                            continue
                        origem = _arquivo_da_assinatura(linha)
                        if origem is None:
                            sem_origem += 1
                            continue

                        # JÁ ESTANDO DENTRO DO ACERVO, ADOTA-SE NO LUGAR
                        # DE COPIAR.
                        #     O COPIAR_ARQUIVOS_EOFICIO trouxe as 3.644
                        #     assinaturas para `arquivos\eoficio\Firmas` — 356
                        #     MB que o backup completo já varre. Copiá-las de
                        #     novo para `arquivos\notas\firmas` faria o mesmo
                        #     acervo pesar 712 MB, e todo backup a partir daí
                        #     carregaria as duas cópias.
                        raiz_acervo = destino.parent.parent
                        try:
                            dentro = origem.resolve().relative_to(
                                raiz_acervo.resolve())
                        except (ValueError, OSError):
                            dentro = None
                        if dentro is not None:
                            conteudo = origem.read_bytes()
                            con.execute(
                                """UPDATE nt_cartao_imagens
                                     SET caminho_interno=?, sha256=?, bytes=?,
                                         copiado_em=? WHERE id=?""",
                                (str(dentro),
                                 hashlib.sha256(conteudo).hexdigest(),
                                 len(conteudo), db.now(), linha["id"]))
                            ja_tinha += 1
                            continue

                        sub = destino / str(linha["cartao_id"] or "sem_cartao")
                        sub.mkdir(parents=True, exist_ok=True)
                        alvo = sub / linha["nome_arquivo"]
                        try:
                            shutil.copy2(origem, alvo)
                            conteudo = alvo.read_bytes()
                            con.execute(
                                """UPDATE nt_cartao_imagens
                                     SET caminho_interno=?, sha256=?, bytes=?,
                                         copiado_em=? WHERE id=?""",
                                (str(alvo.relative_to(destino.parent.parent)),
                                 hashlib.sha256(conteudo).hexdigest(),
                                 len(conteudo), db.now(), linha["id"]))
                            copiadas += 1
                            bytes_total += len(conteudo)
                        except OSError as erro:
                            app.logger.warning("Assinatura %s não copiou: %s",
                                               linha["id"], erro)
                audit("NT_ASSINATURAS_INTERNALIZADAS", "NT_CARTAO_IMAGEM", None,
                      {"copiadas": copiadas, "ja_existiam": ja_tinha,
                       "sem_origem": sem_origem})
                flash(f"{copiadas} assinaturas copiadas para o acervo do sistema "
                      f"({bytes_total / 1048576:.1f} MB). {ja_tinha} já estavam. "
                      + (f"{sem_origem} sem arquivo de origem." if sem_origem else ""),
                      "warning" if sem_origem else "success")
                return redirect(url_for("notas_assinaturas"))

        n = q1("""SELECT COUNT(*) total,
                  COALESCE(SUM(CASE WHEN caminho_interno IS NOT NULL THEN 1 ELSE 0 END),0) copiadas,
                  COALESCE(SUM(bytes),0) bytes FROM nt_cartao_imagens""")
        raiz = Path(raiz_padrao)
        diag = None
        if n["total"] and n["copiadas"] < n["total"]:
            nomes = [r["nome_arquivo"] for r in
                     q("""SELECT nome_arquivo FROM nt_cartao_imagens
                          WHERE nome_arquivo IS NOT NULL AND caminho_interno IS NULL
                          LIMIT 500""")]
            candidatas = pastas_firmas()
            if _e_pasta(raiz) and not any(
                    str(p).lower() == str(raiz).lower() for p in candidatas):
                candidatas.insert(0, raiz)
            diag = RIMG.diagnostico(nomes, candidatas or [raiz])
        return render_template("notas_assinaturas.html", raiz=str(raiz),
                               existe=bool(pastas_firmas()) or _e_pasta(raiz),
                               total=n["total"],
                               copiadas=n["copiadas"], diag=diag,
                               megabytes=round((n["bytes"] or 0) / 1048576, 1),
                               padroes=(str(pasta_firmas_do_acervo()),)
                               + PASTAS_FIRMAS_PADRAO)

    # =================================================== reconhecimento

    # ------------------------------------------------- o selo automatico
    #
    # «O selo deve ser emitido quando praticado o ato. Igual o E-Oficio» —
    # decisao do oficial em 27/08/2026. As Notas foram a ultima atribuicao a
    # ser ligada, e sao a MAIOR: `/selo/notas/reconhecimento-firma` sozinho e
    # metade dos 26.130 selos que esta casa emitiu.
    #
    # Ate hoje esta tela terminava dizendo «Falta colar o selo», e era verdade.

    def selar_simples(tabela: str, ato_id: int, *, servico: int,
                      quantas: int = 1, partes=None) -> str:
        """Um selo por unidade, na autenticacao e no cartao de autografo.

        UM SELO POR FOLHA, e isto e medido: no E-Oficio cada folha
        autenticada era uma linha e um selo — 3.539 autenticacoes, TODAS com
        uma folha so, 3.539 selos distintos e nenhum repetido —, e o envelope
        levava `quantidade: 1` nos 3.664 selos medidos. O item 13.18 e por
        pagina; autenticar cinco folhas e cobrar cinco e selar cinco.

        O CARTAO SELA UMA VEZ, na abertura: `/selo/notas/cartao-assinatura`,
        2.667 usos, e o campo do ato chama-se `selo_abertura`.

        NUNCA DERRUBA O ATO — mesma regra do reconhecimento.
        """
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return SR.recado_pendente_selo()
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            linha = con.execute("SELECT codigo_tj FROM cx_servicos WHERE codigo=?",
                                (int(servico),)).fetchone()
        codigo_tj = (linha["codigo_tj"] if linha else None) or None
        if not codigo_tj:
            return (f" O ato foi lavrado SEM SELO: o serviço {servico} não tem "
                    f"item da tabela do TJMA no cadastro.")
        caminho = AS.CAMINHO_DAS_NOTAS[tabela]
        # A VERSAO E A DATA DA TABELA EM VIGOR, e nao a de hoje — ver o
        # comentario em `selar_reconhecimento`.
        try:
            versao = AS.versao_da_tabela_de_custas(
                caminho, db.get_setting("selo_tabela_custas_em", ""))
            if not versao:
                return (" O ato foi lavrado SEM SELO: falta dizer de que data "
                        "é a tabela de custas em vigor, em Administrativo → "
                        "Configurações.")
            envelope = AS.envelope_das_notas(
                tabela=tabela, codigo_tj=codigo_tj, escrevente=usuario_nome(),
                versao_tabela=versao, partes=partes, quantidade=1)
        except Exception as erro:                              # noqa: BLE001
            return f" O ato foi lavrado SEM SELO: {erro}"

        saiu, faltou = [], []
        for n in range(1, max(1, int(quantas or 1)) + 1):
            r = AS.selar_o_ato_lavrado(
                db, Path(app.config["DATA_DIR"]), tabela=tabela,
                ato_id=ato_id, tipo="ATO", atribuicao="NOTAS",
                agora=datetime.now().isoformat(timespec="seconds"),
                cns=db.get_setting("ri_cns", ""), usuario=usuario_nome(),
                dados=envelope,
                # CADA UNIDADE COM A SUA REFERENCIA: e dela que sai o SID, e e
                # o SID que faz o aparelho devolver o selo que ja existe em vez
                # de vender outro. Uma so para cinco folhas traria o MESMO selo
                # cinco vezes.
                referencia=f"{tabela}:{int(ato_id)}:{codigo_tj}:{n}")
            (saiu if r["selado"] else faltou).append(
                r["numero"] if r["selado"] else r["motivo"])

        if not saiu:
            return f" O ato foi lavrado SEM SELO: {faltou[0] if faltou else ''}"
        coluna = "selo_abertura" if tabela == "nt_cartoes" else "selo"
        try:
            with db.transaction() as con:
                con.execute(f"UPDATE {tabela} SET {coluna}=? WHERE id=?",
                            (saiu[0], int(ato_id)))
        except sqlite3.Error as erro:
            return (f" {len(saiu)} selo(s) obtido(s), mas não consegui gravá-los "
                    f"no ato ({erro}) — eles estão no razão dos selos.")
        recado = (f" Selo {saiu[0]}." if len(saiu) == 1
                  else f" {len(saiu)} selos: {', '.join(saiu)}.")
        if faltou:
            recado += f" ({len(faltou)} sem selo: {faltou[0]})"
        return recado

    def selar_o_ato_de_livro(ato_id: int, *, codigo_tj: str,
                             especie_procuracao: str | None = None,
                             valor_declarado_centavos: int | None = None,
                             isento: bool = False,
                             motivo_isencao: str | None = None) -> str:
        """Pede o selo da ESCRITURA, PROCURACAO ou ATA. FALA COM A REDE.

            «constroi o modulo de selo automatizado na escritura (se ja nao
             houver), ali consta pra inserir o selo manualmente»
              — o oficial, 17/09/2026

        **DEPOIS DO LANCAMENTO, E NAO ANTES** — os 283 envelopes reais desta
        casa levam `selo{escrevente, livro, folha}`, e livro e folha so existem
        depois de o ato entrar no livro. E a mesma ordem do RCPN e do RTD.

        **NUNCA DERRUBA O ATO, e a razao e o proprio livro.** A regra do item 1
        («selo que falha suspende o ato») existe porque no RI corrigir e lavrar
        de novo resolve; aqui a folha e o termo ja foram escritos, e o sistema
        recusa desfazer isso. O ato fica em `atos_sem_selo` e o botao de selar
        continua na tela — corrige-se o aparelho e sela-se de novo.

        **FORA DA TRANSACAO**, como todo pedido de selo da casa: vinte segundos
        segurando o `BEGIN IMMEDIATE` poriam todo outro balcao no
        `busy_timeout`.
        """
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return SR.recado_pendente_selo()
        a = q1("SELECT * FROM nt_atos WHERE id=?", (int(ato_id),))
        if not a:
            return " O ato não existe."
        erro_item = _conferir_item_da_escritura(a, codigo_tj)
        if erro_item:
            return f" O ato foi lavrado SEM SELO: {erro_item}"
        if str(a["selo"] or "").strip():
            return (f" O ato já tem o selo {a['selo']} — dois selos para o "
                    f"mesmo ato é o dinheiro da serventia saindo duas vezes.")
        if not str(a["livro"] or "").strip():
            return (" O ato foi lavrado SEM SELO: o pedido leva o livro e a "
                    "folha, e este ato ainda não foi lançado no livro.")
        versao = AS.versao_da_tabela_de_custas(
            "/selo/notas/ato-declarado/sem-valor",
            db.get_setting("selo_tabela_custas_em", ""))
        if not versao:
            return (" O ato foi lavrado SEM SELO: falta dizer de que data é a "
                    "tabela de custas em vigor, em Administrativo → "
                    "Configurações.")
        partes = [dict(p) for p in q(
            "SELECT nome, documento FROM nt_ato_partes WHERE ato_id=? ORDER BY id",
            (int(ato_id),))]
        # O VALOR VEM DO ATO quando ele ja o declara — `valor_transacao` esta
        # em CENTAVOS, como o resto do sistema, e o envelope pede REAIS.
        centavos = (valor_declarado_centavos
                    if valor_declarado_centavos is not None
                    else a["valor_transacao"])
        try:
            envelope, caminho = AS.envelope_do_ato_de_livro_das_notas(
                tipo=a["tipo"], codigo_tj=codigo_tj, escrevente=usuario_nome(),
                versao_tabela=versao, livro=a["livro"], folha=a["folha"],
                termo=a["termo"], partes=partes,
                valor_declarado=(int(centavos) / 100.0
                                 if centavos not in (None, "") else None),
                especie_procuracao=especie_procuracao,
                isento=isento, motivo_isencao=motivo_isencao)
        except AS.AtoError as erro:
            return f" O ato foi lavrado SEM SELO: {erro}"
        r = AS.selar_o_ato_lavrado(
            db, Path(app.config["DATA_DIR"]), tabela="nt_atos",
            ato_id=int(ato_id), tipo=(a["tipo"] or "ATO"), atribuicao="NOTAS",
            agora=datetime.now().isoformat(timespec="seconds"),
            cns=db.get_setting("ri_cns", ""), usuario=usuario_nome(),
            dados=envelope, caminho=caminho,
            referencia=f"nt_atos:{int(ato_id)}:{codigo_tj}:1")
        if not r["selado"]:
            return f" O ato foi lavrado SEM SELO: {r['motivo']}"
        return f" Selo {r['numero']}."

    def _atualizar_data_teor_antes_do_selo(ato_id: int) -> None:
        """Relato #116 — data do instrumento = dia em que o selo sai."""
        agora = datetime.now()
        with db.transaction() as con:
            NT.atualizar_teor_para_data_de_selo(
                con,
                int(ato_id),
                quando=agora,
                sv=_sv(),
                lavrado_nome=usuario_nome(),
                lavrado_titulo=usuario_funcao(),
            )

    def _selar_arquivamento_das_notas(*, ato_id: int, folhas: int,
                                      selo_do_ato: str | None = None,
                                      partes=None,
                                      isento: bool = False,
                                      motivo_isencao=None) -> dict:
        """Selo 13.30 (arquivamento por folha, Notas) — opcional junto com o do ato.

        Mesma prática do RI (Beatriz 23/09/2026): o selo da escritura sai
        primeiro; o de arquivamento é pedido em seguida e grava em
        `selo_arquivamento`, sem substituir `nt_atos.selo`.
        """
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return SR.recado_pendente_selo()
        try:
            q = max(1, int(folhas or 0))
        except (TypeError, ValueError):
            return {"ok": False,
                    "motivo": "informe a quantidade de folhas (>= 1)."}
        if q < 1:
            return {"ok": False,
                    "motivo": "informe a quantidade de folhas (>= 1)."}
        # HOTFIX-2026-10-08-03 (Carla 08/10/2026): o arquivamento das NOTAS
        # e o item 13.30 da tabela do TJMA (grupo 21, "Arquivamento, por folha
        # do documento"), pelo caminho /selo/notas/atos-em-geral - 712 usos
        # medidos no acervo. O 16.39 e o arquivamento do Registro de Imoveis
        # (grupo 24) e saia aqui com a tabela de custas do RI (prefixo 02).
        codigo_arq = "13.30"
        caminho = "/selo/notas/atos-em-geral"
        versao = AS.versao_da_tabela_de_custas(
            caminho, db.get_setting("selo_tabela_custas_em", ""))
        if not versao:
            return {"ok": False,
                    "motivo": ("falta a data da tabela de custas em "
                               "Administrativo / Configurações.")}
        try:
            envelope = AS.envelope_do_arquivamento_do_ri(
                escrevente=usuario_nome(), versao_tabela=versao, quantidade=q,
                partes=[{"nome": n, "documento": d}
                        for n, d in (partes or []) if str(n or "").strip()],
                isento=bool(isento),
                motivo_isencao=motivo_isencao)
        except AS.AtoError as erro:
            return {"ok": False, "motivo": str(erro)}
        envelope["ato"]["codigo"] = codigo_arq

        if selo_do_ato is None:
            row = q1("SELECT selo FROM nt_atos WHERE id=?", (int(ato_id),))
            selo_do_ato = (row["selo"] if row else None)

        r = AS.selar_o_ato_lavrado(
            db, Path(app.config["DATA_DIR"]), tabela="nt_atos", ato_id=ato_id,
            tipo="ARQUIV", atribuicao="NOTAS",
            agora=datetime.now().isoformat(timespec="seconds"),
            cns=db.get_setting("ri_cns", ""), usuario=usuario_nome(),
            dados=envelope, caminho=caminho,
            referencia=f"nt_atos:{int(ato_id)}:{codigo_arq}:1")
        if not r["selado"]:
            if selo_do_ato:
                with db.transaction() as con:
                    con.execute("UPDATE nt_atos SET selo=? WHERE id=?",
                                (selo_do_ato, int(ato_id)))
            return {"ok": False, "motivo": r["motivo"]}

        with db.transaction() as con:
            con.execute(
                """UPDATE nt_atos
                      SET selo=COALESCE(?, selo),
                          selo_arquivamento=?,
                          folhas_arquivamento=?
                    WHERE id=?""",
                (selo_do_ato or None, r["numero"], q, int(ato_id)))
        return {"ok": True, "numero": r["numero"], "folhas": q,
                "recado": f" Arquivamento {r['numero']} ({q} folha(s))."}

    def motivo_da_falha_do_selo(recado: str) -> str | None:
        """Extrai o motivo legível de mensagens de selo.

        A tela precisa dizer POR QUE o selo não saiu. O selador já devolve esse
        texto; esta função só tira o prefixo comum para a rota decidir se
        bloqueia o ato ou se registra a decisão expressa de lavrar sem selo.
        """
        texto = str(recado or "").strip()
        if "SEM SELO:" in texto:
            return texto.split("SEM SELO:", 1)[1].strip() or "falha sem detalhe"
        if "sem selo:" in texto.lower():
            return texto.split(":", 1)[1].strip() or "falha sem detalhe"
        if " SEM SELO" in f" {texto}" or "sem selo" in texto.lower():
            return texto or "falha sem detalhe"
        return None

    def selar_reconhecimento(rid: int, *, servico: int, especie: str,
                             partes: list[dict]) -> dict:
        """Um selo para CADA firma, depois do ato lavrado. FALA COM A REDE.

        UM SELO POR FIRMA, e isto e medido, nao suposto. No E-Oficio cada
        firma era um ato e um selo: 13.213 reconhecimentos, TODOS com uma
        firma so, e o envelope levava UMA pessoa em `nomesReconhecido.
        parteAto` nos 13.776 selos medidos.

        Este sistema deixa marcar varios cartoes de uma vez. Cada firma cobra
        o seu item da tabela — um selo para tres firmas seria a serventia
        cobrando tres e selando uma.

        CADA FIRMA LEVA A SUA REFERENCIA. E dela que sai o SID, e e o SID que
        faz o aparelho devolver o selo que ja existe em vez de vender outro.
        Uma referencia so para tres firmas traria o MESMO selo tres vezes.

        FORA DA TRANSACAO DO ATO: a chamada ao aparelho tem prazo de vinte
        segundos, e segurar o `BEGIN IMMEDIATE` da casa por vinte segundos
        poria todo outro balcao no `busy_timeout`.

        A FALHA VOLTA ESTRUTURADA. Quem lavra decide se o ato pode ficar sem
        selo. Sem decisao expressa, a rota desfaz o reconhecimento recem-criado:
        etiqueta sem selo colada em documento e pior que balcão parado por
        alguns segundos, porque vira um ato que a parte nao consegue conferir.
        """
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return SR.reconhecimento_pendente()
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            linha = con.execute("SELECT codigo_tj FROM cx_servicos WHERE codigo=?",
                                (int(servico),)).fetchone()
        codigo_tj = (linha["codigo_tj"] if linha else None) or None
        if not codigo_tj:
            motivo = (f"o serviço {servico} não tem item da tabela do TJMA "
                      f"no cadastro.")
            return {"ok": False, "mensagem": f" SEM SELO: {motivo}",
                    "motivo": motivo, "selos": []}
        # A VERSAO E A DATA EM QUE A TABELA ENTROU EM VIGOR, e nao a data do
        # ato — e este foi o segundo defeito que o balcao achou em 27/08/2026.
        #
        #   Eu passava `date.today()`, e saia `0520260827`. O selador nao tem
        #   tabela de custas que comece em 27 de agosto, e respondeu «Nao foi
        #   encontrado um ato para o codigo informado». O certo e `0520260101`
        #   — usado 518 vezes por esta casa so este ano, com o item 13.17.2.
        #
        #   Ela mora em `selo_tabela_custas_em`, que existe exatamente para
        #   isso: o TJMA publica tabela nova, o oficial troca a data na tela, e
        #   ninguem precisa mexer no codigo para o balcao voltar a selar.
        versao = AS.versao_da_tabela_de_custas(
            AS.CAMINHO_DAS_NOTAS["nt_reconhecimentos"],
            db.get_setting("selo_tabela_custas_em", ""))
        if not versao:
            motivo = ("falta dizer de que data é a tabela de custas em vigor, "
                      "em Administrativo → Configurações.")
            return {"ok": False, "mensagem": f" SEM SELO: {motivo}",
                    "motivo": motivo, "selos": []}

        saiu, faltou = [], []
        for p in partes:
            try:
                envelope = AS.envelope_das_notas(
                    tabela="nt_reconhecimentos", codigo_tj=codigo_tj,
                    escrevente=usuario_nome(), versao_tabela=versao,
                    especie=especie, partes=[p])
            except AS.AtoError as erro:
                faltou.append(str(erro))
                continue
            r = AS.selar_o_ato_lavrado(
                db, Path(app.config["DATA_DIR"]),
                tabela="nt_reconhecimentos", ato_id=rid, tipo="ATO",
                atribuicao="NOTAS",
                agora=datetime.now().isoformat(timespec="seconds"),
                cns=db.get_setting("ri_cns", ""), usuario=usuario_nome(),
                dados=envelope,
                referencia=f"nt_reconhecimentos:{int(rid)}:{p['parte_id']}")
            if r["selado"]:
                saiu.append((p["parte_id"], r["numero"]))
            else:
                faltou.append(r["motivo"])

        if not saiu:
            motivo = faltou[0] if faltou else "o selador não devolveu selo."
            return {"ok": False, "mensagem": f" SEM SELO: {motivo}",
                    "motivo": motivo, "selos": []}
        try:
            with db.transaction() as con:
                for parte_id, numero in saiu:
                    con.execute(
                        "UPDATE nt_reconhecimento_partes SET selo=? WHERE id=?",
                        (numero, int(parte_id)))
                # O ATO GUARDA O PRIMEIRO, porque e o que a tela e a etiqueta
                # mostram. Os outros nao se perdem: cada firma tem o seu, e
                # todos estao no razao dos selos.
                con.execute("UPDATE nt_reconhecimentos SET selo=? WHERE id=?",
                            (saiu[0][1], int(rid)))
        except sqlite3.Error as erro:
            motivo = (f"{len(saiu)} selo(s) obtido(s), mas não consegui "
                      f"gravá-los no ato ({erro}) — eles estão no razão dos "
                      f"selos.")
            return {"ok": False, "mensagem": f" SEM SELO: {motivo}",
                    "motivo": motivo, "selos": [n for _, n in saiu]}
        recado = (f" Selo {saiu[0][1]}." if len(saiu) == 1
                  else f" {len(saiu)} selos: "
                       f"{', '.join(n for _, n in saiu)}.")
        if faltou:
            motivo = f"{len(faltou)} firma(s) sem selo: {faltou[0]}"
            recado += f" ({motivo})"
            return {"ok": False, "mensagem": recado, "motivo": motivo,
                    "selos": [n for _, n in saiu]}
        return {"ok": True, "mensagem": recado, "motivo": None,
                "selos": [n for _, n in saiu]}

    @app.route("/notas/reconhecimento", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_reconhecimento():
        """O balcão: procura o cartão, confere a assinatura e reconhece."""
        if request.method == "POST" and request.form.get("acao") == "reconhecer":
            ids = [int(x) for x in request.form.getlist("cartao_id") if str(x).isdigit()]
            especie = (request.form.get("especie") or "SEMELHANCA").upper()
            if not ids:
                flash("Escolha pelo menos um cartão.", "danger")
                return redirect(url_for("notas_reconhecimento"))
            if especie not in ESPECIES_RECONHECIMENTO:
                especie = "SEMELHANCA"

            cartoes = [dict(r) for r in q(
                f"SELECT * FROM nt_cartoes WHERE id IN ({','.join('?' * len(ids))})", ids)]
            bloqueados = [c["nome"] for c in cartoes if c["bloqueado"]]
            if bloqueados and not request.form.get("confirmar_bloqueio"):
                flash("Cartão bloqueado: " + ", ".join(bloqueados)
                      + ". Para reconhecer assim mesmo, marque a confirmação.", "danger")
                return redirect(url_for("notas_reconhecimento"))
            # Cartão que só admite autenticidade não pode sair por semelhança:
            # dizer uma espécie pela outra é falsidade, não estilo.
            so_aut = [c["nome"] for c in cartoes if c["somente_autenticidade"]]
            if so_aut and especie != "AUTENTICIDADE":
                flash("Estes cartões só admitem reconhecimento por autenticidade: "
                      + ", ".join(so_aut) + ".", "danger")
                return redirect(url_for("notas_reconhecimento"))

            veiculo = request.form.get("veiculo") == "1"
            financeiro = request.form.get("financeiro") == "1"
            servico = servico_do_reconhecimento(especie, veiculo, financeiro)
            sinal = request.form.get("sinal_publico") == "1"
            texto = texto_reconhecimento(especie, [c["nome"] for c in cartoes], sinal)

            with db.transaction() as con:
                cur = con.execute(
                    """INSERT INTO nt_reconhecimentos
                       (data, hora, especie, servico_codigo, quantidade,
                        documento_descricao, documento_tipo, veiculo_placa,
                        conteudo_financeiro, sinal_publico, texto, oficial,
                        oficial_funcao, origem, criado_em)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'MANUAL', ?)""",
                    (date.today().isoformat(), datetime.now().strftime("%H:%M"),
                     especie, servico, len(cartoes),
                     (request.form.get("documento_descricao") or "").strip() or None,
                     (request.form.get("documento_tipo") or "").strip() or None,
                     (request.form.get("veiculo_placa") or "").strip().upper() or None,
                     1 if financeiro else 0, 1 if sinal else 0, texto,
                     usuario_nome(), usuario_funcao(), db.now()))
                rid = int(cur.lastrowid)
                # O ID DE CADA FIRMA VOLTA, porque e nele que o selo dela vai
                # ser gravado — e cada firma leva um selo proprio.
                partes = []
                for c in cartoes:
                    cur = con.execute(
                        """INSERT INTO nt_reconhecimento_partes
                           (reconhecimento_id, cartao_id, nome, documento, criado_em)
                           VALUES (?,?,?,?,?)""",
                        (rid, c["id"], c["nome"], c["documento"], db.now()))
                    partes.append({"parte_id": int(cur.lastrowid),
                                   "nome": c["nome"],
                                   "documento": c["documento"]})
            # O SELO SAI AGORA, FORA DA TRANSACAO — «igual o E-Oficio».
            selado = selar_reconhecimento(rid, servico=servico,
                                          especie=especie, partes=partes)
            audit("NT_RECONHECIMENTO_TENTADO", "NT_RECONHECIMENTO", rid,
                  {"especie": especie, "firmas": len(cartoes), "servico": servico,
                   "selo_ok": bool(selado["ok"]),
                   "motivo_selo": selado.get("motivo")})
            if not selado["ok"] and not selado["selos"]:
                with db.transaction() as con:
                    con.execute("DELETE FROM nt_reconhecimento_partes "
                                "WHERE reconhecimento_id=?", (rid,))
                    con.execute("DELETE FROM nt_reconhecimentos WHERE id=?", (rid,))
                audit("NT_RECONHECIMENTO_NAO_LAVRADO_SELO_FALHOU",
                      "NT_RECONHECIMENTO", rid,
                      {"especie": especie, "firmas": len(cartoes),
                       "servico": servico, "motivo": selado.get("motivo")})
                flash("Reconhecimento NÃO lavrado: o selo não saiu. "
                      f"Motivo: {selado.get('motivo') or 'falha sem detalhe'}. "
                      "Corrija o problema do selo e lavre de novo — o ato "
                      "fica suspenso até o selo sair (relato #77).", "danger")
                return redirect(url_for("notas_reconhecimento"))
            if not selado["ok"]:
                audit("NT_RECONHECIMENTO_LAVRADO_COM_FALHA_PARCIAL_DE_SELO",
                      "NT_RECONHECIMENTO", rid,
                      {"especie": especie, "firmas": len(cartoes),
                       "servico": servico, "motivo": selado.get("motivo"),
                       "selos": selado["selos"]})
            else:
                audit("NT_RECONHECIMENTO", "NT_RECONHECIMENTO", rid,
                      {"especie": especie, "firmas": len(cartoes),
                       "servico": servico, "selos": selado["selos"]})
            flash(f"Reconhecimento nº {rid} lavrado — {len(cartoes)} firma(s)."
                  f"{selado['mensagem']}",
                  "success" if selado["ok"] else "warning")
            return redirect(url_for("notas_reconhecimento_ver", reconhecimento_id=rid))

        busca = (request.args.get("busca") or "").strip()
        achados = []
        if len(busca) >= 3:
            with db.connect() as con:
                achados = NP.buscar_cartoes(con, busca, limite=12)
            for c in achados:
                c["avisos"] = NP.avisos_do_cartao(c)
                c["imagem"] = q1("""SELECT id FROM nt_cartao_imagens WHERE cartao_id=?
                                    ORDER BY favorita DESC, ordem LIMIT 1""", (c["id"],))
        hoje = q1("""SELECT COUNT(*) n, COALESCE(SUM(quantidade),0) firmas
                     FROM nt_reconhecimentos WHERE data=? AND cancelado=0""",
                  (date.today().isoformat(),))
        precos = {nome: emolumento_do_servico(cod)
                  for nome, cod in (("comum", SERVICOS["SEMELHANCA"]),
                                    ("veículo", SERVICOS["VEICULO"]),
                                    ("financeiro", SERVICOS["FINANCEIRO"]))}
        return render_template("notas_reconhecimento.html", busca=busca,
                               achados=achados, hoje=hoje, precos=precos,
                               ESPECIES=ESPECIES_RECONHECIMENTO)

    @app.route("/notas/reconhecimento/<int:reconhecimento_id>", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_reconhecimento_ver(reconhecimento_id):
        r = q1("SELECT * FROM nt_reconhecimentos WHERE id=?", (reconhecimento_id,))
        if not r:
            abort(404)

        if request.method == "POST":
            acao = request.form.get("acao")
            if acao == "selo":
                selo = (request.form.get("selo") or "").strip().upper()
                if not selo:
                    flash("Informe o selo.", "danger")
                else:
                    ja = q1("""SELECT id FROM nt_reconhecimentos WHERE selo=? AND id<>?""",
                            (selo, reconhecimento_id))
                    if ja:
                        flash(f"Este selo já está no reconhecimento nº {ja['id']}.", "danger")
                    else:
                        with db.transaction() as con:
                            con.execute("UPDATE nt_reconhecimentos SET selo=? WHERE id=?",
                                        (selo, reconhecimento_id))
                        audit("NT_RECONHECIMENTO_SELADO", "NT_RECONHECIMENTO",
                              reconhecimento_id, {"selo": selo})
                        flash("Selo registrado.", "success")
            elif acao == "cancelar":
                motivo = (request.form.get("motivo") or "").strip()
                if not motivo:
                    flash("Diga por que está cancelando.", "danger")
                else:
                    with db.transaction() as con:
                        con.execute("""UPDATE nt_reconhecimentos SET cancelado=1,
                                       motivo_cancelamento=?, cancelado_em=?,
                                       cancelado_por=? WHERE id=?""",
                                    (motivo, db.now(), usuario_nome(), reconhecimento_id))
                    audit("NT_RECONHECIMENTO_CANCELADO", "NT_RECONHECIMENTO",
                          reconhecimento_id, {"motivo": motivo})
                    flash("Reconhecimento cancelado. O registro fica, com o motivo.",
                          "success")
            return redirect(url_for("notas_reconhecimento_ver",
                                    reconhecimento_id=reconhecimento_id))

        partes = q("""SELECT p.*, c.nome nome_cartao, c.documento documento_cartao,
                             (SELECT i.id FROM nt_cartao_imagens i WHERE i.cartao_id=c.id
                               ORDER BY i.favorita DESC, i.ordem LIMIT 1) imagem_id
                      FROM nt_reconhecimento_partes p
                      LEFT JOIN nt_cartoes c ON c.id = p.cartao_id
                      WHERE p.reconhecimento_id=? ORDER BY p.id""", (reconhecimento_id,))
        presencas = {}
        if (r["especie"] or "").upper() == "AUTENTICIDADE":
            for pr in q("""SELECT origem_chave FROM nt_presencas
                           WHERE origem=? AND reconhecimento_id=?""",
                        (NL.ORIGEM_PRESENCA_RECONHECIMENTO, reconhecimento_id)):
                presencas[str(pr["origem_chave"] or "")] = True
        return render_template("notas_reconhecimento_ver.html", r=dict(r), partes=partes,
                               presencas=presencas,
                               emolumento=emolumento_do_servico(r["servico_codigo"],
                                                                r["quantidade"] or 1),
                               sv=dados_serventia(db.get_settings))

    @app.route("/notas/reconhecimento/<int:reconhecimento_id>/termo-comparecimento/<int:parte_id>")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_reconhecimento_termo_comparecimento(reconhecimento_id, parte_id):
        """Termo individual de comparecimento (.odt) — autenticidade (#91)."""
        r = q1("SELECT * FROM nt_reconhecimentos WHERE id=?", (reconhecimento_id,))
        if not r:
            abort(404)
        if r["cancelado"]:
            flash("Reconhecimento cancelado — não há termo a emitir.", "danger")
            return redirect(url_for("notas_reconhecimento_ver",
                                    reconhecimento_id=reconhecimento_id))
        if (r["especie"] or "").upper() != "AUTENTICIDADE":
            flash("Termo de comparecimento só se gera em reconhecimento por "
                  "autenticidade.", "warning")
            return redirect(url_for("notas_reconhecimento_ver",
                                    reconhecimento_id=reconhecimento_id))
        parte = q1(
            """SELECT p.*, c.nome nome_cartao, c.documento documento_cartao
               FROM nt_reconhecimento_partes p
               LEFT JOIN nt_cartoes c ON c.id = p.cartao_id
               WHERE p.id=? AND p.reconhecimento_id=?""",
            (parte_id, reconhecimento_id))
        if not parte:
            abort(404)
        sv = dados_serventia(db.get_settings)
        from ri_web import data_por_extenso
        data_ext = data_por_extenso(date.fromisoformat(r["data"]))
        html = NL.texto_termo_comparecimento(
            sv=sv, reconhecimento=dict(r), parte=dict(parte),
            data_extenso=data_ext)
        with db.transaction() as con:
            NL.registrar_presenca_reconhecimento(
                con, reconhecimento_id=reconhecimento_id, parte_id=parte_id,
                data=r["data"], nome=(parte["nome"] or parte["nome_cartao"] or ""),
                documento=(parte["documento"] or parte["documento_cartao"]),
                cartao_id=parte["cartao_id"], selo=r["selo"], conteudo=html,
                oficial=r["oficial"], agora=db.now())
        audit("NT_TERMO_COMPARECIMENTO", "NT_RECONHECIMENTO", reconhecimento_id,
              {"parte_id": parte_id})
        nome_arq = (parte["nome"] or parte["nome_cartao"] or "comparecimento")
        nome_arq = re.sub(r"[^\w\-]+", "-", nome_arq.strip())[:40] or "comparecimento"
        arquivo = gerar_odt(html_para_odf(html, compacto=True),
                            titulo=f"Termo comparecimento {reconhecimento_id}")
        return Response(
            arquivo,
            mimetype="application/vnd.oasis.opendocument.text",
            headers={"Content-Disposition":
                     f'attachment; filename="termo-comparecimento-'
                     f'{reconhecimento_id}-{parte_id}-{nome_arq}.odt"'})

    # ============================================ a etiqueta na impressora térmica

    # A medida da etiqueta, e o ajuste fino que toda térmica precisa.
    #
    # POR QUE CONFIGURÁVEL, SE A SERVENTIA JÁ DISSE 100×30
    #     Porque impressora térmica nunca encaixa de primeira. O rolo vem com
    #     dois milímetros a mais de entrelinha, o driver assume uma margem que
    #     não existe, e o texto sai meio milímetro para cima — e nada disso se
    #     descobre antes de imprimir a primeira.
    #
    #     Se o ajuste morar no código, cada meio milímetro vira uma atualização
    #     do sistema. Morando nas configurações, é a serventia que acerta em
    #     dois minutos, com a página de teste ao lado.
    # AS MEDIDAS MORAM EM `etiqueta.py`, E NÃO MAIS AQUI.
    #
    #   Elas ficaram nesta função enquanto havia **uma** etiqueta na casa. Em
    #   03/09/2026 nasceu a segunda — a de registro do RCPJ/RTD, que é
    #   **90 × 40 mm** contra os 100 × 30 desta —, e aí a regra que este próprio
    #   arquivo escreveu passa a valer ao contrário: *«duas etiquetas montadas
    #   por dois caminhos divergiriam no primeiro ajuste de milímetro, e o
    #   ajuste é um só — a impressora é a mesma»*. **A tira não é a mesma**, e
    #   o que não pode divergir é a LEITURA das medidas, e não os números.
    #
    #   O E-Ofício tinha chegado a esta forma: `tbPropriedades_Etiquetas` guarda
    #   **três configurações nomeadas**, cada uma com as suas margens e o seu
    #   corpo de letra. Uma máquina, várias configurações.
    #
    #   **AS CHAVES DE GRAVAÇÃO DESTA CONTINUAM AS MESMAS** — o oficial já pode
    #   ter ajustado a tira dele no balcão, e renomeá-las apagaria o ajuste sem
    #   avisar. `etiqueta.PREFIXO_DA_CONFIGURACAO` é vazio para o reconhecimento
    #   exatamente por isso.
    ETIQUETA_PADRAO = ETQ.PADRAO_DO_RECONHECIMENTO

    # O que o QR carrega. Texto, não número — fica fora do dicionário acima.
    #
    # Ver `notas_selo.py`: o padrão é `https://selo.tjma.jus.br/#/resumo/{selo}`
    # — **o endereço da consulta daquele selo**, medido no portal em
    # 24/09/2026 e conferido em dois selos reais desta casa. A forma antiga,
    # `?selo={selo}`, abria a tela de digitar: o portal é uma aplicação que só
    # lê o que vem depois do «#».
    #
    # CONTINUA CONFIGURÁVEL porque o portal é deles: se a corregedoria mudar o
    # endereço, é um campo nesta tela — e não uma atualização do sistema. O
    # número segue impresso ao lado do QR, para quem preferir digitar.
    ETIQUETA_QR_URL = "etiqueta_qr_url"

    def medidas_da_etiqueta() -> dict:
        """As medidas desta etiqueta, com o padrão como rede. Só LÊ.

        A conta mora em `etiqueta.medidas` desde 03/09/2026 — ver o comentário
        de `ETIQUETA_PADRAO`, acima. O que ela fazia continua igual: número
        inválido nas configurações cai no padrão, porque «10 mm» digitado com a
        unidade junto não pode parar a impressão do balcão.
        """
        return ETQ.medidas(db.get_settings, ETQ.RECONHECIMENTO)

    def modelo_do_qr() -> str:
        """O que vai dentro do QR. Vazio na configuração é escolha, não falta.

        Quem apagar o campo está dizendo "quero o número cru no QR" — e o
        `notas_selo` faz exatamente isso. Por isso o padrão só entra quando a
        chave nunca foi gravada, e não sempre que vier vazia.
        """
        s = db.get_settings()
        if ETIQUETA_QR_URL not in s:
            return NSELO.MODELO_PADRAO
        return (s.get(ETIQUETA_QR_URL) or "").strip()

    # `_token_do_qr` FOI APAGADA EM 24/09/2026 — o QR passou a levar o
    # endereco da consulta pelo NUMERO, medido no portal. Ver `notas_selo`.

    def _texto_do_selo(selo: str) -> str:
        """O texto que o aparelho devolveu para aquele selo. SO LE.

        **Sai de `sd_selos`, o razao dos selos** — nao se remonta aqui o que o
        selador escreveu: o valor impresso no papel tem de ser o que o selo
        declara, e nao uma conta parecida feita depois. Selo que a casa
        digitou a mao pode nao ter texto, e ai a etiqueta sai sem a linha.
        """
        if not selo:
            return ""
        try:
            with db.connect() as con:
                con.row_factory = sqlite3.Row
                linha = con.execute(
                    "SELECT texto FROM sd_selos WHERE numero=?", (selo,)).fetchone()
        except sqlite3.Error:
            # SO A TABELA QUE FALTA SE PERDOA, e devolvendo vazio — que aqui
            # quer dizer «nao ha linha», e nao «os valores sao zero».
            return ""
        return str((linha["texto"] if linha else "") or "").strip()

    def dados_da_etiqueta(r) -> dict:
        """Tudo o que a etiqueta imprime, montado num lugar só."""
        sv = dados_serventia(db.get_settings)
        selo = (r["selo"] or "").strip()
        codigo = (r["codigo_seguranca"] or "").strip()
        medidas = medidas_da_etiqueta()
        # O TOKEN DO TJMA VEM PRIMEIRO, quando existe — medido em 28/08/2026
        # decodificando um QR real do E-Ofício.
        #
        #   «QR code do selo nas etiquetas impressas direciona ao site genérico
        #   de consulta do selo. Se possível, poderia já direcionar a uma
        #   consulta ao próprio selo da etiqueta.» — o oficial, 27/08/2026.
        #
        #   Ele tem razão no problema e a solução não é a que parecia: **o QR
        #   do TJMA não carrega URL nenhuma**. Ele carrega um token de 24
        #   caracteres, que o portal resolve. Decodificado de uma das 4.392
        #   imagens do E-Ofício: `MDGaPtZuqUKD4FtmC82CK5al`, e ele é exatamente
        #   o `strvalorQRCode` que o acervo guarda — em 25.642 dos 26.130
        #   selos.
        #
        #   **E A CONCLUSÃO TIRADA DALI CAIU EM 24/09/2026 — a medição
        #   acima fica.** Estava escrito aqui que «inventar um link
        #   `?selo=NNN` nunca ia funcionar: o portal não procura pelo
        #   número, procura pelo token». **Ele procura pelo número**, e
        #   isso se mediu no próprio portal, em dois selos reais desta
        #   casa: `#/resumo/<SELO>` abre a consulta pronta, com o ato, o
        #   cartório, as partes e os valores.
        #
        #   E havia um argumento que nem dependia do portal: **token cru
        #   dentro de um QR não é link** — a câmera lê vinte e quatro
        #   caracteres e não tem o que abrir. O QR do E-Ofício nunca levou
        #   ninguém à consulta; ele servia ao leitor do próprio Tribunal.
        #
        #   O token SAIU do caminho do QR, e `token_do_qr` foi apagada.
        #   O que a linha abaixo monta é o endereço da consulta.
        marca = NSELO.marca_do_selo(
            selo, modelo=modelo_do_qr(), codigo=codigo,
            tamanho_mm=float(medidas["etiqueta_qr_mm"]))
        return {
            # espaço após a vírgula no fecho montado pelo sistema
            # («CIDADE-UF, dd/mm/aaaa»); importado do E-Oficio fica igual.
            "texto": MOTOR_ETQ.texto_da_etiqueta_motor(
                r["texto"], sv["ri_cidade"], sv["ri_uf"], r["data"]),
            "selo": selo,
            "codigo": codigo,
            "oficial": (r["oficial"] or "").strip(),
            "funcao": (r["oficial_funcao"] or "").strip(),
            "quantidade": r["quantidade"] or 1,
            # Sem selo nao ha QR: um QR que aponta para uma consulta vazia e
            # pior do que nenhum, porque parece conferivel e nao e.
            "qr": marca["qr"],
            "qr_texto": marca["qr_texto"],
            "qr_possivel": marca["qr_possivel"],
            # O QUE O SELO DECLARA, impresso na etiqueta — pedido do oficial em
            # 01/09/2026. A régua é a de `selo_no_papel`, a mesma da certidão
            # do RCPN: uma só para os papéis das seis atribuições.
            "valores": SNPAPEL.linha_de_valores(_texto_do_selo(selo)),
        }

    @app.route("/notas/reconhecimento/<int:reconhecimento_id>/etiqueta")
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_reconhecimento_etiqueta(reconhecimento_id):
        """A etiqueta, no tamanho exato, pronta para a janela de impressão.

        POR QUE HTML E NÃO ESC/POS
            Impressora térmica de etiqueta se instala no Windows como impressora
            comum. Mandar bytes crus para a porta exigiria um programa rodando
            na máquina do balcão — e um programa a mais para instalar, manter e
            consertar em cada computador.

            Uma página com `@page { size: 100mm 30mm; margin: 0 }` sai pela
            mesma impressora, pelo mesmo driver, sem instalar nada. E funciona
            igual na Elgin, na Bematech e na Argox, que é mais do que se pode
            dizer de qualquer comando ESC/POS.

        A CONTAGEM SOBE AQUI, e não num botão separado de "marcar impressa".
            Botão que a pessoa tem de lembrar de apertar é botão que não é
            apertado. Abrir esta tela é a única forma de imprimir; contar aqui
            é contar onde a coisa acontece.
        """
        r = q1("SELECT * FROM nt_reconhecimentos WHERE id=?", (reconhecimento_id,))
        if not r:
            abort(404)
        if r["cancelado"]:
            # Etiqueta de ato cancelado colada num documento é o ato valendo
            # no mundo depois de ter sido desfeito no livro.
            flash("Este reconhecimento está cancelado — não se imprime etiqueta "
                  "de ato cancelado.", "danger")
            return redirect(url_for("notas_reconhecimento_ver",
                                    reconhecimento_id=reconhecimento_id))

        with db.transaction() as con:
            con.execute("""UPDATE nt_reconhecimentos
                           SET etiqueta_impressa_em=?,
                               etiqueta_impressoes=COALESCE(etiqueta_impressoes,0)+1
                           WHERE id=?""", (db.now(), reconhecimento_id))
        vez = (r["etiqueta_impressoes"] or 0) + 1
        audit("NT_ETIQUETA_IMPRESSA", "NT_RECONHECIMENTO", reconhecimento_id,
              {"vez": vez, "selo": r["selo"]})

        return render_template("notas_etiqueta.html", e=dados_da_etiqueta(r),
                               m=medidas_da_etiqueta(), r=dict(r), vez=vez,
                               voltar=url_for("notas_reconhecimento_ver",
                                              reconhecimento_id=reconhecimento_id))

    @app.route("/notas/autenticacao/<int:autenticacao_id>/etiqueta")
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_autenticacao_etiqueta(autenticacao_id):
        """A etiqueta da autenticacao de copia, no mesmo formato da da firma.

        «Gera o selo de autenticacao de copia, mas nao da opcao de imprimir a
        etiqueta» — relatado pelo oficial em 27/08/2026.

        A MAQUINA DA ETIQUETA JA EXISTIA INTEIRA e servia so o reconhecimento.
        Reaproveita-la e o certo: duas etiquetas montadas por dois caminhos
        divergiriam no primeiro ajuste de milimetro, e o ajuste e um so — a
        impressora e a mesma.

        A CONTAGEM SOBE AQUI, e nao num botao de «marcar impressa»: abrir esta
        tela e a unica forma de imprimir, e contar onde a coisa acontece e o
        que faz a segunda via aparecer na conferencia.
        """
        r = q1("SELECT * FROM nt_autenticacoes WHERE id=?", (autenticacao_id,))
        if not r:
            abort(404)
        if r["cancelado"]:
            flash("Esta autenticação está cancelada — não se imprime etiqueta "
                  "de ato cancelado.", "danger")
            return redirect(url_for("notas_autenticacao"))

        with db.transaction() as con:
            con.execute("""UPDATE nt_autenticacoes
                           SET etiqueta_impressa_em=?,
                               etiqueta_impressoes=COALESCE(etiqueta_impressoes,0)+1
                           WHERE id=?""", (db.now(), autenticacao_id))
        vez = (r["etiqueta_impressoes"] or 0) + 1
        audit("NT_ETIQUETA_IMPRESSA", "NT_AUTENTICACAO", autenticacao_id,
              {"vez": vez, "selo": r["selo"]})

        # A AUTENTICACAO NAO TEM `quantidade` NEM `codigo_seguranca`: a
        # etiqueta e por FOLHA, e a quantidade dela chama-se `folhas`. O resto
        # do envelope da etiqueta e igual, e por isso a montagem e a mesma.
        dados = dict(r)
        dados["quantidade"] = r["folhas"] or 1
        dados["codigo_seguranca"] = None
        return render_template("notas_etiqueta.html",
                               e=dados_da_etiqueta(dados),
                               m=medidas_da_etiqueta(), r=dados, vez=vez,
                               voltar=url_for("notas_autenticacao"))

    @app.route("/notas/etiqueta/ajuste", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_etiqueta_ajuste():
        """Acertar o encaixe na impressora — com régua, e sem gastar o rolo.

        A página de teste desenha a borda da etiqueta e uma régua em
        milímetros. Imprimindo numa folha comum e pondo a etiqueta em cima, dá
        para ver o quanto está fora antes de estragar uma tira inteira.
        """
        if request.method == "POST":
            # CAMPO QUE NÃO VEIO FICA COMO ESTÁ — não vira erro nem zero.
            #
            #   Antes, toda medida era lida com `request.form.get(chave) or ""`
            #   e passada ao `float()`. Um campo ausente virava string vazia,
            #   o `float("")` levantava, e a tela recusava a gravação INTEIRA
            #   dizendo que "" não é número — sem dizer de qual campo.
            #
            #   Isso não é hipótese: aconteceu ao acrescentar o tamanho do QR.
            #   Os formulários já abertos no navegador do balcão não tinham o
            #   campo novo, e passaram a não conseguir salvar nada. Toda vez
            #   que uma medida for acrescentada aqui, o mesmo aconteceria.
            #
            #   Ausente é "não mexi nisso". Presente e inválido é erro — e aí
            #   a mensagem diz qual campo é.
            novo = {}
            for chave in ETIQUETA_PADRAO:
                if chave not in request.form:
                    continue
                bruto = (request.form.get(chave) or "").replace(",", ".").strip()
                try:
                    float(bruto)
                except ValueError:
                    flash(f"'{bruto}' não é um número — corrija {chave}.", "danger")
                    return redirect(url_for("notas_etiqueta_ajuste"))
                novo[chave] = bruto
            if ETIQUETA_QR_URL in request.form:
                novo[ETIQUETA_QR_URL] = (request.form.get(ETIQUETA_QR_URL) or "").strip()
            if not novo:
                flash("Nenhuma medida foi enviada.", "warning")
                return redirect(url_for("notas_etiqueta_ajuste"))
            db.set_settings(novo)
            audit("NT_ETIQUETA_AJUSTADA", None, None, novo)
            flash("Medidas guardadas. Imprima a página de teste e confira.", "success")
            return redirect(url_for("notas_etiqueta_ajuste"))

        sv = dados_serventia(db.get_settings)
        medidas = medidas_da_etiqueta()
        selo_exemplo = "RECFIR000000D0XB4FK298AWP401"
        qr_texto = NSELO.conteudo(modelo_do_qr(), selo_exemplo,
                                  "A1C594FCA5921EE228376E476DA45E")
        exemplo = {
            "texto": MOTOR_ETQ.texto_da_etiqueta_motor(
                "RECONHEÇO POR SEMELHANÇA A FIRMA DE MARIA DA SILVA SANTOS. DOU FÉ.",
                sv["ri_cidade"], sv["ri_uf"], date.today().isoformat()),
            "selo": selo_exemplo,
            "codigo": "A1C594FCA5921EE228376E476DA45E",
            "oficial": usuario_nome(), "funcao": usuario_funcao(), "quantidade": 1,
            "qr": NSELO.svg(qr_texto, medidas["etiqueta_qr_mm"]),
            "qr_texto": qr_texto,
            "qr_possivel": NSELO.disponivel(),
            # O EXEMPLO MOSTRA A LINHA DE VALORES, senao o oficial ajusta o
            # tamanho da tira sem ver justamente o que mais estoura nela.
            # Os numeros sao os de um reconhecimento real desta casa, de
            # 06/12/2021 — item 13.17.4, por semelhanca.
            "valores": ("Total R$ 18,11 Emol R$ 16,31 FERC R$ 0,50 "
                        "FEMP R$ 0,65 FADEP R$ 0,65"),
        }
        return render_template("notas_etiqueta_ajuste.html", m=medidas,
                               e=exemplo, padrao=ETIQUETA_PADRAO,
                               qr_url=modelo_do_qr(),
                               qr_url_padrao=NSELO.MODELO_PADRAO,
                               qr_campo=ETIQUETA_QR_URL,
                               portal=NSELO.PORTAL_TJMA)

    @app.route("/notas/reconhecimentos")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_reconhecimentos():
        busca = (request.args.get("busca") or "").strip()
        especie = (request.args.get("especie") or "").strip().upper()
        pagina = max(1, int(request.args.get("pagina") or 1))
        onde, params = ["1=1"], []
        if especie in ESPECIES_RECONHECIMENTO:
            onde.append("r.especie=?")
            params.append(especie)
        if busca:
            onde.append("""(r.selo LIKE ? OR EXISTS (
                             SELECT 1 FROM nt_reconhecimento_partes p
                             JOIN nt_cartoes c ON c.id = p.cartao_id
                             WHERE p.reconhecimento_id = r.id AND c.nome_norm LIKE ?))""")
            params += [f"%{busca.upper()}%", f"%{NP.normalizar(busca)}%"]
        filtro = " AND ".join(onde)
        total = q1(f"SELECT COUNT(*) n FROM nt_reconhecimentos r WHERE {filtro}", params)["n"]
        rows = q(f"""SELECT r.*, (SELECT GROUP_CONCAT(c.nome, ' / ')
                                  FROM nt_reconhecimento_partes p
                                  JOIN nt_cartoes c ON c.id = p.cartao_id
                                  WHERE p.reconhecimento_id = r.id) nomes
                     FROM nt_reconhecimentos r WHERE {filtro}
                     ORDER BY r.data DESC, r.id DESC LIMIT ? OFFSET ?""",
                 params + [POR_PAGINA, (pagina - 1) * POR_PAGINA])
        return render_template("notas_reconhecimentos.html", rows=rows, busca=busca,
                               especie=especie, total=total, pagina=pagina,
                               paginas=max(1, (total + POR_PAGINA - 1) // POR_PAGINA),
                               ESPECIES=ESPECIES_RECONHECIMENTO)

    # =================================================== autenticacao

    @app.route("/notas/autenticacao", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_autenticacao():
        if request.method == "POST" and request.form.get("acao") == "autenticar":
            try:
                folhas = max(1, int(request.form.get("folhas") or 1))
            except ValueError:
                folhas = 1
            tipo = (request.form.get("tipo") or "PADRAO").upper()
            if tipo not in TIPOS_AUTENTICACAO:
                tipo = "PADRAO"
            with db.transaction() as con:
                cur = con.execute(
                    """INSERT INTO nt_autenticacoes
                       (data, hora, tipo, servico_codigo, folhas, documento_descricao,
                        documento_tipo, apresentante, apresentante_documento, texto,
                        oficial, oficial_funcao, origem, criado_em)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'MANUAL', ?)""",
                    (date.today().isoformat(), datetime.now().strftime("%H:%M"), tipo,
                     SERVICOS["AUTENTICACAO"], folhas,
                     (request.form.get("documento_descricao") or "").strip() or None,
                     (request.form.get("documento_tipo") or "").strip() or None,
                     (request.form.get("apresentante") or "").strip() or None,
                     NP.so_digitos(request.form.get("apresentante_documento")) or None,
                     texto_autenticacao(tipo), usuario_nome(), usuario_funcao(), db.now()))
                aid = int(cur.lastrowid)
            # UM SELO POR FOLHA — o item 13.18 e por pagina, e o E-Oficio
            # selava uma vez por folha: 3.539 autenticacoes, todas de uma
            # folha, 3.539 selos distintos.
            selado = selar_simples("nt_autenticacoes", aid,
                                   servico=SERVICOS["AUTENTICACAO"],
                                   quantas=folhas)
            motivo_selo = motivo_da_falha_do_selo(selado)
            if motivo_selo:
                with db.transaction() as con:
                    con.execute("DELETE FROM nt_autenticacoes WHERE id=?", (aid,))
                audit("NT_AUTENTICACAO_NAO_LAVRADA_SELO_FALHOU",
                      "NT_AUTENTICACAO", aid,
                      {"tipo": tipo, "folhas": folhas, "motivo": motivo_selo})
                flash("Autenticação NÃO lavrada: o selo não saiu. "
                      f"Motivo: {motivo_selo}. Corrija o problema do "
                      "selo e lavre de novo — o ato fica suspenso até o selo "
                      "sair (relato #77).",
                      "danger")
                return redirect(url_for("notas_autenticacao"))
            audit("NT_AUTENTICACAO", "NT_AUTENTICACAO", aid,
                  {"tipo": tipo, "folhas": folhas})
            flash(f"Autenticação nº {aid} — {folhas} folha(s).{selado}",
                  "warning" if motivo_selo else "success")
            return redirect(url_for("notas_autenticacao"))

        hoje = q1("""SELECT COUNT(*) n, COALESCE(SUM(folhas),0) folhas
                     FROM nt_autenticacoes WHERE data=? AND cancelado=0""",
                  (date.today().isoformat(),))
        ultimas = q("""SELECT * FROM nt_autenticacoes ORDER BY id DESC LIMIT 15""")
        return render_template("notas_autenticacao.html", hoje=hoje, ultimas=ultimas,
                               preco=emolumento_do_servico(SERVICOS["AUTENTICACAO"]),
                               TIPOS=TIPOS_AUTENTICACAO)


    @app.route("/notas/cartoes/<int:cartao_id>/selar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_cartao_selar(cartao_id):
        """Sela cartao pendente — so humano. Robo recebe 403."""
        import selo_robo as SR
        if SR.exige_humano_para_selar():
            abort(403)
        c = q1("SELECT * FROM nt_cartoes WHERE id=?", (cartao_id,))
        if not c:
            abort(404)
        if (c["selo_abertura"] or "").strip():
            flash(f"Cartão nº {cartao_id} já tem selo: {c['selo_abertura']}.", "warning")
            return redirect(url_for("notas_cartao", cartao_id=cartao_id))
        selado = selar_simples(
            "nt_cartoes", cartao_id, servico=SERVICOS["CARTAO"],
            partes=[{"nome": c["nome"], "documento": c["documento"]}])
        motivo = motivo_da_falha_do_selo(selado)
        if motivo:
            flash(f"Não selou o cartão: {motivo}", "danger")
        else:
            audit("NT_CARTAO_SELADO", "NT_CARTAO", cartao_id, {"via": "botao_selar"})
            flash(f"Cartão nº {cartao_id} selado.{selado}", "success")
        return redirect(url_for("notas_cartao", cartao_id=cartao_id))

    @app.route("/notas/reconhecimento/<int:reconhecimento_id>/selar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_reconhecimento_selar(reconhecimento_id):
        """Sela reconhecimento pendente via aparelho — so humano."""
        import selo_robo as SR
        if SR.exige_humano_para_selar():
            abort(403)
        r = q1("SELECT * FROM nt_reconhecimentos WHERE id=?", (reconhecimento_id,))
        if not r:
            abort(404)
        if (r["selo"] or "").strip():
            flash(f"Reconhecimento nº {reconhecimento_id} já tem selo.", "warning")
            return redirect(url_for("notas_reconhecimento_ver",
                                    reconhecimento_id=reconhecimento_id))
        partes = q("""SELECT id parte_id, nome, documento
                        FROM nt_reconhecimento_partes
                       WHERE reconhecimento_id=? ORDER BY id""",
                   (reconhecimento_id,))
        selado = selar_reconhecimento(
            reconhecimento_id,
            servico=int(r["servico_codigo"] or SERVICOS["SEMELHANCA"]),
            especie=r["especie"] or "SEMELHANCA",
            partes=[{"parte_id": p["parte_id"], "nome": p["nome"],
                     "documento": p["documento"]} for p in partes])
        if not selado.get("ok") and not selado.get("selos"):
            flash(f"Não selou: {selado.get('motivo') or 'falha'}", "danger")
        else:
            audit("NT_RECONHECIMENTO_SELADO", "NT_RECONHECIMENTO",
                  reconhecimento_id, {"via": "botao_selar",
                                      "selos": selado.get("selos")})
            flash(f"Reconhecimento nº {reconhecimento_id} selado."
                  f"{selado.get('mensagem') or ''}",
                  "success" if selado.get("ok") else "warning")
        return redirect(url_for("notas_reconhecimento_ver",
                                reconhecimento_id=reconhecimento_id))

    @app.route("/notas/autenticacao/<int:autenticacao_id>/selar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_autenticacao_selar(autenticacao_id):
        """Sela autenticacao pendente via aparelho — so humano."""
        import selo_robo as SR
        if SR.exige_humano_para_selar():
            abort(403)
        a = q1("SELECT * FROM nt_autenticacoes WHERE id=?", (autenticacao_id,))
        if not a:
            abort(404)
        if (a["selo"] or "").strip():
            flash(f"Autenticação nº {autenticacao_id} já tem selo.", "warning")
            return redirect(url_for("notas_autenticacao"))
        folhas = int(a["folhas"] or 1)
        selado = selar_simples("nt_autenticacoes", autenticacao_id,
                               servico=SERVICOS["AUTENTICACAO"], quantas=folhas)
        motivo = motivo_da_falha_do_selo(selado)
        if motivo:
            flash(f"Não selou a autenticação: {motivo}", "danger")
        else:
            audit("NT_AUTENTICACAO_SELADA_APARELHO", "NT_AUTENTICACAO",
                  autenticacao_id, {"via": "botao_selar"})
            flash(f"Autenticação nº {autenticacao_id} selada.{selado}", "success")
        return redirect(url_for("notas_autenticacao"))


    @app.route("/notas/autenticacao/<int:autenticacao_id>/selo", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_autenticacao_selo(autenticacao_id):
        selo = (request.form.get("selo") or "").strip().upper()
        if not selo:
            flash("Informe o selo.", "danger")
        else:
            ja = q1("SELECT id FROM nt_autenticacoes WHERE selo=? AND id<>?",
                    (selo, autenticacao_id))
            if ja:
                flash(f"Este selo já está na autenticação nº {ja['id']}.", "danger")
            else:
                with db.transaction() as con:
                    con.execute("UPDATE nt_autenticacoes SET selo=? WHERE id=?",
                                (selo, autenticacao_id))
                audit("NT_AUTENTICACAO_SELADA", "NT_AUTENTICACAO", autenticacao_id,
                      {"selo": selo})
                flash("Selo registrado.", "success")
        return redirect(url_for("notas_autenticacao"))

    # =================================================== livros

    def _sv():
        return dados_serventia(db.get_settings)

    def _hoje_extenso() -> str:
        """A data de hoje por extenso, como o resto do sistema escreve.

        Import local, no mesmo molde do traslado: `ri_web` importa este módulo
        de volta, e importar no topo fecharia o ciclo.
        """
        from ri_web import data_por_extenso
        return data_por_extenso(date.today())

    @app.route("/notas/livros", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_livros():
        """Abertura e encerramento de livro, e a conferência de cada um.

        O termo de abertura e o de encerramento não são formalidade: são o que
        diz o que o livro é, quantas folhas tem, quais foram usadas e quais
        ficaram inutilizadas — Lei 8.935/1994, art. 30, I, e o Código de Normas
        do Foro Extrajudicial do Maranhão (Prov. TJMA 28/2026), Seção III do
        Capítulo IV, "Dos Livros e da sua Escrituração", arts. 788 a 797.

        Desde a versão 3.3.8 os dois textos são ESCRITOS PELO SISTEMA quando o
        campo vem em branco. Antes o de abertura era opcional e ninguém o
        preenchia — o livro nascia sem identidade e nada avisava.
        """
        if request.method == "POST":
            acao = request.form.get("acao")
            if somente_leitura():
                flash("Perfil de auditoria não abre nem encerra livro.", "danger")
                return redirect(url_for("notas_livros"))
            if acao == "abrir":
                tipo = (request.form.get("tipo") or "").upper()
                if tipo not in TIPOS_LIVRO:
                    flash("Escolha o tipo do livro.", "danger")
                    return redirect(url_for("notas_livros"))
                try:
                    with db.transaction() as con:
                        lid = NL.abrir_livro(
                            con, tipo, _sv(), db.now(), _hoje_extenso(),
                            usuario=usuario_nome(),
                            numero=request.form.get("numero"),
                            folhas=NL.inteiro(request.form.get("folhas")),
                            abertura=(request.form.get("abertura") or "").strip() or None,
                            complemento=request.form.get("complemento") or "",
                            termo=request.form.get("termo_abertura"))
                except NL.LivroError as erro:
                    flash(str(erro), "danger")
                    return redirect(url_for("notas_livros"))
                except sqlite3.IntegrityError:
                    # Dois balcões abrindo o mesmo livro no mesmo instante. O
                    # UNIQUE(tipo, numero, complemento) é a rede; antes desta
                    # versão o IntegrityError subia como HTTP 500 na cara do
                    # escrevente.
                    flash("Esse livro acabou de ser aberto por outra pessoa.",
                          "warning")
                    return redirect(url_for("notas_livros"))
                audit("NT_LIVRO_ABERTO", "NT_LIVRO", lid, {"tipo": tipo})
                flash(f"{TIPOS_LIVRO[tipo]} aberto, com termo de abertura.",
                      "success")

            elif acao == "encerrar":
                lid = NL.inteiro(request.form.get("livro_id")) or 0
                try:
                    with db.transaction() as con:
                        feito = NL.encerrar_livro(
                            con, lid, _sv(), db.now(), _hoje_extenso(),
                            usuario=usuario_nome(),
                            motivo=request.form.get("motivo"),
                            termo=request.form.get("termo_encerramento"))
                except NL.LivroError as erro:
                    flash(str(erro), "danger")
                    return redirect(url_for("notas_livros"))
                audit("NT_LIVRO_ENCERRADO", "NT_LIVRO", lid, feito)
                aviso = (f" Folhas {feito['folhas_inutilizadas']} declaradas "
                         f"inutilizadas no termo." if feito["folhas_inutilizadas"]
                         else "")
                flash(f"Livro nº {feito['numero']} encerrado.{aviso}", "success")

            elif acao == "fixar_termo":
                serie = (request.form.get("serie") or "").upper()
                try:
                    with db.transaction() as con:
                        NL.fixar_termo(con, serie,
                                       NL.inteiro(request.form.get("proximo")) or 0,
                                       usuario_nome(),
                                       request.form.get("observacao"), db.now())
                except NL.LivroError as erro:
                    flash(str(erro), "danger")
                    return redirect(url_for("notas_livros"))
                audit("NT_TERMO_FIXADO", "NT_LIVRO", None,
                      {"serie": serie, "proximo": request.form.get("proximo")})
                flash(f"Numeração de termo da série {serie} corrigida.", "success")

            return redirect(url_for("notas_livros"))

        # ESTA TELA SO LE.
        #
        # A primeira versao abria uma transacao aqui para reconciliar
        # `folha_atual` antes de mostrar. Transacao no GET e `BEGIN IMMEDIATE`:
        # com outro balcao lavrando, a tela ficava dez segundos no
        # `busy_timeout` e devolvia 500 — numa pagina que o usuario so queria
        # olhar. E o AUDITOR, que e perfil de leitura, gravava no banco ao
        # abri-la. A conta da folha corrente e a mesma, feita por
        # `NL.folha_livre`, que nao grava.
        livros = []
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            for r in con.execute(
                    """SELECT l.*,
                         (SELECT COUNT(*) FROM nt_atos a WHERE a.livro_id = l.id) atos
                       FROM nt_livros l
                       ORDER BY l.encerrado, l.tipo, CAST(l.numero AS INTEGER)"""):
                d = dict(r)
                inicio = int(d.get("folha_inicial") or 1)
                cap = NL.capacidade(r)
                atual = (int(d.get("folha_atual") or inicio) if d.get("encerrado")
                         else NL.folha_livre(con, r))
                d["capacidade"] = cap
                d["folha_atual"] = atual
                d["ultima_folha"] = inicio + cap - 1
                d["usadas"] = max(0, atual - inicio)
                d["restam"] = max(0, inicio + cap - atual)
                d["quase_cheio"] = (not d.get("encerrado")) and 0 < d["restam"] <= 10
                d["sem_capacidade"] = not NL.inteiro(d.get("folhas"))
                livros.append(d)

            series = []
            for serie in sorted(set(NL.LIVRO_DO_ATO.values())):
                linha = con.execute("SELECT * FROM nt_termos WHERE serie=?",
                                    (serie,)).fetchone()
                series.append({
                    "serie": serie,
                    "nome": NL.NOME_DA_SERIE.get(serie, serie),
                    "proximo": (int(linha["proximo"]) if linha
                                else NL.proximo_termo(con, serie, consumir=False)),
                    "maior_em_uso": int(linha["maior_em_uso"] or 0) if linha else 0,
                    "observacao": linha["observacao"] if linha else None,
                })

        return render_template("notas_livros.html", livros=livros, series=series,
                               TIPOS_LIVRO=TIPOS_LIVRO,
                               capacidade_padrao=NL.CAPACIDADE_PADRAO)

    @app.route("/notas/livros/<int:livro_id>/termo/<qual>")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_livro_termo(livro_id, qual):
        """O termo de abertura ou de encerramento, em .odt, para colar no livro.

        Termo que só existe dentro do banco não serve: o livro de papel é que
        precisa dele na primeira e na última folha.
        """
        if qual not in ("abertura", "encerramento"):
            abort(404)
        livro = q1("SELECT * FROM nt_livros WHERE id=?", (livro_id,))
        if not livro:
            abort(404)
        texto = (livro[f"termo_{qual}"] or "").strip()
        if not texto:
            flash(f"Este livro ainda não tem termo de {qual}.", "warning")
            return redirect(url_for("notas_livros"))
        sv = _sv()
        html = (f'<p align="center"><b>{sv["unit_name"]}</b></p>'
                f'<p align="center">{sv["serventia_titulo"]}: '
                f'{sv["serventia_titular"]}</p>'
                f'<p align="center">CNS {sv["ri_cns"]} — {sv["endereco_completo"]}</p>'
                f'<p></p><p>{texto}</p><p></p><p></p>'
                f'<p align="center">_________________________________</p>'
                f'<p align="center">{sv["serventia_titular"]}</p>'
                f'<p align="center">{sv["serventia_titulo"]}</p>')
        arquivo = gerar_odt(html_para_odf(html),
                            titulo=f"Termo de {qual} — livro {livro['numero']}")
        audit("NT_LIVRO_TERMO", "NT_LIVRO", livro_id, {"qual": qual})
        nome = f"termo-{qual}-livro-{livro['numero']}.odt"
        return Response(arquivo, mimetype="application/vnd.oasis.opendocument.text",
                        headers={"Content-Disposition":
                                 f'attachment; filename="{nome}"'})

    @app.route("/notas/anotacoes/pendentes")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_anotacoes_pendentes():
        """Revogações e substabelecimentos que ainda não foram à margem.

        É a lista que responde à correição: toda revogação lavrada foi anotada
        na margem da procuração que ela revoga? Enquanto não for, aqui está o
        que falta, e por quê.
        """
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            faltando = NA.pendentes(con)
        return render_template("notas_anotacoes_pendentes.html",
                               faltando=faltando, TIPOS_ATO=TIPOS_ATO)

    def _odt_inutilizacao(faces, serie, numero, titulo):
        """As faces inutilizadas, uma por página, prontas para imprimir.

        Sai em .odt como o resto do sistema. Cada face leva o traço, o dizer e
        a linha de assinatura — o escrevente imprime sobre a folha do livro e
        não risca nada à mão.
        """
        sv = _sv()
        extenso = _hoje_extenso()
        texto = NI.dizer(faces, serie, numero, sv, extenso)
        paginas = [NI.html_da_face(f, serie, numero, sv, extenso, texto)
                   for f in faces]
        # Uma face por página. O `ri_odt` não tem estilo de quebra, então as
        # páginas são separadas pelo próprio corpo — o LibreOffice quebra ao
        # encher, e cada face tem altura de folha inteira por causa do traço.
        arquivo = gerar_odt(html_para_odf("".join(paginas)), titulo=titulo)
        return Response(
            arquivo, mimetype="application/vnd.oasis.opendocument.text",
            headers={"Content-Disposition":
                     f'attachment; filename="{safe(titulo)}.odt"'})

    def safe(nome: str) -> str:
        return "".join(c if c.isalnum() or c in "-_" else "-"
                       for c in nome.lower()).strip("-")[:60] or "documento"

    @app.route("/notas/atos/<int:ato_id>/inutilizacao")
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_ato_inutilizacao(ato_id):
        """O verso que sobrou, impresso já inutilizado.

        O ato começa em folha nova e ocupa folhas inteiras. Terminando o texto
        na frente da última, o verso fica sem uso — e não pode ficar em branco:
        art. 795, § 2º do Código de Normas, escrituração seguida, sem claros.
        Em vez de riscar à mão, imprime-se a face já riscada.
        """
        a = q1("SELECT * FROM nt_atos WHERE id=?", (ato_id,))
        if not a:
            abort(404)
        faces = NI.faces_do_ato(a)
        if not faces:
            flash("Este ato não deixou face em branco — o texto termina no "
                  "verso da última folha.", "warning")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        audit("NT_INUTILIZACAO", "NT_ATO", ato_id, {"faces": faces})
        return _odt_inutilizacao(faces, a["serie"] or a["tipo"], a["livro"],
                                 f"Inutilizacao livro {a['livro']} folha {faces[0]}")

    @app.route("/notas/livros/<int:livro_id>/inutilizacao")
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_livro_inutilizacao(livro_id):
        """As folhas que sobraram quando o livro encerrou, já inutilizadas."""
        livro = q1("SELECT * FROM nt_livros WHERE id=?", (livro_id,))
        if not livro:
            abort(404)
        faces = NI.faces_do_livro(livro)
        if not faces:
            flash("Este livro não tem folhas em branco declaradas no termo de "
                  "encerramento.", "warning")
            return redirect(url_for("notas_livros"))
        audit("NT_INUTILIZACAO", "NT_LIVRO", livro_id, {"faces": len(faces)})
        return _odt_inutilizacao(faces, livro["tipo"], livro["numero"],
                                 f"Inutilizacao livro {livro['numero']}")

    @app.route("/notas/livros/<int:livro_id>/conferir")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_livro_conferir(livro_id):
        """As três perguntas que a correição faz ao livro.

        Folha pulada, folha repetida, termo faltando. Responder antes de o
        corregedor perguntar é toda a diferença.
        """
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            try:
                laudo = NL.conferir_livro(con, livro_id)
            except NL.LivroError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("notas_livros"))
        problemas = []
        if laudo["folhas_puladas"]:
            problemas.append("folhas puladas: " + ", ".join(laudo["folhas_puladas"]))
        if laudo["folhas_repetidas"]:
            problemas.append("folhas repetidas: "
                             + ", ".join(str(n) for n in laudo["folhas_repetidas"]))
        if laudo["termos_faltando"]:
            problemas.append("termos faltando: " + ", ".join(laudo["termos_faltando"]))
        if laudo["sem_termo_de_abertura"]:
            problemas.append("sem termo de abertura")
        if laudo["em_lavratura"]:
            problemas.append(f"{laudo['em_lavratura']} ato(s) ainda em lavratura")
        if problemas:
            flash(f"Livro {laudo['livro']}: " + "; ".join(problemas) + ".", "warning")
        else:
            flash(f"Livro {laudo['livro']}: {laudo['atos']} ato(s), numeração "
                  f"seguida, sem folha pulada nem repetida.", "success")
        return redirect(url_for("notas_livros"))

    # =================================================== atos de livro

    def _painel_da_familia(chave: str):
        """O painel é um só; a configuração decide se mostra escritura ou ata."""
        familia = NF.por_chave(chave)
        if not familia:
            abort(404)
        tipos = familia["tipos_ato"]
        marcas = ",".join("?" for _ in tipos)
        resumo = q1(
            f"""SELECT COUNT(*) total,
                       SUM(CASE WHEN situacao='EM_LAVRATURA' THEN 1 ELSE 0 END)
                           em_lavratura,
                       SUM(CASE WHEN situacao='LAVRADO' THEN 1 ELSE 0 END) lavrados,
                       SUM(CASE WHEN situacao!='EM_LAVRATURA'
                                 AND COALESCE(selo,'')='' THEN 1 ELSE 0 END)
                           sem_selo,
                       SUM(CASE WHEN COALESCE(TRIM(teor),'')='' THEN 1 ELSE 0 END)
                           sem_teor,
                       SUM(CASE WHEN NOT EXISTS (
                             SELECT 1 FROM nt_ato_partes p WHERE p.ato_id=a.id
                           ) THEN 1 ELSE 0 END) sem_partes
                  FROM nt_atos a WHERE a.tipo IN ({marcas})""", tipos)
        # sqlite3.Row itera VALORES; aqui precisamos explicitamente das chaves.
        resumo = {k: int(resumo[k] or 0) for k in resumo.keys()}  # noqa: SIM118
        resumo["documentos"] = q1(
            f"""SELECT COUNT(*) n FROM attachments x
                  JOIN nt_atos a ON a.id=x.entity_id
                 WHERE x.entity_type='NT_ATO' AND a.tipo IN ({marcas})""",
            tipos)["n"]
        recentes = q(
            f"""SELECT a.*, (SELECT GROUP_CONCAT(p.nome, ' / ')
                                FROM nt_ato_partes p WHERE p.ato_id=a.id) nomes
                  FROM nt_atos a WHERE a.tipo IN ({marcas})
                 ORDER BY a.data DESC, a.id DESC LIMIT 12""", tipos)
        marcas_modelo = ",".join("?" for _ in familia["tipos_modelo"])
        modelos = [dict(x) for x in q(
            f"""SELECT codigo, tipo, nome, fundamento FROM nt_modelos
                 WHERE ativo=1 AND tipo IN ({marcas_modelo})
                 ORDER BY nome_norm""", familia["tipos_modelo"])]
        for modelo in modelos:
            padrao = NMOD.por_codigo(modelo["codigo"]) or {}
            modelo["requisitos"] = padrao.get("requisitos", [])
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            previsao = NL.previsao(con, familia["tipo_principal"])
        return render_template(
            "notas_familia.html", familia=familia, resumo=resumo,
            recentes=recentes, modelos=modelos, previsao=previsao,
            TIPOS_ATO=TIPOS_ATO)

    @app.route("/notas/escrituras")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_escrituras():
        return _painel_da_familia("escrituras")

    @app.route("/notas/atas")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_atas():
        return _painel_da_familia("atas")

    @app.route("/notas/atos")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_atos():
        busca = (request.args.get("busca") or "").strip()
        tipo = (request.args.get("tipo") or "").strip().upper()
        familia_chave = (request.args.get("familia") or "").strip().lower()
        familia = NF.por_chave(familia_chave)
        pagina = max(1, int(request.args.get("pagina") or 1))
        livro_id = (request.args.get("livro_id") or "").strip()
        livro_q = (request.args.get("livro") or "").strip()
        folha_q = (request.args.get("folha") or "").strip()
        termo_q = (request.args.get("termo") or "").strip()
        if busca and not (livro_q and folha_q):
            par_livro, par_folha = NL.parse_livro_folha_busca(busca)
            if par_livro and par_folha:
                livro_q, folha_q = par_livro, par_folha
                busca = ""
            elif busca.isdigit() and not termo_q:
                termo_q = busca
                busca = ""
        onde, params = ["1=1"], []
        if familia:
            marcas = ",".join("?" for _ in familia["tipos_ato"])
            onde.append(f"a.tipo IN ({marcas})")
            params.extend(familia["tipos_ato"])
        elif tipo in TIPOS_ATO:
            onde.append("a.tipo=?")
            params.append(tipo)
        if livro_id.isdigit():
            onde.append("a.livro_id=?")
            params.append(int(livro_id))
        elif livro_q:
            onde.append("(a.livro=? OR EXISTS (SELECT 1 FROM nt_livros l "
                         "WHERE l.id=a.livro_id AND l.numero=?))")
            params.extend([livro_q, livro_q])
            if folha_q:
                folha_num = NL.inteiro(folha_q)
                if folha_num is not None:
                    onde.append("""(a.folha_inicial_num=? OR a.folha=? OR
                                    CAST(a.folha AS TEXT)=?)""")
                    params.extend([folha_num, folha_q, folha_q])
                else:
                    onde.append("(a.folha=? OR CAST(a.folha AS TEXT)=?)")
                    params.extend([folha_q, folha_q])
        if termo_q.isdigit():
            onde.append("a.termo=?")
            params.append(int(termo_q))
        if busca:
            onde.append("""(a.interessado LIKE ? OR a.selo LIKE ? OR
                             CAST(a.termo AS TEXT)=? OR EXISTS (
                             SELECT 1 FROM nt_ato_partes p
                             WHERE p.ato_id = a.id AND p.nome_norm LIKE ?))""")
            params += [f"%{busca}%", f"%{busca.upper()}%", busca,
                       f"%{NP.normalizar(busca)}%"]
        filtro = " AND ".join(onde)
        total = q1(f"SELECT COUNT(*) n FROM nt_atos a WHERE {filtro}", params)["n"]
        rows = q(f"""SELECT a.*, (SELECT GROUP_CONCAT(p.nome, ' / ') FROM nt_ato_partes p
                                  WHERE p.ato_id = a.id AND p.testemunha=0) nomes
                     FROM nt_atos a WHERE {filtro}
                     ORDER BY a.livro, COALESCE(a.folha_inicial_num, 0),
                              a.termo, a.data DESC, a.id DESC
                     LIMIT ? OFFSET ?""",
                 params + [POR_PAGINA, (pagina - 1) * POR_PAGINA])
        livro_ctx = None
        if livro_id.isdigit():
            livro_ctx = q1("SELECT * FROM nt_livros WHERE id=?", (int(livro_id),))
        return render_template("notas_atos.html", rows=rows, busca=busca, tipo=tipo,
                               familia=familia, familia_chave=familia_chave,
                               livro_id=livro_id, livro_q=livro_q, folha_q=folha_q,
                               termo_q=termo_q, livro_ctx=livro_ctx,
                               total=total, pagina=pagina, TIPOS_ATO=TIPOS_ATO,
                               paginas=max(1, (total + POR_PAGINA - 1) // POR_PAGINA))

    @app.route("/notas/atos/<int:ato_id>/apagar-rascunho", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_ato_apagar_rascunho(ato_id):
        """Apaga um ato EM LAVRATURA. Relato #78, 17/09/2026.

            «precisa ser possivel apagar rascunhos, direto na pagina de atos
             de livro» — Carla Exemplo Lima

        **SO O RASCUNHO SE APAGA.** Ato lavrado tem livro, folha, numero e
        selo; ele nao se apaga — cancela-se, com rastro. As quatro recusas
        daqui sao a forma das quatro do script das minutas do RI: ato que nao
        esta em lavratura, ato com selo, ato com dinheiro no caixa, e ato que
        ja foi para uma Central.

        **O TEOR VAI PARA A AUDITORIA, INTEIRO.** O ato nunca existiu no livro,
        mas o trabalho existiu: ha rascunho com 11.907 caracteres nesta casa.
        Apagar sem guardar seria perder uma tarde de escrita num clique.

        **QUEM APAGA E QUEM ABRIU, OU O OFICIAL.** O rascunho errado e de quem
        o abriu — e foi uma escrevente quem pediu isto. Trancar no ADMIN faria
        o pedido dela depender de alguem que nao esta no balcao.
        """
        a = q1("SELECT * FROM nt_atos WHERE id=?", (ato_id,))
        if not a:
            abort(404)

        def recusar(motivo: str):
            flash(f"Este ato não pode ser apagado: {motivo}", "danger")
            return redirect(url_for("notas_atos"))

        if (a["situacao"] or "").upper() != "EM_LAVRATURA":
            return recusar("ele já foi lavrado — ato no livro se cancela, com "
                           "rastro, e não se apaga.")
        if (a["selo"] or "").strip():
            return recusar("ele já tem selo. O selo foi comprado e está no "
                           "razão; fale com o oficial.")
        if a["lancamento_id"]:
            return recusar("ele já tem lançamento no caixa. Dinheiro que "
                           "entrou sai por estorno, que deixa rastro.")
        if q1("SELECT 1 FROM nt_remessa_itens WHERE ato_id=? LIMIT 1", (ato_id,)):
            return recusar("ele já foi numa remessa a uma Central.")

        eu = (usuario_nome() or "").strip().upper()
        dono = (a["lavrado_nome"] or "").strip().upper()
        if (app.extensions["usuario_papel"]() not in ("ADMIN", "MANAGER")
                and dono and eu != dono):
            return recusar(f"ele foi aberto por {a['lavrado_nome']}. Só quem "
                           f"abriu, o oficial ou o gerente podem apagá-lo.")

        partes = q1("SELECT COUNT(*) n FROM nt_ato_partes WHERE ato_id=?",
                    (ato_id,))["n"]
        # O TEOR E O QUE NAO SE REFAZ: ele vai inteiro para o rastro, ANTES de
        # a linha sumir. Nao e o ato — o ato nunca existiu no livro —, e o
        # trabalho de quem escreveu.
        audit("NT_RASCUNHO_APAGADO", "NT_ATO", ato_id,
              {"tipo": a["tipo"], "data": a["data"],
               "interessado": a["interessado"], "aberto_por": a["lavrado_nome"],
               "criado_em": a["criado_em"], "partes": partes,
               "teor": a["teor"] or "", "modelo": a["modelo_codigo"]})
        with db.transaction() as con:
            con.execute("DELETE FROM nt_ato_anotacoes WHERE ato_id=? "
                        "OR ato_relacionado_id=?", (ato_id, ato_id))
            con.execute("DELETE FROM nt_ato_partes WHERE ato_id=?", (ato_id,))
            con.execute("DELETE FROM nt_atos WHERE id=?", (ato_id,))
        flash(f"Rascunho nº {ato_id} apagado. O texto que estava nele ficou "
              f"guardado na auditoria.", "success")
        return redirect(url_for("notas_atos"))

    @app.route("/notas/atos/novo", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_ato_novo():
        """Abre o ato EM LAVRATURA. Livro, folha e termo vêm no lançamento.

        POR QUE O ATO NÃO NASCE MAIS COM FOLHA
            Folha reservada para ato que talvez não se lavre vira buraco no
            livro, e buraco em livro de notas não se explica em correição. O
            ato nasce sem livro, sem folha e sem termo; recebe os três de uma
            vez quando o teor está pronto e se sabe quantas páginas ele tem.

            Enquanto está em lavratura o ato não vai a central nenhuma: a
            separação da remessa filtra por `situacao = 'LAVRADO'`.
        """
        familia_chave = ((request.form.get("familia") if request.method == "POST"
                          else request.args.get("familia")) or "").strip().lower()
        familia = NF.por_chave(familia_chave)

        if request.method == "POST":
            tipo = (request.form.get("tipo") or "").upper()
            modelo_codigo = (request.form.get("modelo_codigo") or "").strip() or None
            modelo = q1("SELECT * FROM nt_modelos WHERE codigo=?",
                        (modelo_codigo,)) if modelo_codigo else None
            volta = ({"familia": familia_chave} if familia else {})
            if modelo_codigo and not modelo:
                flash("O modelo escolhido não existe mais ou está indisponível.",
                      "danger")
                return redirect(url_for("notas_ato_novo", **volta))
            if familia and modelo and not NF.aceita_modelo(familia, modelo["tipo"]):
                flash("O modelo escolhido não pertence a este módulo.", "danger")
                return redirect(url_for("notas_ato_novo", **volta))
            tipo_do_modelo = (NF.tipo_ato_do_modelo(modelo["tipo"])
                              if modelo else None)
            if tipo_do_modelo:
                # O modelo manda no livro correto; o navegador não consegue
                # transformar uma ata em escritura alterando o formulário.
                tipo = tipo_do_modelo
            tipos_permitidos = (familia["tipos_ato"] if familia else TIPOS_ATO)
            if tipo not in tipos_permitidos:
                flash("Escolha o tipo do ato.", "danger")
                return redirect(url_for("notas_ato_novo", **volta))
            with db.transaction() as con:
                cur = con.execute(
                    """INSERT INTO nt_atos
                       (tipo, serie, data, hora, situacao, natureza,
                        natureza_censec, modelo_codigo, interessado,
                        teor_formato, lavrado_nome, lavrado_titulo,
                        origem, criado_em)
                       VALUES (?,?,?,?, 'EM_LAVRATURA', ?,?,?,?, 'html', ?,?,
                               'MANUAL', ?)""",
                    (tipo, NL.LIVRO_DO_ATO.get(tipo),
                     (request.form.get("data") or date.today().isoformat()),
                     datetime.now().strftime("%H:%M"),
                     (modelo["nome"] if modelo else
                      (request.form.get("natureza") or "").strip() or None),
                     modelo["natureza_censec"] if modelo else None,
                     modelo_codigo,
                     (request.form.get("interessado") or "").strip() or None,
                     usuario_nome(), usuario_funcao(), db.now()))
                aid = int(cur.lastrowid)
            audit("NT_ATO_ABERTO", "NT_ATO", aid, {"tipo": tipo, "modelo": modelo_codigo})
            flash(f"{TIPOS_ATO[tipo]} aberto, em lavratura. Agora as partes e o "
                  f"teor; o livro e a folha saem no lançamento.", "success")
            return redirect(url_for("notas_ato", ato_id=aid))

        modelo_escolhido = (request.args.get("modelo") or "").strip()
        sql_modelos = "SELECT codigo, tipo, nome FROM nt_modelos WHERE ativo=1"
        params_modelos = []
        if familia:
            marcas = ",".join("?" for _ in familia["tipos_modelo"])
            sql_modelos += f" AND tipo IN ({marcas})"
            params_modelos.extend(familia["tipos_modelo"])
        modelos = [dict(x) for x in q(sql_modelos + " ORDER BY tipo, nome_norm",
                                      params_modelos)]
        for m in modelos:
            m["tipo_ato"] = NF.tipo_ato_do_modelo(m["tipo"]) or ""
        tipos_visiveis = ({k: TIPOS_ATO[k] for k in familia["tipos_ato"]}
                          if familia else TIPOS_ATO)
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            previsoes = {t: NL.previsao(con, t) for t in tipos_visiveis}
        return render_template("notas_ato_novo.html", modelos=modelos,
                               previsoes=previsoes, TIPOS_ATO=tipos_visiveis,
                               familia=familia, familia_chave=familia_chave,
                               modelo_escolhido=modelo_escolhido,
                               hoje=date.today().isoformat())

    # ------------------------------------- levar o teor para o LibreOffice
    #
    # «O teor do ato nao sai formatado e visivel como ficara completo pra quem
    # lavra… possibilitar em botao facilitado a exportacao do arquivo base e
    # permitir a importacao do arquivo odt ou docx apos a edicao, assim como
    # gerar e receber o upload do pdf assinado apos a lavratura e selo» — o
    # oficial, em 27/08/2026, quando o assunto voltou a lista de problemas pela
    # segunda vez.
    #
    # POR QUE ESTE CAMINHO, E NAO O LIBREOFFICE EMBUTIDO
    #     Embutir a suite numa tela de navegador exige um servidor de documentos
    #     ao lado — outro programa para instalar, atualizar e consertar, numa
    #     serventia com um servidor so. O proprio oficial ofereceu a
    #     alternativa, e ela e a que cabe: o escrevente edita no LibreOffice que
    #     ja esta na maquina dele.

    @app.route("/notas/atos/<int:ato_id>/teor.odt")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_ato_teor_odt(ato_id):
        """O rascunho do teor, para editar no LibreOffice. SO LE.

        NAO E O TRASLADO, e a diferenca importa. O traslado e copia fiel do que
        esta no LIVRO, e por isso so sai depois de o ato ser lancado, com livro
        e folha impressos e a assinatura do tabeliao embaixo. Este e o
        RASCUNHO: sai a qualquer momento, e o cabecalho dele diz o que ele e.

        Sair sem dizer faria alguem entregar um rascunho como se fosse
        instrumento.
        """
        a = q1("SELECT * FROM nt_atos WHERE id=?", (ato_id,))
        if not a:
            abort(404)
        nome_modelo = None
        if a["modelo_codigo"]:
            mrow = q1("SELECT nome FROM nt_modelos WHERE codigo=?",
                      (a["modelo_codigo"],))
            nome_modelo = mrow["nome"] if mrow else None
        teor_limpo = NT.teor_sem_titulos_duplicados(
            a["teor"], _titulos_para_limpar_do_teor(dict(a), nome_modelo=nome_modelo))
        paragrafos = TA.paragrafos_do_html(teor_limpo)
        if not paragrafos:
            flash("Este ato ainda não tem teor para exportar. Monte o teor "
                  "primeiro, ou escreva-o na caixa.", "warning")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        sv = _sv()
        aviso = (f'<p align="center"><b>RASCUNHO — ato {a["id"]}'
                 f'{" · " + a["natureza"] if a["natureza"] else ""}</b></p>'
                 f'<p align="center">{sv["unit_name"]}</p>'
                 f'<p align="center">Este documento é o teor em edição. Não é '
                 f'traslado nem certidão, e não vale como instrumento.</p>'
                 f'<p></p>')
        corpo = "".join(f"<p>{p}</p>" for p in paragrafos)
        arquivo = gerar_odt(html_para_odf(aviso + corpo),
                            titulo=f"Teor do ato {a['id']} (rascunho)")
        audit("NT_TEOR_EXPORTADO", "NT_ATO", ato_id,
              {"paragrafos": len(paragrafos)})
        nome = f"teor-ato-{a['id']}.odt"
        return Response(arquivo,
                        mimetype="application/vnd.oasis.opendocument.text",
                        headers={"Content-Disposition":
                                 f'attachment; filename="{nome}"'})

    @app.route("/notas/atos/<int:ato_id>/teor/importar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_ato_teor_importar(ato_id):
        """Traz de volta o teor editado no LibreOffice ou no Word. ESCREVE.

        A TELA MOSTRA O TAMANHO DA MUDANCA, E DEPOIS GRAVA. O escrevente vai
        substituir o teor de um ato: ele tem direito de ver quantos paragrafos
        entraram, quantos sairam e quantos ficaram iguais. E a mesma decisao da
        previa da ajuda — quem manda dado para fora ve o que esta mandando;
        aqui, quem traz de volta ve o que esta trazendo.

        NAO SE IMPORTA SOBRE ATO LANCADO. Ato que ja ocupa folha de livro tem
        teor que foi para o livro; trocar o texto depois faria o sistema e o
        papel divergirem, e quem confere le o papel. Correcao de ato lancado e
        RETIFICACAO, que e outro ato.
        """
        a = q1("SELECT * FROM nt_atos WHERE id=?", (ato_id,))
        if not a:
            abort(404)
        if (a["situacao"] or "") != "EM_LAVRATURA":
            flash("Este ato já foi lançado no livro — o teor dele foi para o "
                  "papel. Corrigir ato lançado é retificação, e não troca de "
                  "texto.", "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))

        enviado = request.files.get("arquivo")
        if not enviado or not enviado.filename:
            flash("Escolha o arquivo editado.", "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        try:
            paragrafos = TA.ler_documento(enviado.read(), enviado.filename)
        except TA.TeorArquivoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))

        # O AVISO DE RASCUNHO NAO VOLTA PARA DENTRO DO TEOR. Ele foi posto no
        # arquivo exportado para ninguem confundir rascunho com instrumento, e
        # trazê-lo de volta poria a frase «isto e um rascunho» dentro do ato.
        # O CABEÇALHO SE RECONHECE PELO TEXTO, E NÃO PELA MARCAÇÃO.
        #
        #   Ele sai em NEGRITO no arquivo — e desde 28/08/2026 o negrito volta,
        #   o que é o ponto. Então o parágrafo que volta é
        #   `<b>RASCUNHO — ato 12</b>`, e comparar com o texto cru deixava o
        #   aviso «isto é um rascunho» entrar dentro do ato.
        #
        #   Quem compara tira as marcas antes; o parágrafo que FICA continua
        #   com elas.
        def _so_texto(p: str) -> str:
            return re.sub(r"</?[biu]>", "", p).strip()

        cabecalho = (f"RASCUNHO —", _sv()["unit_name"],
                     "Este documento é o teor em edição")
        while paragrafos and any(
                _so_texto(paragrafos[0]).startswith(x) for x in cabecalho):
            paragrafos.pop(0)
        if not paragrafos:
            flash("O arquivo só tinha o cabeçalho de rascunho, e nenhum teor.",
                  "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))

        antes = TA.paragrafos_do_html(a["teor"])
        mudanca = TA.conferir_a_volta(antes, paragrafos)
        with db.transaction() as con:
            con.execute(
                "UPDATE nt_atos SET teor=?, teor_formato='html' WHERE id=?",
                (TA.html_dos_paragrafos(paragrafos), ato_id))
        audit("NT_TEOR_IMPORTADO", "NT_ATO", ato_id, mudanca)
        flash(f"Teor trazido do arquivo: {mudanca['paragrafos_depois']} "
              f"parágrafo(s), contra {mudanca['paragrafos_antes']} que havia. "
              f"{mudanca['iguais']} ficaram iguais.", "success")
        return redirect(url_for("notas_ato", ato_id=ato_id))

    @app.route("/notas/atos/<int:ato_id>/assinado", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_ato_pdf_assinado(ato_id):
        """Recebe o PDF assinado do ato lavrado. ESCREVE.

        «Gerar e receber o upload do pdf assinado apos a lavratura e selo» — o
        oficial. O PDF assinado e a prova de que o ato foi assinado por quem
        devia, e ele nao cabe no teor: e arquivo, e vai para os anexos, com
        sha256, como toda evidencia desta casa.

        SO DEPOIS DE LANCADO. PDF assinado de ato que ainda esta em lavratura e
        assinatura de coisa que ainda pode mudar.
        """
        a = q1("SELECT * FROM nt_atos WHERE id=?", (ato_id,))
        if not a:
            abort(404)
        if (a["situacao"] or "") == "EM_LAVRATURA":
            flash("Este ato ainda está em lavratura. O PDF assinado entra "
                  "depois de o ato ser lançado no livro.", "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        enviado = request.files.get("arquivo")
        if not enviado or not enviado.filename:
            flash("Escolha o PDF assinado.", "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        if not enviado.filename.lower().endswith(".pdf"):
            flash("O documento assinado entra em PDF — é o formato que carrega "
                  "a assinatura digital.", "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        raiz = Path(db.get_setting("archive_root", "").strip()
                    or (Path(db.db_path).parent / "arquivos"))
        destino = raiz / "notas" / "assinados" / f"ato-{ato_id:05d}"
        info = save_upload(enviado, destino)
        anexo = db.add_attachment("NT_ATO", ato_id, info,
                                  int(app.extensions["usuario_id"]() or 0),
                                  "PDF assinado do ato")
        audit("NT_PDF_ASSINADO", "NT_ATO", ato_id,
              {"attachment_id": anexo, "sha256": info["sha256"]})
        flash(f"PDF assinado guardado, com a impressão digital "
              f"{info['sha256'][:16]}…", "success")
        return redirect(url_for("notas_ato", ato_id=ato_id))

    @app.route("/notas/atos/<int:ato_id>/anexos", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_ato_anexo(ato_id):
        """Documentos do instrumento; na ata, evidencias da constatacao.

        Aceita varios arquivos de uma vez (mesmo tipo/descricao).
        """
        a = q1("SELECT * FROM nt_atos WHERE id=?", (ato_id,))
        if not a:
            abort(404)
        enviados = [f for f in request.files.getlist("arquivo") if f and f.filename]
        descricao = (request.form.get("descricao") or "").strip()
        if not enviados:
            flash("Escolha o documento ou a evidencia.", "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        if a["tipo"] in ("ATA", "ATA_USUCAPIAO") and not descricao:
            flash("Na ata, descreva o que o arquivo comprova, a origem/local "
                  "e o momento da constatacao.", "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        raiz = Path(db.get_setting("archive_root", "").strip()
                    or (Path(db.db_path).parent / "arquivos"))
        destino = raiz / "notas" / "atos" / f"ato-{ato_id:05d}" / "evidencias"
        nomes = []
        ultimo_sha = ""
        for enviado in enviados:
            info = save_upload(enviado, destino)
            anexo_id = db.add_attachment(
                "NT_ATO", ato_id, info, int(app.extensions["usuario_id"]() or 0),
                descricao or "Documento do ato")
            audit("NT_ATO_ANEXO", "NT_ATO", ato_id,
                  {"attachment_id": anexo_id, "sha256": info["sha256"],
                   "descricao": descricao or "Documento do ato"})
            nomes.append(info.get("original_name") or enviado.filename)
            ultimo_sha = info["sha256"]
        if len(nomes) == 1:
            flash(f"Arquivo guardado com SHA-256 {ultimo_sha[:16]}…", "success")
        else:
            flash(f"{len(nomes)} arquivos guardados.", "success")
        return redirect(url_for("notas_ato", ato_id=ato_id))



    @app.route("/notas/atos/<int:ato_id>/anexos/<int:attachment_id>/retirar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_ato_anexo_retirar(ato_id, attachment_id):
        """Tira o arquivo da lista do ato. O binário fica no acervo; a auditoria registra."""
        a = q1("SELECT * FROM nt_atos WHERE id=?", (ato_id,))
        if not a:
            abort(404)
        if somente_leitura():
            flash("Perfil de auditoria não retira arquivo do ato.", "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        row = db.get_attachment(attachment_id)
        if not row or row["entity_type"] != "NT_ATO" or int(row["entity_id"]) != int(ato_id):
            flash("Arquivo não pertence a este ato.", "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        removido = db.delete_attachment(attachment_id)
        if not removido:
            flash("Arquivo não encontrado.", "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        audit("NT_ATO_ANEXO_RETIRADO", "NT_ATO", ato_id, {
            "attachment_id": attachment_id,
            "original_name": removido["original_name"],
            "sha256": removido["sha256"],
            "stored_path": removido["stored_path"],
        })
        flash(f"Arquivo '{removido['original_name']}' retirado deste ato.", "success")
        return redirect(url_for("notas_ato", ato_id=ato_id))



    @app.route("/notas/atos/<int:ato_id>", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_ato(ato_id):
        a = q1("SELECT * FROM nt_atos WHERE id=?", (ato_id,))
        if not a:
            abort(404)

        if request.method == "POST":
            acao = request.form.get("acao")
            if somente_leitura():
                flash("Perfil de auditoria não pratica ato. Lançar no livro "
                      "gasta folha e termo, e eles não voltam.", "danger")
                return redirect(url_for("notas_ato", ato_id=ato_id))

            # ------------------------------------------- depósito prévio
            #
            # Escritura tem adiantamento como qualquer título. Lançar pela tela
            # do caixa e depois tentar lembrar a que ato pertencia é como o
            # dinheiro deixa de ter dono — e a pergunta "quanto já foi pago
            # nesta escritura?" fica sem resposta.
            #
            # A criação vive em `caixa_depositos.py`: é a MESMA função que o
            # caixa e o Registro de Imóveis chamam. Copiá-la aqui seria repetir
            # o defeito das três cópias que foi corrigido nesta semana.
            if acao == "deposito":
                if (a["situacao"] or "") == "EM_LAVRATURA":
                    flash("Enquanto o ato está em lavratura, o adiantamento "
                          "se baixa no caixa — não se cadastra depósito novo "
                          "nesta tela. Abra Administrativo → Depósito prévio "
                          "e use «consumir» no depósito já vinculado a este "
                          "ato.", "warning")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                valor = CXC.centavos(request.form.get("valor"))
                primeira = q1("""SELECT nome FROM nt_ato_partes
                                 WHERE ato_id=? ORDER BY id LIMIT 1""", (ato_id,))
                depositante = ((request.form.get("depositante") or "").strip()
                               or (primeira["nome"] if primeira else ""))
                operador = usuario_nome()
                aberto = q1("""SELECT * FROM cx_caixas WHERE operador_nome=?
                               AND situacao='ABERTO' ORDER BY data DESC LIMIT 1""",
                            (operador,))
                with db.transaction() as con:
                    con.row_factory = sqlite3.Row
                    try:
                        feito = DEP.criar(
                            con, valor_centavos=valor, depositante=depositante,
                            agora=db.now(),
                            documento=request.form.get("depositante_documento"),
                            observacao=(request.form.get("observacao")
                                        or f"Depósito prévio do ato de livro "
                                           f"nº {ato_id}"),
                            forma_pagamento=request.form.get("forma_pagamento"),
                            caixa_id=aberto["id"] if aberto else None,
                            nt_ato_id=ato_id)
                    except ValueError as erro:
                        flash(str(erro), "danger")
                        return redirect(url_for("notas_ato", ato_id=ato_id))
                audit("DEPOSITO_PREVIO_CRIADO", "DEPOSITO", feito["id"],
                      {"numero": feito["numero"], "valor": feito["valor"],
                       "nt_ato": ato_id, "depositante": depositante})
                flash(f"Depósito {feito['numero']} — R$ {feito['valor']} — "
                      f"registrado neste ato"
                      + (" e lançado no caixa do dia." if feito["lancado_no_caixa"]
                         else ". ATENÇÃO: não há caixa aberto no seu nome, então "
                              "ele não entrou no movimento do dia. Abra o caixa e "
                              "lance a entrada, senão a gaveta não fecha."),
                      "success" if feito["lancado_no_caixa"] else "warning")
                return redirect(url_for("notas_ato", ato_id=ato_id))

            if acao == "parte_cartao":
                # Caminho 1: aproveitar a ficha de firma.
                cartao_id = int(request.form.get("cartao_id") or 0)
                c = q1("SELECT * FROM nt_cartoes WHERE id=?", (cartao_id,))
                if not c:
                    flash("Cartão não encontrado.", "danger")
                else:
                    d = NP.dados_para_parte(dict(c))
                    with db.transaction() as con:
                        con.execute(
                            """INSERT INTO nt_ato_partes
                               (ato_id, cartao_id, nome, nome_norm, documento,
                                tipo_pessoa, qualificacao, nacionalidade,
                                estado_civil, profissao, endereco, testemunha,
                                ordem, criado_em)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,
                                       (SELECT COALESCE(MAX(ordem),0)+1 FROM nt_ato_partes
                                         WHERE ato_id=?), ?)""",
                            (ato_id, cartao_id, d["nome"], d["nome_norm"], d["documento"],
                             d["tipo_pessoa"] or "F",
                             (request.form.get("qualificacao") or "").strip() or None,
                             d["nacionalidade"], d["estado_civil"], d["profissao"],
                             d["endereco_completo"],
                             1 if request.form.get("testemunha") else 0,
                             ato_id, db.now()))
                    audit("NT_ATO_PARTE", "NT_ATO", ato_id,
                          {"cartao": cartao_id, "origem": "CARTAO"})
                    faltando = NP.campos_faltantes(d, "ATO")
                    if faltando:
                        flash(f"Parte incluída, mas a ficha não tem: "
                              f"{', '.join(faltando)}. Complete no cartão.", "warning")
                    else:
                        flash("Parte incluída a partir do cartão de autógrafo.", "success")
            elif acao == "parte_nova":
                # Caminho 2: cadastro do zero, com opcao de abrir o cartao junto.
                nome = (request.form.get("nome") or "").strip()
                if not nome:
                    flash("Informe o nome da parte.", "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                dados = {k: request.form.get(k) for k in request.form}
                cartao_id = None
                with db.transaction() as con:
                    if request.form.get("abrir_cartao"):
                        cartao_id = NP.criar_cartao(con, dados, db.now(), usuario_nome())
                    con.execute(
                        """INSERT INTO nt_ato_partes
                           (ato_id, cartao_id, nome, nome_norm, documento, tipo_pessoa,
                            qualificacao, nacionalidade, estado_civil, profissao,
                            endereco, testemunha, ordem, criado_em)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,
                                   (SELECT COALESCE(MAX(ordem),0)+1 FROM nt_ato_partes
                                     WHERE ato_id=?), ?)""",
                        (ato_id, cartao_id, nome, NP.normalizar(nome),
                         NP.so_digitos(dados.get("documento")) or None,
                         (dados.get("tipo_pessoa") or "F")[:1],
                         (dados.get("qualificacao") or "").strip() or None,
                         (dados.get("nacionalidade") or "").strip() or None,
                         (dados.get("estado_civil") or "").strip() or None,
                         (dados.get("profissao") or "").strip() or None,
                         (dados.get("endereco") or "").strip() or None,
                         1 if request.form.get("testemunha") else 0, ato_id, db.now()))
                audit("NT_ATO_PARTE", "NT_ATO", ato_id,
                      {"origem": "NOVO", "cartao_aberto": cartao_id})
                flash("Parte incluída." + (f" Cartão de autógrafo nº {cartao_id} aberto — "
                                           f"da próxima vez é só procurar."
                                           if cartao_id else ""), "success")
            elif acao == "remover_parte":
                pid = int(request.form.get("parte_id") or 0)
                with db.transaction() as con:
                    con.execute("DELETE FROM nt_ato_partes WHERE id=? AND ato_id=?",
                                (pid, ato_id))
                audit("NT_ATO_PARTE_REMOVIDA", "NT_ATO", ato_id, {"parte": pid})
                flash("Parte removida.", "success")
            elif acao == "papel_doi":
                try:
                    pid = int(request.form.get("parte_id") or 0)
                except ValueError:
                    pid = 0
                lado = (request.form.get("doi_lado") or "").strip().upper()
                if lado not in ("", "ALIENANTE", "ADQUIRENTE", "FORA"):
                    flash("Papel DOI inválido.", "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                parte = q1("SELECT * FROM nt_ato_partes WHERE id=? AND ato_id=?",
                           (pid, ato_id))
                if not parte:
                    abort(404)
                if lado in ("ALIENANTE", "ADQUIRENTE") and (
                        parte["testemunha"] or
                        NDOI.lado_da_parte(parte["qualificacao"]) == "FORA"):
                    flash("Testemunha ou representante não pode ser titular "
                          "da operação na DOI. Revise a parte do ato.", "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                with db.transaction() as con:
                    alterado = con.execute(
                        "UPDATE nt_ato_partes SET doi_lado=? WHERE id=? AND ato_id=?",
                        (lado or None, pid, ato_id)).rowcount
                if not alterado:
                    abort(404)
                audit("NT_ATO_PARTE_PAPEL_DOI", "NT_ATO", ato_id,
                      {"parte": pid, "lado": lado})
                flash("Papel DOI desta parte atualizado no ato.", "success")
                return redirect(url_for("notas_ato", ato_id=ato_id))
            elif acao == "qualificacao_parte":
                # CORRIGIR A QUALIFICAÇÃO SEM TIRAR A PARTE — 09/10/2026. Até
                # aqui o único caminho era remover e incluir de novo; a trava
                # da lavratura passou a exigir qualificação que a CENSEC
                # entenda, e trava sem saída cômoda vira trava contornada.
                # Não mexe no teor: o texto já escrito continua o que é, e a
                # auditoria guarda o antes e o depois.
                try:
                    pid = int(request.form.get("parte_id") or 0)
                except ValueError:
                    pid = 0
                nova = " ".join((request.form.get("qualificacao") or "").split()).upper()
                parte = q1("SELECT * FROM nt_ato_partes WHERE id=? AND ato_id=?",
                           (pid, ato_id))
                if not parte:
                    abort(404)
                if not nova:
                    flash("Informe a qualificação da parte.", "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                with db.transaction() as con:
                    con.execute("UPDATE nt_ato_partes SET qualificacao=? "
                                "WHERE id=? AND ato_id=?", (nova, pid, ato_id))
                audit("NT_ATO_PARTE_QUALIFICACAO", "NT_ATO", ato_id,
                      {"parte": pid, "antes": parte["qualificacao"], "depois": nova})
                if NC.qualidade_cep(nova, a["tipo"]) is None and \
                        NC.central_do_ato(dict(a)) == "CEP":
                    flash(f"Qualificação gravada, mas «{nova}» não corresponde a "
                          "nenhuma qualidade da CEP — o ato não poderá ser lavrado "
                          "assim. Use outorgante, outorgado, interveniente, "
                          "testemunha, assina a rogo, requerente…", "warning")
                else:
                    flash("Qualificação da parte atualizada.", "success")
                return redirect(url_for("notas_ato", ato_id=ato_id))
            elif acao == "imovel":
                # OS DADOS DO IMOVEL, PARA A DOI — relatado pelo oficial em
                # 27/08/2026: «consta apenas DOI e CTP no registro de imoveis,
                # deveriamos ter para as escrituras tambem».
                #
                #   Ele esta certo, e o buraco era maior do que parecia: as
                #   colunas `com_imovel`, `doi_transacao`, `doi_matricula`,
                #   `doi_endereco` e `doi_area` **ja existiam** em `nt_atos`
                #   desde a importacao — e nenhuma tela as preenchia. Medido:
                #   zero em 260 escrituras.
                #
                #   A DOI e obrigacao com multa da Receita Federal, e uma
                #   escritura de compra e venda a gera do mesmo jeito que um
                #   registro. O sistema tinha o modulo inteiro (`notas_doi.py`)
                #   e so o Registro de Imoveis o chamava.
                com_imovel = request.form.get("com_imovel") == "1"
                operacao = (request.form.get("doi_transacao") or "").strip()
                if com_imovel and operacao and operacao not in CTP.TIPO_OPERACAO:
                    flash(f"{operacao} não é uma operação imobiliária da tabela "
                          f"da Receita. Escolha da lista.", "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                tipo = (request.form.get("doi_tipo_imovel") or "").strip()
                if com_imovel and tipo and tipo not in CTP.TIPO_IMOVEL:
                    flash(f"{tipo} não é um tipo de imóvel da tabela da "
                          f"Receita. Escolha da lista.", "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                torna_texto = (request.form.get("doi_torna_dinheiro") or "").strip()
                try:
                    torna = EMOL.centavos(torna_texto) if torna_texto else None
                except (ValueError, TypeError):
                    torna = -1
                if torna is not None and torna < 0:
                    flash("Informe uma torna em dinheiro válida.", "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                if torna and operacao != "13":
                    flash("Torna em dinheiro exige operação Permuta.", "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                if torna and a["valor_transacao"] and torna > a["valor_transacao"]:
                    flash("A torna não pode superar o valor total do ato.", "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                # A PARTICIPACAO DE CADA PARTE, QUE A RECEITA SOMA.
                #
                #   Ela valida que a soma de cada lado fique entre 99,00% e
                #   100,00% e recusa o ARQUIVO INTEIRO fora disso — nao a
                #   linha. Por isso a recusa e aqui, no balcao, com o cliente
                #   ainda na frente: descobrir no fim do mes que o arquivo
                #   voltou custa o prazo da serventia.
                #
                #   A folga de um ponto existe porque a divisao entre tres nao
                #   fecha em cem: 33,33 tres vezes da 99,99.
                partes_ato = [dict(x) for x in q(
                    "SELECT * FROM nt_ato_partes WHERE ato_id=? ORDER BY id",
                    (ato_id,))]
                percentuais = {
                    p["id"]: (request.form.get(f"participacao_{p['id']}") or "").strip()
                    for p in partes_ato}
                if com_imovel:
                    alienantes, adquirentes, _ = NDOI.lados_das_partes(partes_ato)
                    for rotulo, lado in (("alienantes", alienantes),
                                         ("adquirentes", adquirentes)):
                        if not lado:
                            continue
                        recusas = NDOI.conferir_participacoes(
                            [dict(x, participacao=percentuais.get(x["id"]))
                             for x in lado], rotulo)
                        if recusas:
                            flash(recusas[0].motivo, "danger")
                            return redirect(url_for("notas_ato", ato_id=ato_id))
                with db.transaction() as con:
                    con.execute(
                        """UPDATE nt_atos
                              SET com_imovel=?, doi_transacao=?,
                                  doi_tipo_imovel=?, doi_matricula=?,
                                  doi_endereco=?, doi_area=?, doi_torna_dinheiro=?
                            WHERE id=?""",
                        (1 if com_imovel else 0,
                         operacao or None, tipo or None,
                         (request.form.get("doi_matricula") or "").strip() or None,
                         (request.form.get("doi_endereco") or "").strip() or None,
                         (request.form.get("doi_area") or "").strip() or None,
                         torna,
                         ato_id))
                    for parte_id, quanto in percentuais.items():
                        con.execute(
                            "UPDATE nt_ato_partes SET participacao=? WHERE id=?",
                            (quanto or None, parte_id))
                audit("NOTAS_ATO_IMOVEL", "NOTAS_ATO", ato_id,
                      {"com_imovel": com_imovel, "operacao": operacao,
                       "participacoes": len([x for x in percentuais.values() if x])})
                flash("Dados do imóvel anotados. Eles vão para a DOI do mês, "
                      "junto com os atos do Registro de Imóveis — um arquivo "
                      "só, da serventia inteira." if com_imovel else
                      "Marcado como ato SEM imóvel: ele não entra na DOI.",
                      "success")
                return redirect(url_for("notas_ato", ato_id=ato_id))

            elif acao == "teor":
                # ESTA AÇÃO NÃO TOCA MAIS EM FOLHA.
                #
                # Ela escrevia `folha`, `folha_final` e `folhas` junto com o
                # teor, direto do formulário. Guardar o teor com o campo Folha
                # em branco — o que acontecia toda vez que alguém corrigia uma
                # vírgula — APAGAVA a folha do ato, em silêncio. A folha agora
                # só se escreve no lançamento, e uma vez só.
                corpo = request.form.get("teor") or ""
                with db.transaction() as con:
                    con.execute("""UPDATE nt_atos SET teor=?, teor_formato='html'
                                   WHERE id=?""", (corpo, ato_id))
                audit("NT_ATO_TEOR", "NT_ATO", ato_id, {"letras": len(corpo)})
                flash("Teor guardado. As páginas do livro o sistema conta "
                      "sozinho, no termo, na hora de lançar.", "success")

            elif acao == "lancar":
                # O lançamento no livro. É aqui, e só aqui, que o ato ganha
                # livro, folha inicial, folha final e termo.
                #
                # A TRAVA VEM ANTES DE TUDO — ordem do oficial em 09/10/2026
                # («cria travas na lavratura quando tivermos esses problemas e
                # nao for possivel enviar pra censec»). Antes da revisão prévia,
                # para ninguém gastar uma revisão num ato que não pode sair.
                # Ver `_travas_da_lavratura`.
                travas = _travas_da_lavratura(dict(a))
                if travas:
                    audit("NT_ATO_LAVRATURA_TRAVADA", "NT_ATO", int(ato_id),
                          {"motivos": travas[:20]})
                    flash("Ato NÃO lançado — corrija antes de lavrar: "
                          + " · ".join(travas[:6])
                          + (f" · e mais {len(travas) - 6}" if len(travas) > 6 else ""),
                          "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                #
                # A REVISÃO ANTES DA LAVRATURA vem primeiro — ordem do oficial
                # em 06/10/2026; ver `revisao_previa.py`. Ela vale para o teor
                # GUARDADO: teor mudado depois da revisão pede revisão nova.
                import revisao_previa as RV
                try:
                    with db.transaction() as _con_rv:
                        # HOTFIX-2026-10-08-07: papel + «lavrar com a revisão anterior».
                        _rv_como = RV.exigir_para_lavrar(
                            _con_rv, Path(app.config["DATA_DIR"]), "NOTAS", int(ato_id),
                            RV.hash_do_ato(a["tipo"], a["teor"]),
                            justificativa=request.form.get("revisao_justificativa") or "",
                            usuario=usuario_nome(),
                            papel=app.extensions["usuario_papel"](),
                            usar_revisao_anterior=request.form.get("revisao_usar_anterior") == "1",
                            justificativa_anterior=request.form.get("revisao_justificativa_anterior") or "",
                            texto_atual=a["teor"])
                    if str(_rv_como).startswith("anterior"):
                        audit("REVISAO_PREVIA_ANTERIOR_USADA", "NT_ATO", int(ato_id),
                              {"como": _rv_como,
                               "justificativa": request.form.get("revisao_justificativa_anterior") or ""})
                except RV.RevisaoPendente as erro:
                    flash(f"Ato NÃO lançado: {erro}", "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                gerar_arquivamento = request.form.get("gerar_arquivamento") == "1"
                folhas_arquivamento = None
                if gerar_arquivamento:
                    bruto_folhas = (request.form.get("folhas_arquivamento") or "").strip()
                    try:
                        folhas_arquivamento = int(bruto_folhas or 0)
                    except ValueError:
                        folhas_arquivamento = 0
                    if folhas_arquivamento < 1:
                        flash("Para gerar o selo de arquivamento junto com a "
                              "escritura, informe a quantidade de folhas (>= 1).",
                              "danger")
                        return redirect(url_for("notas_ato", ato_id=ato_id))
                item = (request.form.get("codigo_tj") or "").strip()
                if not item:
                    flash("Ato NÃO lançado: escolha o item da tabela de "
                          "emolumentos. É por ele que o selo é emitido; sem "
                          "o item o livro ficaria com um ato sem selo.",
                          "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                erro_item = _conferir_item_da_escritura(a, item)
                if erro_item:
                    flash(f"Ato NÃO lançado: {erro_item}", "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                # O valor vai CRU para `lancar_ato`, que usa `NL.quantidade` e
                # recusa 0, negativo e lixo. Passar por `NL.inteiro` aqui era o
                # bastante para "-3" virar 3 no caminho — ele lê o primeiro
                # grupo de dígitos e o sinal some.
                paginas = request.form.get("paginas")
                # AS PÁGINAS SE MEDEM NO TERMO, E NÃO SE PERGUNTAM (07/10/2026
                # — ver `_paginas_medidas_para_lancar`). O campo só volta à
                # tela quando a medição falha, e aí o escrevente conta no
                # papel; recusar o lançamento por falta do LibreOffice pararia
                # o balcão por uma peça de fora.
                if not (paginas or "").strip():
                    try:
                        paginas = _paginas_medidas_para_lancar(
                            dict(a), arquivamento=gerar_arquivamento)
                    except IPDF.PdfError as erro:
                        flash(f"Ato NÃO lançado: não consegui contar as "
                              f"páginas do termo ({erro}). Imprima o termo, "
                              f"conte as páginas escritas e informe abaixo.",
                              "danger")
                        return redirect(url_for("notas_ato", ato_id=ato_id,
                                                paginas_a_mao=1))
                anotado = None
                try:
                    with db.transaction() as con:
                        feito = NL.lancar_ato(
                            con, ato_id, _sv(), db.now(), _hoje_extenso(),
                            paginas=paginas, usuario=usuario_nome())
                        # A ANOTAÇÃO À MARGEM SAI NA MESMA TRANSAÇÃO.
                        #
                        # Revogação lançada no livro e procuração revogada
                        # intacta no livro anterior são duas verdades no mesmo
                        # acervo. Se a anotação falhar, o lançamento volta
                        # atrás junto — as duas coisas são um ato só.
                        anotado = NA.anotar_ato_anterior(
                            con, ato_id, _sv(), db.now(), usuario_nome())
                except (NL.LivroError, NA.AnotacaoError) as erro:
                    flash(str(erro), "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                except sqlite3.IntegrityError:
                    # A rede de baixo: `ux_nt_atos_folha` e `ux_nt_atos_termo`.
                    # Se ela disparar, alguma coisa passou por fora do contador
                    # — e o certo é recusar, não gravar duas escrituras na
                    # mesma folha.
                    flash("A folha ou o termo já estão ocupados. Confira o "
                          "livro antes de lançar de novo.", "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                audit("NT_ATO_LANCADO", "NT_ATO", ato_id, feito)
                if anotado:
                    audit("NT_ANOTACAO_MARGEM", "NT_ATO",
                          anotado["ato_id"], anotado)

                recado = (f"Lançado no livro {feito['livro']}, folha "
                          f"{feito['folha']}"
                          + (f" a {feito['folha_final']}"
                             if feito["folha_final"] != feito["folha"] else "")
                          + f", termo nº {feito['termo']}.")
                if feito["livro_aberto_automaticamente"]:
                    flash(f"O livro anterior encheu. Abri o livro "
                          f"{feito['livro']} com termo de abertura — confira e "
                          f"imprima na tela de livros.", "warning")
                if feito["folhas_inutilizadas"]:
                    flash(f"As folhas {feito['folhas_inutilizadas']} do livro "
                          f"encerrado ficaram em branco e o termo de "
                          f"encerramento as declarou inutilizadas. Inutilize-as "
                          f"no papel antes de encadernar.", "warning")
                if anotado:
                    flash(f"Anotado à margem do ato anterior: {anotado['texto']}"
                          + (f" O ato anotado passou a "
                             f"{SITUACOES_ATO[anotado['situacao_nova']].lower()}."
                             if anotado["situacao_nova"] else ""), "success")
                elif ATO_PEDE_ANOTACAO.get((a["tipo"] or "").upper()):
                    flash("Este ato pede anotação à margem do ato anterior, e "
                          "eu não consegui identificá-lo com segurança. "
                          "Vincule o ato anterior nesta tela, ou anote à mão.",
                          "warning")
                if feito["inutilizar"]:
                    flash(f"O texto termina na frente da folha "
                          f"{feito['folha_final']}. O verso ({feito['inutilizar']}) "
                          f"já sai inutilizado na última página do Termo do "
                          f"livro: imprima o termo inteiro, frente e verso — "
                          f"escrituração seguida, sem claros (art. 795, § 2º, "
                          f"do Código de Normas).", "info")

                # **O SELO SAI AQUI, com o ato já no livro** — 17/09/2026,
                # ordem do oficial: «constroi o modulo de selo automatizado na
                # escritura». O envelope leva livro e folha, que só existem
                # agora; e a chamada é FORA da transação, que já fechou.
                #
                #   **SEM ITEM MARCADO NÃO SAI SELO, e a tela diz por quê** —
                #   o item é escolha de quem atende, e a média do que a casa
                #   costuma cobrar não serve para o caso concreto.
                _atualizar_data_teor_antes_do_selo(ato_id)
                recado_do_selo = selar_o_ato_de_livro(
                    ato_id, codigo_tj=item,
                    especie_procuracao=request.form.get(
                        "especie_procuracao"),
                    isento=request.form.get("selo_isento") == "1",
                    motivo_isencao=request.form.get("motivo_isencao"))
                motivo = motivo_da_falha_do_selo(recado_do_selo)
                audit("NT_ATO_SELO_AUTOMATICO", "NT_ATO", ato_id,
                      {"item": item or None, "motivo": motivo,
                       "recado": recado_do_selo.strip()})
                if motivo:
                    with db.transaction() as con:
                        con.execute(
                            "UPDATE nt_atos SET situacao='SUSPENSO_SELO' "
                            "WHERE id=?", (ato_id,))
                    audit("NT_ATO_NAO_LAVRADO_SELO_FALHOU", "NT_ATO",
                          ato_id, {"item": item, "motivo": motivo})
                    flash("Ato NÃO concluído: o selo não saiu. "
                          f"Motivo: {motivo}. O livro e a folha ficaram "
                          "reservados para este mesmo ato; corrija o problema "
                          "e use «Pedir o selo ao aparelho».", "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                recado_do_arquivamento = ""
                if gerar_arquivamento and folhas_arquivamento:
                    partes_arq = [dict(p) for p in q(
                        "SELECT nome, documento FROM nt_ato_partes "
                        "WHERE ato_id=? ORDER BY id", (ato_id,))]
                    selo_ato = q1("SELECT selo FROM nt_atos WHERE id=?",
                                  (ato_id,))["selo"]
                    arq = _selar_arquivamento_das_notas(
                        ato_id=ato_id, folhas=folhas_arquivamento,
                        selo_do_ato=str(selo_ato or "").strip() or None,
                        partes=[(p["nome"], p.get("documento"))
                                for p in partes_arq],
                        isento=request.form.get("selo_isento") == "1",
                        motivo_isencao=request.form.get("motivo_isencao"))
                    if arq.get("ok"):
                        recado_do_arquivamento = arq["recado"]
                        audit("NT_ATO_ARQUIVAMENTO_SELADO", "NT_ATO", ato_id,
                              {"folhas": folhas_arquivamento,
                               "selo_arquivamento": arq["numero"]})
                    else:
                        recado_do_arquivamento = (
                            f" Arquivamento PENDENTE ({folhas_arquivamento} "
                            f"folha(s)): {arq.get('motivo')}. Use «Selar "
                            f"arquivamento» na ficha para tentar de novo.")
                        audit("NT_ATO_ARQUIVAMENTO_PENDENTE", "NT_ATO", ato_id,
                              {"folhas": folhas_arquivamento,
                               "motivo": arq.get("motivo")})
                flash(recado, "success")
                flash(recado_do_selo.strip() + recado_do_arquivamento,
                      "warning" if "PENDENTE" in recado_do_arquivamento
                      else "success")
            elif acao == "anotar":
                # Anotação escrita à mão. O caminho de fora: revogação lavrada
                # em outra serventia, ordem judicial, retificação.
                try:
                    with db.transaction() as con:
                        feito = NA.anotar(
                            con, ato_id, request.form.get("tipo") or "",
                            db.now(),
                            texto=request.form.get("texto"),
                            data=request.form.get("data"),
                            selo=request.form.get("selo_anotacao"),
                            criado_por=usuario_nome(), sv=_sv(),
                            externa=bool(request.form.get("externa")),
                            serventia_externa=request.form.get("serventia_externa"),
                            cns_externa=request.form.get("cns_externa"))
                except NA.AnotacaoError as erro:
                    flash(str(erro), "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                audit("NT_ANOTACAO_MARGEM", "NT_ATO", ato_id, feito)
                flash("Anotação escrita à margem."
                      + (f" O ato passou a "
                         f"{SITUACOES_ATO[feito['situacao_nova']].lower()}."
                         if feito["situacao_nova"] else "")
                      + (f" {feito['aviso']}" if feito.get("aviso") else "")
                      + " Anotação não se apaga: errada, corrige-se com outra.",
                      "warning" if feito.get("aviso") else "success")

            elif acao == "vincular_anterior":
                anterior_id = NL.inteiro(request.form.get("anterior_id")) or 0
                try:
                    with db.transaction() as con:
                        ligado = NA.vincular_anterior(con, ato_id, anterior_id, _sv())
                        anotado = (NA.anotar_ato_anterior(
                            con, ato_id, _sv(), db.now(), usuario_nome())
                            if (a["situacao"] or "") != "EM_LAVRATURA" else None)
                except NA.AnotacaoError as erro:
                    flash(str(erro), "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                audit("NT_ATO_ANTERIOR", "NT_ATO", ato_id, ligado)
                if anotado:
                    audit("NT_ANOTACAO_MARGEM", "NT_ATO", anotado["ato_id"], anotado)
                flash(f"Vinculado ao ato do livro {ligado['livro']}, folha "
                      f"{ligado['folha']}."
                      + (" Anotação escrita à margem dele."
                         if anotado else
                         " A anotação sai quando este ato for lançado no livro."),
                      "success")

            elif acao == "selar":
                # **SELAR UM ATO JÁ LANÇADO** — a saída de quando o aparelho
                # estava fora do ar na hora do lançamento. Sem ela, o ato
                # ficaria sem selo para sempre: o livro já foi escrito, e
                # desfazê-lo é o que o sistema recusa. É o mesmo botão que o
                # RI ganhou em 15/09, pela mesma razão.
                item = (request.form.get("codigo_tj") or "").strip()
                if not item:
                    flash("Marque o item da tabela de emolumentos: é por ele "
                          "que o selo sai.", "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                erro_item = _conferir_item_da_escritura(a, item)
                if erro_item:
                    flash(f"O selo não foi pedido: {erro_item}", "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                _atualizar_data_teor_antes_do_selo(ato_id)
                recado = selar_o_ato_de_livro(
                    ato_id, codigo_tj=item,
                    especie_procuracao=request.form.get("especie_procuracao"),
                    isento=request.form.get("selo_isento") == "1",
                    motivo_isencao=request.form.get("motivo_isencao"))
                motivo = motivo_da_falha_do_selo(recado)
                audit("NT_ATO_SELO_AUTOMATICO", "NT_ATO", ato_id,
                      {"item": item, "motivo": motivo,
                       "recado": recado.strip()})
                if motivo:
                    flash("O selo ainda não saiu. "
                          f"Motivo: {motivo}. O ato continua suspenso.",
                          "danger")
                else:
                    with db.transaction() as con:
                        con.execute(
                            "UPDATE nt_atos SET situacao='LAVRADO' "
                            "WHERE id=? AND situacao='SUSPENSO_SELO'",
                            (ato_id,))
                    flash(recado.strip(), "success")

            elif acao == "selo":
                # **O SELO À MÃO PASSA PELO RAZÃO — 17/09/2026.** Até aqui esta
                # tela gravava `nt_atos.selo` direto: o número não era lido, o
                # CNS não era conferido, o selo repetido só era recusado dentro
                # desta mesma tabela, e **nada entrava em `sd_selos`** — de
                # modo que a tela «Selos» não via, e a trava do razão ficava
                # desligada. É o buraco que este projeto declarou em 01/09 e
                # que `registrar_selo_obtido_a_mao` existe para fechar: função
                # pronta que ninguém chamava, pela enésima vez.
                selo = (request.form.get("selo") or "").strip().upper()
                if not selo:
                    flash("Informe o número do selo.", "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                try:
                    with db.transaction() as con:
                        AS.registrar_selo_obtido_a_mao(
                            con, selo, tabela="nt_atos", ato_id=int(ato_id),
                            atribuicao="NOTAS", agora=db.now(),
                            cns=db.get_setting("ri_cns", ""),
                            usuario=usuario_nome(),
                            texto=(request.form.get("selo_texto") or "").strip()
                            or None)
                except AS.AtoError as erro:
                    flash(str(erro), "danger")
                    return redirect(url_for("notas_ato", ato_id=ato_id))
                with db.transaction() as con:
                    con.execute(
                        "UPDATE nt_atos SET situacao='LAVRADO' "
                        "WHERE id=? AND situacao='SUSPENSO_SELO'", (ato_id,))
                audit("NT_ATO_SELADO", "NT_ATO", ato_id, {"selo": selo})
                flash("Selo registrado, e ele entrou no razão dos selos.",
                      "success")

            elif acao == "anotacao_de_lavratura":
                # **A ANOTAÇÃO ANTES DA LAVRATURA** — 17/09/2026, pedido do
                # oficial: «acrescenta o campo de anotações antes da lavratura
                # também para as escrituras e atas notariais».
                #
                #   **ELA NÃO É A ANOTAÇÃO À MARGEM.** Aquela é ATO — entra no
                #   livro, tem selo e não se apaga; esta é nota de trabalho, e
                #   existe antes de o ato existir. A mesma palavra em dois
                #   lugares não quer dizer a mesma coisa.
                texto = (request.form.get("observacao") or "").strip()
                with db.transaction() as con:
                    con.execute(
                        """UPDATE nt_atos
                              SET observacao=?, observacao_em=?, observacao_por=?
                            WHERE id=?""",
                        (texto or None, db.now(), usuario_nome(), ato_id))
                audit("NT_ANOTACAO_DA_LAVRATURA", "NT_ATO", ato_id,
                      {"texto": texto or None})
                flash("Anotação guardada." if texto else "Anotação apagada.",
                      "success")
            elif acao == "situacao":
                nova = (request.form.get("situacao") or "").upper()
                motivo = (request.form.get("motivo") or "").strip()
                if nova not in SITUACOES_ATO:
                    flash("Situação inválida.", "danger")
                elif nova == "EM_LAVRATURA":
                    # Voltar um ato lavrado para rascunho desfaria a folha no
                    # banco e não desfaria no papel. O livro já foi escrito.
                    flash("Ato já lançado no livro não volta para lavratura. "
                          "O que se faz com ato errado é anotá-lo à margem.",
                          "danger")
                elif nova == "LAVRADO" and a["termo"] is None:
                    flash("Este ato ainda não foi lançado no livro. Use o "
                          "lançamento, que atribui livro, folha e termo.",
                          "danger")
                elif nova != "LAVRADO" and not motivo:
                    flash("Diga o motivo.", "danger")
                else:
                    with db.transaction() as con:
                        con.execute("""UPDATE nt_atos SET situacao=?, sem_efeito_motivo=?,
                                       revogado_em=?, revogado_por=? WHERE id=?""",
                                    (nova, motivo or None,
                                     date.today().isoformat() if nova != "LAVRADO" else None,
                                     usuario_nome() if nova != "LAVRADO" else None, ato_id))
                    audit("NT_ATO_SITUACAO", "NT_ATO", ato_id,
                          {"situacao": nova, "motivo": motivo})
                    flash(f"Ato marcado como {SITUACOES_ATO[nova].lower()}.", "success")
            return redirect(url_for("notas_ato", ato_id=ato_id))

        partes = q("""SELECT * FROM nt_ato_partes WHERE ato_id=? ORDER BY testemunha, ordem""",
                   (ato_id,))
        modelo = q1("SELECT * FROM nt_modelos WHERE codigo=?",
                    (a["modelo_codigo"],)) if a["modelo_codigo"] else None
        familia = NF.do_tipo_ato(a["tipo"])
        anexos = db.get_attachments("NT_ATO", ato_id)
        modelo_padrao = NMOD.por_codigo(a["modelo_codigo"]) if a["modelo_codigo"] else None
        requisitos_modelo = (modelo_padrao or {}).get("requisitos", [])
        busca = (request.args.get("busca_parte") or "").strip()
        achados = []
        if len(busca) >= 3:
            with db.connect() as con:
                achados = NP.buscar_cartoes(con, busca, limite=10)
            for c in achados:
                c["avisos"] = NP.avisos_do_cartao(c)
        # O QUADRO DE PREENCHER NAO FECHA MAIS SOZINHO — relato #78,
        # 17/09/2026: «depois que avanca e salva o rascunho da escritura, nao
        # consegue voltar pra pagina intermediaria de preenchimento de dados».
        #
        #   A condicao era `modelo and not teor`: o quadro existia **enquanto o
        #   teor estivesse vazio**, e sumia no instante em que ele era
        #   preenchido — justamente quando se descobre que um campo saiu
        #   errado. O que sobrava era editar o texto corrido a mao, ou
        #   descobrir o truque que outra mensagem do sistema cita de passagem
        #   («esvazie o teor e preencha de novo»). Truque que o sistema conta
        #   numa mensagem de erro nao e caminho: e senha.
        #
        #   COM TEOR ELE SAI FECHADO E AVISANDO, porque preencher **substitui**
        #   o teor: quem editou o texto a mao depois de preencher perde a
        #   edicao, e isso tem de estar escrito antes do clique.
        campos = []
        if modelo:
            try:
                campos = campos_do_modelo({"corpo": modelo["corpo"]})
            except Exception:                                   # noqa: BLE001
                campos = []
        # E O QUE ELE JA TINHA DIGITADO VOLTA COM ELE. Sem isto, «voltar a
        # pagina de preenchimento» seria redigitar dezenas de campos.
        valores_do_modelo = {}
        try:
            import json as _json
            valores_do_modelo = _json.loads(a["modelo_valores"] or "{}") or {}
        except (KeyError, IndexError, ValueError, TypeError):
            valores_do_modelo = {}

        # Assinantes do fecho: se o campo ainda está vazio, sugere nome e
        # condição das partes já qualificadas no formulário (pedido 18/09/2026).
        if not (valores_do_modelo.get(NT.CHAVE_ASSINANTES) or "").strip():
            sugerido = NT.texto_dos_assinantes(partes)
            if sugerido:
                valores_do_modelo[NT.CHAVE_ASSINANTES] = sugerido
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            depositos = DEP.do_ato(con, ato_id)

        # O que o lançamento vai atribuir, se ainda não foi lançado. Mostrar
        # antes evita a surpresa de descobrir o livro depois de imprimir.
        paginas_estimadas = NL.estimar_paginas(a["teor"])
        previsao = None
        if (a["situacao"] or "") == "EM_LAVRATURA" and a["termo"] is None:
            with db.connect() as con:
                con.row_factory = sqlite3.Row
                previsao = NL.previsao(con, a["tipo"], paginas_estimadas)

        # Anotações à margem, e a busca do ato anterior quando o ato é dos
        # que pedem uma (revogação, renúncia, substabelecimento).
        busca_anterior = (request.args.get("busca_anterior") or "").strip()
        pede_anotacao = ATO_PEDE_ANOTACAO.get((a["tipo"] or "").upper())
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            anotacoes = NA.do_ato(con, ato_id)
            anterior = (con.execute("SELECT * FROM nt_atos WHERE id=?",
                                    (a["anterior_ato_id"],)).fetchone()
                        if a["anterior_ato_id"] else None)
            candidatos = (NA.candidatos(con, busca_anterior)
                          if pede_anotacao and busca_anterior else [])
            candidatos = [c for c in candidatos if c["id"] != ato_id]

        # Sobrando o verso, quanto de entrelinha o fecharia — dentro da banda
        # que o delegatário autorizou. É sugestão, não ajuste: ver
        # `notas_inutilizacao.sugerir_entrelinha`.
        #
        # 07/10/2026: a sugestão saiu da tela. Ela partia da ESTIMATIVA, e o
        # verso que sobra agora sai inutilizado no próprio termo — não há mais
        # o que o escrevente decidir aqui.
        entrelinha = None
        face_em_branco = NI.faces_do_ato(a)

        # A LISTA DE ATENCAO PARA FRAUDES, sobre as partes do ato. `nt_partes`
        # ja guarda `nome_norm`, e por isso a busca por nome acha com acento.
        with db.connect() as _c:
            _c.row_factory = sqlite3.Row
            fraudes = FR.conferir_pessoas(_c, [
                {"nome": x.get("nome"), "documento": x.get("documento"),
                 "papel_no_ato": (x.get("qualificacao") or "parte")}
                for x in map(dict, partes)])
        # DE QUE LADO CADA PARTE ESTA, E QUANTO SE SUGERE PARA ELA.
        #
        #   A regua e a mesma que monta a declaracao — `lados_das_partes` —, e
        #   nao uma segunda leitura «parecida»: a tela tem de mostrar o que o
        #   arquivo vai levar, senao ela mostra uma coisa e manda outra.
        #
        #   A sugestao vai PREENCHIDA no campo, a vista, porque o oficial
        #   decidiu em 28/08/2026 que ninguem manda um percentual sem ver qual
        #   e. Ela so vale depois de gravada.
        _lista = [dict(x) for x in partes]
        _al, _ad, _ = NDOI.lados_das_partes(_lista)
        _sugerido = {}
        for _grupo in (_al, _ad):
            for _parte, _quanto in zip(_grupo,
                                       NDOI.participacoes_sugeridas(len(_grupo))):
                _sugerido[_parte["id"]] = _quanto
        doi_partes = [{"p": x, "lado": NDOI.lado_da_parte_no_ato(x),
                       "sugerido": _sugerido.get(x["id"], "")}
                      for x in _lista]
        return render_template("notas_ato.html", a=dict(a), partes=partes,
                               doi_partes=doi_partes,
                               fraudes=fraudes, modelo=modelo, familia=familia,
                               anexos=anexos,
                               requisitos_modelo=requisitos_modelo,
                               campos=campos, valores_do_modelo=valores_do_modelo,
                               busca_parte=busca, achados=achados,
                               pendencias=pendencias_modelo(a["teor"] or ""),
                               falta_qualificar=NT.pendencias_da_qualificacao(partes),
                               depositos=depositos, previsao=previsao,
                               paginas_estimadas=paginas_estimadas,
                               paginas_a_mao=bool(request.args.get("paginas_a_mao")),
                               entrelinha=entrelinha, face_em_branco=face_em_branco,
                               anotacoes=anotacoes, anterior=anterior,
                               pede_anotacao=pede_anotacao,
                               busca_anterior=busca_anterior,
                               candidatos=candidatos,
                               saldo=CXC.reais(DEP.saldo_do_titulo(depositos)),
                               FORMAS=CXC.FORMAS_PAGAMENTO,
                               TIPOS_ANOTACAO=TIPOS_ANOTACAO,
                               # AS TABELAS DA RECEITA, para a escritura dizer
                               # o que a DOI pede — em caixa de seleção, e não
                               # em campo livre: código de operação digitado à
                               # mão é o que a Receita recusa sem dizer qual
                               # linha.
                               DOI_OPERACOES=CTP.TIPO_OPERACAO,
                               DOI_IMOVEIS=CTP.TIPO_IMOVEL,
                               TIPOS_ATO=TIPOS_ATO, SITUACOES=SITUACOES_ATO,
                               # O SELO DO ATO DE LIVRO — 17/09/2026. A tela
                               # oferece os itens que a casa usou NAQUELE
                               # caminho, em ordem de frequencia, e as tres
                               # procuracoes; quem decide o caminho e o
                               # dominio, e nao esta lista.
                               **_o_selo_desta_tela(a))

    def _o_selo_desta_tela(a) -> dict:
        """O que a tela precisa para pedir o selo do ato de livro. SO LE.

        **OS ITENS SAO OS QUE A CASA USOU NAQUELE CAMINHO**, em ordem de
        frequencia — medidos nos 283 envelopes reais. Item de um uso em
        duzentos e excecao, e nao regra, e por isso a ordem importa.

        **E O NOME DO SERVICO SAI DE `cx_servicos`**: quem atende escolhe pelo
        que o item e, e nao por um codigo de quatro digitos. Item que o
        cadastro nao conhece aparece assim mesmo, com o codigo — sumir com ele
        esconderia justamente o que falta cadastrar.
        """
        tipo = str((a["tipo"] or "")).strip().upper()
        if tipo not in ("ESCRITURA", "PROCURACAO", "ATA",
                        "ATA_USUCAPIAO"):
            return {
                "selo_caminhos": [], "selo_sem_caminho": True,
                "selo_aviso": (f"Ainda não há caminho de selo configurado "
                                f"para {TIPOS_ATO.get(tipo, tipo)}.")}
        if tipo == "ATA_USUCAPIAO" and not a["valor_transacao"]:
            return {
                "selo_caminhos": [], "selo_sem_caminho": True,
                "selo_aviso": (
                    "A ata para usucapião ainda não pode ser selada: informe "
                    "o valor do imóvel. O item 13.14.3 manda calcular pelas "
                    "faixas do item 13.1 conforme esse valor.")}
        if tipo == "ESCRITURA":
            com_valor = bool(a["valor_transacao"])
            caminhos = [(None, AS.caminho_do_ato_de_livro_das_notas(
                tipo, com_valor=com_valor))]
        elif tipo in ("ATA", "ATA_USUCAPIAO"):
            caminhos = [(None, AS.caminho_do_ato_de_livro_das_notas(
                tipo, com_valor=bool(a["valor_transacao"])))]
        else:
            caminhos = [(chave, caminho) for chave, caminho
                        in AS.CAMINHO_DA_PROCURACAO.items()]
        fora = []
        for chave, caminho in caminhos:
            itens = []
            catalogo = (AS.ITENS_DA_ATA.get(tipo, ())
                        if tipo in AS.ITENS_DA_ATA
                        else AS.ITENS_MEDIDOS_DO_ATO_DE_LIVRO.get(caminho, ()))
            if tipo == "ESCRITURA" and a["valor_transacao"]:
                faixa = _faixa_da_escritura(a)
                catalogo = ((faixa["codigo_tj"], 0),) if faixa and faixa.get("codigo_tj") else ()
            for codigo, quantas in catalogo:
                linha = q1("SELECT descricao FROM cx_servicos WHERE codigo_tj=? "
                           "LIMIT 1", (codigo,))
                itens.append({
                    "codigo": codigo, "usos": quantas,
                    "descricao": (linha["descricao"] if linha else "") or ""})
            fora.append({"chave": chave, "caminho": caminho, "itens": itens})
        aviso = None
        if tipo == "ESCRITURA" and a["valor_transacao"]:
            faixa = _faixa_da_escritura(a)
            if not faixa or not faixa.get("codigo_tj") or faixa.get("acima_do_teto"):
                return {"selo_caminhos": [], "selo_sem_caminho": True,
                        "selo_aviso": "Não foi possível conferir a faixa vigente da escritura. Revise a tabela de custas antes de lançar."}
            aviso = f"Faixa vigente para o valor declarado: {faixa['codigo_tj']}. Confira com o orçamento."
        if tipo == "ATA":
            aviso = ("O selo principal usa o item 13.14.1 (primeira folha). "
                     "O item 13.14.2 é cobrança complementar por folha "
                     "excedente e não substitui o selo principal.")
        return {"selo_caminhos": fora, "selo_sem_caminho": False,
                "selo_aviso": aviso}

    def _faixa_da_escritura(a):
        with db.connect() as con:
            return EMOL.faixa_por_valor(con, a["valor_transacao"], tabela=3)

    def _conferir_item_da_escritura(a, item: str) -> str | None:
        if (a["tipo"] or "").upper() != "ESCRITURA" or not a["valor_transacao"]:
            return None
        faixa = _faixa_da_escritura(a)
        if not faixa or not faixa.get("codigo_tj") or faixa.get("acima_do_teto"):
            return "não foi possível conferir a faixa vigente da escritura; revise a tabela de custas"
        if item != faixa["codigo_tj"]:
            return f"o valor do ato exige o item {faixa['codigo_tj']} da tabela vigente"
        return None

    # ONDE SE CORRIGE CADA IMPEDIMENTO DA CENSEC — a recusa diz o que fazer, e
    # não só o que falta (regra da casa). As chaves são os campos de
    # `notas_censec.Impedimento`.
    _ONDE_CORRIGIR = {
        "partes": "inclua as partes no quadro «Partes»",
        "partes.nome": "corrija o nome da parte",
        "partes.qualidade": "escolha a qualificação no quadro «Partes»",
        "partes.numeroDocumento": "corrija o CPF/CNPJ no cartão da parte",
        "valor": "informe o valor em Notas → Escrituras pendentes",
        "naturezaEscritura": "escolha a natureza em Notas → Escrituras pendentes",
    }

    def _travas_da_lavratura(a: dict) -> list[str]:
        """O que impede este ato de ser lavrado — vazio, pode lavrar.

        Duas coisas, e as duas pelos MESMOS detectores que já existem:
        o campo em branco do teor (`pendencias_modelo`, que a tela só
        avisava) e o que a CENSEC recusaria
        (`notas_censec.impedimentos_para_lavrar`, a conferência da remessa).
        """
        # Ato que já não está em lavratura não passa por aqui: quem recusa o
        # relançamento é `notas_livro`, com a frase dele («já está lançado»).
        if (a.get("situacao") or "") != "EM_LAVRATURA":
            return []
        travas = [f"o texto tem campo em branco {m} — edite o teor"
                  for m in pendencias_modelo(a.get("teor") or "")]
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            for imp in NC.impedimentos_para_lavrar(con, a):
                onde = _ONDE_CORRIGIR.get(imp.campo)
                travas.append(f"CENSEC: {imp.motivo}" + (f" — {onde}" if onde else ""))
            if (a.get("tipo") or "") in TIPOS_COM_TRAVA_DE_PROCURACAO:
                partes = [dict(p) for p in con.execute(
                    "SELECT * FROM nt_ato_partes WHERE ato_id=? ORDER BY ordem, id",
                    (a["id"],))]
                travas += _travas_da_procuracao(a, partes)
        return travas

    # A PROCURAÇÃO SÓ LAVRA COM TODOS OS CAMPOS DO ATO PREENCHIDOS — ordem do
    # oficial em 13/10/2026: «coloque revisor de procuracao pelo sonnet,
    # obrigando que todos campos do ato sejam preenchidos no sistema, para nao
    # ocorrer esse problema de novo». O problema: a procuração 791 foi lavrada
    # com o procurador só no termo impresso (corrigido fora do sistema) — o
    # cadastro ficou sem ele e o texto guardado, com o colchete do modelo. A
    # leitura pelo Sonnet (`revisao_previa`) aponta o que é de redação; ESTAS
    # travas são regra fixa e não dependem da IA responder.
    TIPOS_COM_TRAVA_DE_PROCURACAO = ("PROCURACAO", "PROCURACAO_PREVIDENCIARIA")

    def _travas_da_procuracao(a: dict, partes: list[dict]) -> list[str]:
        travas = []
        quem = [p for p in partes if not p.get("testemunha")]
        qualidades = {NC.qualidade_cep(p.get("qualificacao"), a.get("tipo")) for p in quem}
        if "Outorgante" not in qualidades:
            travas.append("procuração sem OUTORGANTE no quadro «Partes» — inclua quem "
                          "outorga e qualifique como outorgante")
        if "Outorgado" not in qualidades:
            travas.append("procuração sem OUTORGADO (procurador) no quadro «Partes» — "
                          "inclua o procurador e qualifique como outorgado")
        for falta in NT.pendencias_da_qualificacao(quem):
            travas.append(f"cadastro incompleto — {falta}: complete no cartão da parte")
        texto = NC._norm(re.sub(r"<[^>]+>", " ", a.get("teor") or ""))
        texto = " ".join(texto.split())
        for p in quem:
            nome = " ".join(NC._norm(p.get("nome") or "").split())
            if nome and nome not in texto:
                travas.append(f"{p.get('nome')} está no quadro «Partes» e não aparece no "
                              "texto do ato — confira o teor")
        return travas

    @app.route("/notas/atos/<int:ato_id>/montar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_ato_montar(ato_id):
        """Monta o teor: comparecimento, qualificação das partes e o objeto.

        Os 301 modelos importados do E-Ofício (`origem='EOFICIO'`) são só a
        cláusula de poderes — o resto ele monta por fora, a partir do
        cadastro. Aqui a qualificação sai das partes do ato, que por sua vez
        vieram da ficha de firma.

        OS MODELOS DO SUBMÓDULO (`origem='SISTEMA'`) NÃO PASSAM POR AQUI —
        achado em 07/09/2026, com o oficial testando o ato 777 no servidor.
        Eles são instrumento completo, com o próprio comparecimento, a
        própria qualificação (`{{ outorgantes }}`/`{{ outorgados }}`) e o
        próprio fecho — e esta rota escreve o SEU comparecimento e a SUA
        qualificação por cima, colando o corpo do modelo (cru, sem passar
        pelo Jinja) depois. O ato saía com o texto dobrado: um comparecimento
        de verdade seguido do modelo inteiro de novo, com `{{ }}` e
        `[CAMPO]` intactos. Quem monta os de origem SISTEMA é
        `notas_ato_preencher`, e só ele.
        """
        a = q1("SELECT * FROM nt_atos WHERE id=?", (ato_id,))
        if not a:
            abort(404)
        partes = [dict(p) for p in q(
            "SELECT * FROM nt_ato_partes WHERE ato_id=? ORDER BY testemunha, ordem",
            (ato_id,))]
        if not partes:
            flash("Inclua as partes antes de montar o teor.", "warning")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        modelo = q1("SELECT * FROM nt_modelos WHERE codigo=?",
                    (a["modelo_codigo"],)) if a["modelo_codigo"] else None
        if modelo and modelo["origem"] == "SISTEMA":
            flash("Este modelo já é o instrumento completo — use "
                  "\"Preencher a partir do modelo\", não \"Montar o teor\". "
                  "Se o teor já tiver sido montado errado, esvazie-o em "
                  "\"Editar o teor\" e preencha de novo a partir do modelo.",
                  "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        from ri_web import data_por_extenso
        s = db.get_settings()
        corpo = NT.montar(
            a["tipo"], partes, modelo["corpo"] if modelo else None,
            data_extenso=data_por_extenso(date.fromisoformat(a["data"])),
            cidade=s.get("ri_cidade", ""), uf=s.get("ri_uf", "MA"),
            lavrado_nome=a["lavrado_nome"] or usuario_nome(),
            lavrado_titulo=a["lavrado_titulo"] or usuario_funcao())
        with db.transaction() as con:
            con.execute("UPDATE nt_atos SET teor=?, teor_formato='html' WHERE id=?",
                        (corpo, ato_id))
        audit("NT_ATO_MONTADO", "NT_ATO", ato_id, {"partes": len(partes)})
        faltas = NT.pendencias_da_qualificacao(partes)
        if faltas:
            flash("Teor montado, mas a qualificação está incompleta — "
                  + "; ".join(faltas[:3]), "warning")
        else:
            flash("Teor montado com a qualificação das partes.", "success")
        return redirect(url_for("notas_ato", ato_id=ato_id))

    @app.route("/notas/atos/<int:ato_id>/selar-arquivamento", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_selar_arquivamento(ato_id):
        """Selo 13.30 quando a lavratura deixou o arquivamento pendente."""
        a = q1("SELECT * FROM nt_atos WHERE id=?", (ato_id,))
        if not a:
            abort(404)
        if not str(a["selo"] or "").strip():
            flash("Peça primeiro o selo da escritura — o arquivamento sai "
                  "depois.", "warning")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        if str(a["selo_arquivamento"] or "").strip():
            flash(f"Este ato já tem selo de arquivamento: "
                  f"{a['selo_arquivamento']}.", "warning")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        bruto = (request.form.get("folhas_arquivamento") or "").strip()
        try:
            folhas = int(bruto or 0)
        except ValueError:
            folhas = 0
        if folhas < 1:
            flash("Informe a quantidade de folhas (>= 1) para o arquivamento.",
                  "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        partes_arq = [dict(p) for p in q(
            "SELECT nome, documento FROM nt_ato_partes WHERE ato_id=? "
            "ORDER BY id", (ato_id,))]
        arq = _selar_arquivamento_das_notas(
            ato_id=ato_id, folhas=folhas,
            selo_do_ato=str(a["selo"] or "").strip(),
            partes=[(p["nome"], p.get("documento")) for p in partes_arq])
        if arq.get("ok"):
            audit("NT_ATO_ARQUIVAMENTO_SELADO", "NT_ATO", ato_id,
                  {"folhas": folhas, "selo_arquivamento": arq["numero"]})
            flash(f"Arquivamento selado.{arq['recado']}", "success")
        else:
            audit("NT_ATO_ARQUIVAMENTO_PENDENTE", "NT_ATO", ato_id,
                  {"folhas": folhas, "motivo": arq.get("motivo")})
            flash(f"Arquivamento não saiu: {arq.get('motivo')}.", "danger")
        return redirect(url_for("notas_ato", ato_id=ato_id))

    @app.route("/notas/atos/<int:ato_id>/preencher", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_ato_preencher(ato_id):
        """Aplica o modelo escolhido, com os campos que o operador preencheu.

        OS MODELOS DE `notas_modelos.py` TÊM DUAS CAMADAS DE MARCADOR, E ESTA
        ROTA SÓ RESOLVIA UMA. `[CAMPO]`, `{ESCOLHA}` e `«SE»` vêm de
        `preencher_modelo`; mas `{{ sv.ri_cidade }}`, `{{ lavrado_nome }}`,
        `{{ lavrado_titulo }}`, `{{ outorgantes }}` e `{{ outorgados }}` são
        Jinja, e nada os renderizava — o ato sairia com as chaves duplas
        escritas por cima do nome das partes, no documento que a serventia
        assina. Achado ao ajustar o modelo da escritura pública ao padrão do
        oficial em 07/09/2026, e corrigido antes de a lacuna chegar ao balcão.
        """
        a = q1("SELECT * FROM nt_atos WHERE id=?", (ato_id,))
        if not a:
            abort(404)
        modelo = q1("SELECT * FROM nt_modelos WHERE codigo=?", (a["modelo_codigo"],))
        if not modelo:
            flash("Este ato não tem modelo associado.", "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        partes = [dict(p) for p in q(
            "SELECT * FROM nt_ato_partes WHERE ato_id=? ORDER BY testemunha, ordem",
            (ato_id,))]
        ctx = NT.contexto_jinja_partes(partes)
        from jinja2.sandbox import SandboxedEnvironment
        env = SandboxedEnvironment(autoescape=False)
        try:
            corpo_jinja = env.from_string(modelo["corpo"]).render(
                sv=dados_serventia(db.get_settings),
                lavrado_nome=a["lavrado_nome"] or usuario_nome(),
                lavrado_titulo=a["lavrado_titulo"] or usuario_funcao(),
                **ctx)
        except Exception as erro:                               # noqa: BLE001
            flash(f"O modelo tem um erro: {type(erro).__name__}: {erro}", "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        valores = {k: v for k, v in request.form.items() if k != "csrf_token"}
        # Campo do fecho aproveita as partes do formulário se veio em branco.
        if not (valores.get(NT.CHAVE_ASSINANTES) or "").strip():
            sugerido = NT.texto_dos_assinantes(partes)
            if sugerido:
                valores[NT.CHAVE_ASSINANTES] = sugerido
        try:
            corpo = preencher_modelo({"corpo": corpo_jinja}, valores)
        except Exception as erro:                               # noqa: BLE001
            flash(f"O modelo tem um erro: {type(erro).__name__}: {erro}", "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        # O QUE FOI DIGITADO FICA — relato #78. Ele volta na tela quando o
        # escrevente reabre o quadro para corrigir um campo.
        import json as _json
        with db.transaction() as con:
            con.execute("""UPDATE nt_atos
                              SET teor=?, teor_formato='html', modelo_valores=?
                            WHERE id=?""",
                        (corpo, _json.dumps(valores, ensure_ascii=False), ato_id))
        audit("NT_ATO_PREENCHIDO", "NT_ATO", ato_id,
              {"modelo": a["modelo_codigo"], "campos": len(valores)})
        faltam = pendencias_modelo(corpo)
        if faltam:
            flash(f"Teor montado, mas {len(faltam)} campo(s) continuam em branco: "
                  f"{', '.join(faltam[:6])}", "warning")
        else:
            flash("Teor montado a partir do modelo.", "success")
        return redirect(url_for("notas_ato", ato_id=ato_id))

    @app.route("/notas/atos/<int:ato_id>/traslado")
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_ato_traslado(ato_id):
        """O traslado que fica com a parte, em .odt."""
        a = q1("SELECT * FROM nt_atos WHERE id=?", (ato_id,))
        if not a:
            abort(404)
        if not (a["teor"] or "").strip():
            flash("O ato ainda não tem teor.", "warning")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        if (a["situacao"] or "") == "EM_LAVRATURA":
            # Traslado é cópia fiel do que está no livro. De ato que não está
            # em livro nenhum, o traslado sairia com "LIVRO — FOLHA —" e a
            # assinatura do tabelião embaixo. Isso é instrumento público de
            # ato inexistente.
            flash("Este ato ainda não foi lançado no livro. Não há do que "
                  "extrair traslado — lance-o primeiro.", "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        # AS ANOTACOES VAO NO TRASLADO, e e o ponto inteiro delas.
        #
        # Traslado de procuracao revogada que nao diz que foi revogada e copia
        # infiel do livro — e a Lei 8.935/1994, art. 6º, II, manda expedir
        # copia FIDEDIGNA. Era o que saia ate aqui, porque a margem nao existia.
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            anotacoes = NA.do_ato(con, ato_id)
            partes = [dict(p) for p in con.execute(
                "SELECT * FROM nt_ato_partes WHERE ato_id=? "
                "ORDER BY testemunha, ordem", (ato_id,)).fetchall()]

        lavrado_nome = a["lavrado_nome"] or usuario_nome()
        lavrado_titulo = a["lavrado_titulo"] or usuario_funcao()

        from jinja2.sandbox import SandboxedEnvironment
        from ri_web import data_por_extenso
        env = SandboxedEnvironment(autoescape=False)
        with db.connect() as _c:
            _modelo = MODELOS.corpo_de(_c, "NOTAS_TRASLADO")
        nome_modelo = None
        if a["modelo_codigo"]:
            mrow = q1("SELECT nome FROM nt_modelos WHERE codigo=?",
                      (a["modelo_codigo"],))
            nome_modelo = mrow["nome"] if mrow else None
        # O teor sem o bloco de assinaturas que `montar` possa ter gravado —
        # as linhas saem em @@ASSINATURAS@@, montadas ao vivo das partes.
        titulo_inst = titulo_do_instrumento(dict(a), nome_modelo=nome_modelo)
        teor_sem_ass = NT.teor_sem_titulos_duplicados(
            NT.sem_bloco_de_assinaturas(a["teor"]),
            _titulos_para_limpar_do_teor(dict(a), nome_modelo=nome_modelo))
        html = env.from_string(_modelo).render(
            a=dict(a), anotacoes=anotacoes,
            sv=dados_serventia(db.get_settings),
            rotulo_tipo=TIPOS_ATO.get(a["tipo"], a["tipo"]),
            titulo_do_instrumento=titulo_inst,
            data_extenso=data_por_extenso(date.today()),
            lavrado_nome=lavrado_nome,
            lavrado_titulo=lavrado_titulo)
        # O BRASÃO DA REPÚBLICA — pedido do oficial em 07/09/2026. O arquivo
        # já existia em `static/brasao.jpg` (usado na prévia em HTML da folha
        # do RCPN); aqui ele entra no `.odt` pelo mesmo mecanismo do QR do
        # selo (`ri_odt.bloco_selo_odf`) — a imagem vai dentro do pacote, em
        # `Pictures/`, e o `<draw:frame>` a referencia por lá.
        brasao = (Path(app.static_folder) / "brasao.jpg").read_bytes()
        # ESTE PARÁGRAFO ABRE A PÁGINA 1 SEM O CABEÇALHO DE PÁGINA — ver
        # `ESTILO_PAGINA_1` em `ri_odt.py`. Livro/Folha/Termo já aparecem
        # escritos no corpo, logo abaixo do endereço da serventia; o
        # cabeçalho de página só entra a partir da segunda.
        brasao_odf = (f'<text:p text:style-name="{ESTILO_PAGINA_1}">'
                     '<draw:frame draw:style-name="Fr-qr" text:anchor-type="as-char" '
                     'svg:width="2.5cm" svg:height="2.5cm">'
                     '<draw:image xlink:href="Pictures/brasao.jpg" '
                     'xlink:type="simple" xlink:show="embed" '
                     'xlink:actuate="onLoad"/></draw:frame></text:p>')
        # O teor JA E ODF quando chega aqui, e nao pode passar de novo pelo
        # conversor. O `fragmentos` do ri_odt existe para isto: troca o
        # PARAGRAFO INTEIRO que contem a marca. Na primeira versao eu troquei
        # so o texto da marca, e o resultado foi um <text:p> dentro de outro —
        # ODF invalido, que o LibreOffice descarta em silencio. O traslado saiu
        # bonito e sem o teor.
        # O CARIMBO COMPLETO DO SELO — pedido 18/09/2026: o traslado saía só
        # com o número (`Selo: {{ a.selo }}`); agora usa o mesmo carimbo das
        # certidões (QR, emolumentos, link), via `etiqueta_do_ato` +
        # `carimbo_da_certidao_odf`. Sem selo, o fragmento fica vazio.
        frag_do_selo = ""
        imagens_selo: dict = {}
        imagens_do_selo: dict = {}
        if (a["selo"] or "").strip():
            with db.connect() as con:
                etiqueta = AS.etiqueta_do_ato(
                    con, "nt_atos", ato_id, a["selo"]) or str(a["selo"]).strip()
            rotulo_selo = {
                "ESCRITURA": "SELO DA ESCRITURA",
                "PROCURACAO": "SELO DA PROCURAÇÃO",
                "PROCURACAO_PREVIDENCIARIA": "SELO DA PROCURAÇÃO",
                "SUBSTABELECIMENTO": "SELO DO SUBSTABELECIMENTO",
                "REVOGACAO": "SELO DA REVOGAÇÃO",
                "RENUNCIA": "SELO DA RENÚNCIA",
                "ATA": "SELO DA ATA",
                "ATA_USUCAPIAO": "SELO DA ATA",
                "TESTAMENTO": "SELO DO TESTAMENTO",
                "TESTAMENTO_CERRADO": "SELO DO TESTAMENTO",
            }.get(a["tipo"] or "", "SELO DO ATO")
            frag_do_selo, imagens_do_selo = carimbo_da_certidao_odf(
                etiqueta, rotulo=rotulo_selo,
                prefixo=f"qr-selo-traslado-{ato_id}")
        # AS ASSINATURAS — mesmo bloco do teor (`notas_teor.bloco_de_assinaturas`).
        ass_html = NT.bloco_de_assinaturas(
            partes, lavrado_nome=lavrado_nome, lavrado_titulo=lavrado_titulo)
        ass_odf = html_para_odf(ass_html) if (ass_html or "").strip() else ""
        # O teor JA E ODF quando chega aqui, e nao pode passar de novo pelo
        # conversor. O `fragmentos` do ri_odt existe para isto: troca o
        # PARAGRAFO INTEIRO que contem a marca. Na primeira versao eu troquei
        # so o texto da marca, e o resultado foi um <text:p> dentro de outro —
        # ODF invalido, que o LibreOffice descarta em silencio. O traslado saiu
        # bonito e sem o teor.
        corpo = html_para_odf(html, fragmentos={
            "@@TEOR@@": html_para_odf(teor_sem_ass),
            "@@BRASAO@@": brasao_odf,
            "@@SELO@@": frag_do_selo,
            "@@ASSINATURAS@@": ass_odf,
        })
        # LIVRO, FOLHA E TERMO NA PÁGINA 1 SAEM NO CORPO (acima); DA PÁGINA 2
        # EM DIANTE, PELO CABEÇALHO DE PÁGINA — pedido do oficial em
        # 07/09/2026, para não escrever a mesma coisa duas vezes bem no topo
        # da primeira página.
        cab_html = env.from_string(MODELO_TRASLADO_CABECALHO).render(a=dict(a))
        cab_odf = html_para_odf(cab_html, compacto=True)
        # A FOLHA MOSTRA A PÁGINA, E NÃO A FAIXA — «não a janela que a
        # escritura está usando». `a["folha"]` guarda o número inicial
        # gravado no lançamento (ex.: "1"); o ajuste faz a página 1 do PDF
        # já sair mostrando esse número, e as seguintes contarem dali.
        folha_ini = NL.inteiro(str(a["folha"] or "")) or 1
        imagens = {"brasao.jpg": (brasao, "image/jpeg")}
        imagens.update(imagens_do_selo)
        arquivo = gerar_odt(corpo, titulo=f"Traslado {ato_id}",
                           cabecalho_odf=cab_odf,
                           # Uma linha só — não precisa dos 3,2 cm da ficha
                           # do RI, nem do traço embaixo.
                           cabecalho_altura_min="0.6cm",
                           cabecalho_margem_baixo="0.2cm",
                           cabecalho_borda=False,
                           cabecalho_a_partir_da_pagina_2=True,
                           folha_livro_inicio=folha_ini,
                           imagens=imagens)
        audit("NT_TRASLADO", "NT_ATO", ato_id, {})
        return Response(arquivo, mimetype="application/vnd.oasis.opendocument.text",
                        headers={"Content-Disposition":
                                 f'attachment; filename="traslado-{ato_id}.odt"'})

    # A PÁGINA DO LIVRO SE MEDE, E NÃO SE PERGUNTA — 07/10/2026, pedido do
    # oficial: «consegue resolver o problema do escrevente precisar dizer
    # quantas páginas vai ter o ato? isso é uma informação confusa, deve ter
    # outra forma de garantir que o ato termine no verso para não continuar o
    # próximo no verso do anterior».
    #
    #   QUEM DECIDE A QUEBRA É O LIBREOFFICE, e o papel que vai ao livro é o
    #   termo que ESTA casa monta. Então a conta se faz no próprio termo: ele é
    #   montado, convertido em PDF e contado — a mesma régua da certidão, que
    #   conta as próprias folhas desde 22/09/2026 (`certidao_folhas.py`).
    #
    #   E O VERSO QUE SOBRA SAI NO MESMO ARQUIVO, JÁ INUTILIZADO. Terminando o
    #   texto na frente da última folha, o termo leva mais uma página — o traço,
    #   o dizer e a linha de assinatura de `notas_inutilizacao` — e por isso o
    #   arquivo tem sempre número PAR de páginas: imprime-se o termo inteiro,
    #   frente e verso, e o ato seguinte só pode começar em folha nova.
    #   Antes, o verso dependia de alguém lembrar de imprimir a face à parte.

    from ri_odt import ESTILOS_EXTRA
    ESTILO_QUEBRA_DE_PAGINA = "P-nova-pagina"
    ESTILOS_EXTRA.setdefault(
        ESTILO_QUEBRA_DE_PAGINA,
        f'<style:style style:name="{ESTILO_QUEBRA_DE_PAGINA}" '
        'style:family="paragraph" style:parent-style-name="P-centro">'
        '<style:paragraph-properties fo:break-before="page"/></style:style>')

    def _odt_do_termo_livro(a: dict, *, etiqueta: str | None = None,
                            faces_inutilizadas=()) -> bytes:
        """O termo que vai ao livro, em .odt. SO LE.

        `etiqueta` None usa o selo gravado no ato; texto dado é a etiqueta de
        AMOSTRA da medição, que acontece antes de o selo existir — o carimbo tem
        tamanho fixo, e sem ele a conta erraria por baixo. `faces_inutilizadas`
        são os versos que vão no fim, um por página, já riscados.
        """
        ato_id = a["id"]
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            partes = [dict(p) for p in con.execute(
                "SELECT * FROM nt_ato_partes WHERE ato_id=? "
                "ORDER BY testemunha, ordem", (ato_id,)).fetchall()]

        lavrado_nome = a["lavrado_nome"] or usuario_nome()
        lavrado_titulo = a["lavrado_titulo"] or usuario_funcao()

        from jinja2.sandbox import SandboxedEnvironment
        env = SandboxedEnvironment(autoescape=False)
        with db.connect() as _c:
            _modelo = MODELOS.corpo_de(_c, "NOTAS_TERMO_LIVRO")
        nome_modelo = None
        if a["modelo_codigo"]:
            mrow = q1("SELECT nome FROM nt_modelos WHERE codigo=?",
                      (a["modelo_codigo"],))
            nome_modelo = mrow["nome"] if mrow else None
        titulo_inst = titulo_do_instrumento(dict(a), nome_modelo=nome_modelo)
        teor_sem_ass = NT.teor_sem_titulos_duplicados(
            NT.sem_bloco_de_assinaturas(a["teor"]),
            _titulos_para_limpar_do_teor(dict(a), nome_modelo=nome_modelo))
        html = env.from_string(_modelo).render(
            a=dict(a),
            sv=dados_serventia(db.get_settings),
            rotulo_tipo=TIPOS_ATO.get(a["tipo"], a["tipo"]),
            titulo_do_instrumento=titulo_inst)

        brasao = (Path(app.static_folder) / "brasao.jpg").read_bytes()
        brasao_odf = (f'<text:p text:style-name="{ESTILO_PAGINA_1}">'
                     '<draw:frame draw:style-name="Fr-qr" text:anchor-type="as-char" '
                     'svg:width="2.5cm" svg:height="2.5cm">'
                     '<draw:image xlink:href="Pictures/brasao.jpg" '
                     'xlink:type="simple" xlink:show="embed" '
                     'xlink:actuate="onLoad"/></draw:frame></text:p>')

        frag_do_selo = ""
        # QR do carimbo ODT (aj_problemas #97, 22/09/2026).
        imagens_selo: dict = {}
        if etiqueta is None and (a["selo"] or "").strip():
            with db.connect() as con:
                etiqueta = AS.etiqueta_do_ato(
                    con, "nt_atos", ato_id, a["selo"]) or str(a["selo"]).strip()
        if (etiqueta or "").strip():
            rotulo_selo = {
                "ESCRITURA": "SELO DA ESCRITURA",
                "PROCURACAO": "SELO DA PROCURAÇÃO",
                "PROCURACAO_PREVIDENCIARIA": "SELO DA PROCURAÇÃO",
                "SUBSTABELECIMENTO": "SELO DO SUBSTABELECIMENTO",
                "REVOGACAO": "SELO DA REVOGAÇÃO",
                "RENUNCIA": "SELO DA RENÚNCIA",
                "ATA": "SELO DA ATA",
                "ATA_USUCAPIAO": "SELO DA ATA",
                "TESTAMENTO": "SELO DO TESTAMENTO",
                "TESTAMENTO_CERRADO": "SELO DO TESTAMENTO",
            }.get(a["tipo"] or "", "SELO DO ATO")
            # 22/09/2026 — QR + número + emolumentos no termo do livro.
            frag_do_selo = carimbo_compacto_odf(
                etiqueta, rotulo=rotulo_selo, imagens=imagens_selo)

        ass_html = NT.bloco_de_assinaturas(
            partes, lavrado_nome=lavrado_nome, lavrado_titulo=lavrado_titulo)
        ass_odf = html_para_odf(ass_html) if (ass_html or "").strip() else ""

        corpo = html_para_odf(html, fragmentos={
            "@@BRASAO@@": brasao_odf,
            "@@TEOR@@": html_para_odf(teor_sem_ass),
            "@@SELO@@": frag_do_selo,
            "@@ASSINATURAS@@": ass_odf,
        })
        if faces_inutilizadas:
            sv = _sv()
            extenso = _hoje_extenso()
            serie = a["serie"] or a["tipo"]
            dizer = NI.dizer(list(faces_inutilizadas), serie, a["livro"], sv,
                             extenso)
            for face in faces_inutilizadas:
                pagina = html_para_odf(NI.html_da_face(
                    face, serie, a["livro"], sv, extenso, dizer))
                # O primeiro parágrafo da face abre página nova: sem isso o
                # traço começaria logo abaixo das assinaturas, na mesma página.
                corpo += pagina.replace(
                    'text:style-name="P-centro"',
                    f'text:style-name="{ESTILO_QUEBRA_DE_PAGINA}"', 1)
        cab_html = env.from_string(MODELO_TRASLADO_CABECALHO).render(a=dict(a))
        cab_odf = html_para_odf(cab_html, compacto=True)
        folha_ini = NL.inteiro(str(a["folha"] or "")) or 1
        imagens = {"brasao.jpg": (brasao, "image/jpeg")}
        imagens.update(imagens_selo)
        return gerar_odt(corpo, titulo=f"Termo do livro {ato_id}",
                         cabecalho_odf=cab_odf,
                         cabecalho_altura_min="0.6cm",
                         cabecalho_margem_baixo="0.2cm",
                         cabecalho_borda=False,
                         cabecalho_a_partir_da_pagina_2=True,
                         folha_livro_inicio=folha_ini,
                         imagens=imagens)

    def _medir_paginas(odt: bytes) -> int:
        """As páginas que o LibreOffice desenha. Ponto único, para o teste
        trocar a medição sem precisar do LibreOffice."""
        return IPDF.paginas_do_odt(odt, get_setting=db.get_setting)

    app.extensions["notas_medir_paginas"] = _medir_paginas

    def _paginas_medidas_para_lancar(a: dict, *, arquivamento: bool) -> int:
        """Quantas páginas o termo deste ato terá no livro. MEDIDO, e só lê.

        Monta o termo como ele vai sair — com o livro, a folha e o termo que o
        lançamento vai dar, e um carimbo de selo de AMOSTRA (o selo só sai
        depois do lançamento, e o carimbo ocupa linhas) — e conta as páginas.
        Com o selo de arquivamento pedido, são dois carimbos.
        """
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            prev = NL.previsao(con, a["tipo"], 1)
            amostra = con.execute(
                """SELECT id, selo FROM nt_atos
                    WHERE selo IS NOT NULL AND selo <> ''
                    ORDER BY id DESC LIMIT 1""").fetchone()
            etiqueta = (AS.etiqueta_do_ato(con, "nt_atos", amostra["id"],
                                           amostra["selo"])
                        if amostra else "")
        if not (etiqueta or "").strip():
            # Casa sem um único ato de livro selado: a forma do texto que o
            # aparelho devolve, com os números do maior selo desta casa.
            etiqueta = ("PODER JUDICIÁRIO – TJMA SELO: ESCPUB000000XXXXXXXXXXXXXXXX "
                        "00/00/0000 00:00:00, ATO: 13.1.13, PARTE(S): "
                        "NOME DA PARTE OUTORGANTE E NOME DA PARTE OUTORGADA, "
                        "TOTAL R$ 1.074,88 EMOL R$ 959,68 FERC R$ 28,80 FADEP R$ 38,40 "
                        "FEMP R$ 38,40 FERRFIS R$ 9,60 CONSULTE EM HTTPS://SELO.TJMA.JUS.BR")
        if arquivamento:
            etiqueta = etiqueta + "\n" + etiqueta
        provisorio = dict(a)
        provisorio["livro"] = prev.get("livro") or prev.get("proximo_livro")
        provisorio["folha"] = NL.rotulo_folha(prev.get("folha_inicial") or 1)
        provisorio["termo"] = prev.get("termo")
        return app.extensions["notas_medir_paginas"](
            _odt_do_termo_livro(provisorio, etiqueta=etiqueta))

    def _faces_que_completam(a: dict, paginas_do_texto: int) -> list[str]:
        """Os versos que faltam para o termo fechar as folhas reservadas.

        A página `k` do termo é a folha `inicial + (k-1)//2`, frente quando `k`
        é ímpar. O lançamento reservou `folhas` folhas inteiras; o que o texto
        não ocupa sai inutilizado no fim do mesmo arquivo.
        """
        inicio = NL.inteiro(a["folha_inicial_num"]) or NL.inteiro(str(a["folha"] or ""))
        folhas = NL.inteiro(a["folhas"]) or 0
        if not inicio or not folhas:
            return []
        faces = []
        for k in range(paginas_do_texto + 1, folhas * NL.PAGINAS_POR_FOLHA + 1):
            faces.append(NL.rotulo_folha(inicio + (k - 1) // NL.PAGINAS_POR_FOLHA,
                                         verso=(k % NL.PAGINAS_POR_FOLHA == 0)))
        return faces

    @app.route("/notas/atos/<int:ato_id>/termo-livro")
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_ato_termo_livro(ato_id):
        """O termo que vai para o livro, em .odt.

        NAO E O TRASLADO (via da parte) nem o rascunho (`teor.odt`). E o
        instrumento com o mesmo cabeçalho do traslado (brasão e serventia), o mesmo teor, as mesmas linhas de
        assinatura dos comparecentes (`bloco_de_assinaturas`) e o carimbo
        compacto do selo COM QR, número e emolumentos (pedido da
        substituta em 22/09/2026). Entre o carimbo e as assinaturas há
        espaço em branco para a caneta.

        E SAI FECHANDO AS FOLHAS QUE O LANÇAMENTO RESERVOU (07/10/2026): o
        verso que o texto não ocupa vai no fim do mesmo arquivo, já
        inutilizado. Se o texto passar do que foi reservado, o arquivo NÃO
        sai — imprimi-lo escreveria por cima da folha do ato seguinte.
        """
        a = q1("SELECT * FROM nt_atos WHERE id=?", (ato_id,))
        if not a:
            abort(404)
        if not (a["teor"] or "").strip():
            flash("O ato ainda não tem teor.", "warning")
            return redirect(url_for("notas_ato", ato_id=ato_id))
        if (a["situacao"] or "") == "EM_LAVRATURA":
            flash("Este ato ainda não foi lançado no livro. Não há termo de "
                  "livro para baixar — lance-o primeiro.", "danger")
            return redirect(url_for("notas_ato", ato_id=ato_id))

        a = dict(a)
        arquivo = _odt_do_termo_livro(a)
        reservadas = (NL.inteiro(a["folhas"]) or 0) * NL.PAGINAS_POR_FOLHA
        if reservadas:
            try:
                paginas = app.extensions["notas_medir_paginas"](arquivo)
            except IPDF.PdfError:
                # Sem medir, vale o que o lançamento gravou: com o verso em
                # branco declarado, ele vai inutilizado no fim.
                paginas = reservadas - len(NI.faces_do_ato(a))
            if paginas > reservadas:
                flash(f"O termo saiu com {paginas} página(s), e o livro reservou "
                      f"{reservadas} para este ato (folha {a['folha']} a "
                      f"{a['folha_final']}). Imprimi-lo escreveria na folha do "
                      f"ato seguinte. NÃO imprima: chame o oficial — o texto "
                      f"mudou depois do lançamento, ou o selo ocupou mais do "
                      f"que a medição previu.", "danger")
                audit("NT_TERMO_LIVRO_EXCEDE", "NT_ATO", ato_id,
                      {"paginas": paginas, "reservadas": reservadas})
                return redirect(url_for("notas_ato", ato_id=ato_id))
            faces = _faces_que_completam(a, paginas)
            if faces:
                arquivo = _odt_do_termo_livro(a, faces_inutilizadas=faces)
        audit("NT_TERMO_LIVRO", "NT_ATO", ato_id, {})
        return Response(arquivo, mimetype="application/vnd.oasis.opendocument.text",
                        headers={"Content-Disposition":
                                 f'attachment; filename="termo-livro-{ato_id}.odt"'})

    # =================================================== painel e importacao

    @app.route("/notas")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_painel():
        hoje = date.today().isoformat()
        resumo = {
            "cartoes": q1("SELECT COUNT(*) n FROM nt_cartoes")["n"],
            "reconhecimentos": q1("SELECT COUNT(*) n FROM nt_reconhecimentos")["n"],
            "autenticacoes": q1("SELECT COUNT(*) n FROM nt_autenticacoes")["n"],
            "atos": q1("SELECT COUNT(*) n FROM nt_atos")["n"],
            "modelos": q1("SELECT COUNT(*) n FROM nt_modelos WHERE ativo=1")["n"],
            "rec_hoje": q1("SELECT COUNT(*) n FROM nt_reconhecimentos WHERE data=?",
                           (hoje,))["n"],
            "aut_hoje": q1("SELECT COUNT(*) n FROM nt_autenticacoes WHERE data=?",
                           (hoje,))["n"],
            "sem_selo": q1("""SELECT COUNT(*) n FROM nt_reconhecimentos
                              WHERE (selo IS NULL OR selo='') AND cancelado=0""")["n"],
            # Ato aberto e nunca lançado no livro. Não vai a central nenhuma e
            # não ocupa folha — mas também não existe para o mundo. É o que
            # some da vista se ninguém contar.
            "em_lavratura": q1("""SELECT COUNT(*) n FROM nt_atos
                                  WHERE situacao='EM_LAVRATURA'""")["n"],
            # Revogação lavrada e procuração ainda sem a anotação à margem.
            # É a pergunta que a correição faz, e a resposta tem de ser zero.
            "anotacao_pendente": q1(
                f"""SELECT COUNT(*) n FROM nt_atos a
                    WHERE a.tipo IN ({','.join('?' * len(ATO_PEDE_ANOTACAO))})
                      AND a.situacao NOT IN ('EM_LAVRATURA','CANCELADO')
                      AND NOT EXISTS (SELECT 1 FROM nt_ato_anotacoes n
                                      WHERE n.ato_relacionado_id = a.id)""",
                tuple(ATO_PEDE_ANOTACAO))["n"],
            "livro_acabando": q1(
                """SELECT COUNT(*) n FROM nt_livros
                   WHERE ativo=1 AND encerrado=0 AND folhas IS NOT NULL
                     AND (COALESCE(folha_inicial,1) + folhas
                          - COALESCE(folha_atual, 1)) <= 10""")["n"],
        }
        atos = q("""SELECT tipo, COUNT(*) n FROM nt_atos GROUP BY tipo ORDER BY n DESC""")
        return render_template("notas_painel.html", resumo=resumo, atos=atos,
                               TIPOS_ATO=TIPOS_ATO, TIPOS_LIVRO=TIPOS_LIVRO)

    @app.route("/notas/importar", methods=["GET", "POST"])
    @roles_required("ADMIN")
    def notas_importar():
        """Traz o acervo do E-Ofício. Pode rodar quantas vezes precisar."""
        from ri_web import procurar_arquivos
        if request.method == "POST":
            pasta = (request.form.get("pasta") or "").strip()
            if not pasta:
                achados = procurar_arquivos("firma_cartao.jsonl", limite=3)
                pasta = str(achados[0].parent) if achados else ""
            if not pasta or not Path(pasta).is_dir():
                flash("Não encontrei a pasta EXPORT_NOTAS_EOFICIO. Informe o caminho.",
                      "danger")
                return redirect(url_for("notas_importar"))
            from notas_import import importar as importar_notas
            try:
                with db.transaction() as con:
                    resultado = importar_notas(con, pasta)
            except Exception as erro:                              # noqa: BLE001
                flash(f"A carga falhou: {type(erro).__name__}: {erro}", "danger")
                return redirect(url_for("notas_importar"))
            # Desempate de folha do acervo, logo depois da carga.
            #
            # A CENSEC identifica o ato por (livro, livroComplemento, folha,
            # folhaComplemento). O acervo tem pares de atos na MESMA folha do
            # mesmo livro — reais, herdados do E-Ofício. Sem complemento, a
            # central recusa os dois por duplicidade. A coluna existia, o
            # `notas_censec.py` já a lia, e nada jamais a escrevia.
            #
            # Roda aqui porque só faz sentido depois de o acervo estar dentro,
            # e é idempotente: recarregar não remexe no que já foi desempatado.
            with db.transaction() as con:
                desempatadas = NL.desambiguar_folhas_do_acervo(con)
            if desempatadas:
                resultado["folhas_desempatadas"] = desempatadas

            # Reconcilia a folha corrente de cada livro trazido do acervo: o
            # E-Ofício manda `intFolha`, mas quem manda é o maior número de
            # folha realmente ocupado pelos atos daquele livro.
            with db.transaction() as con:
                for r in con.execute(
                        "SELECT id FROM nt_livros WHERE ativo=1 AND encerrado=0"):
                    NL.sincronizar_folha_atual(con, r["id"])

            # A biblioteca de modelos entra junto, e e repetivel: o modelo que a
            # serventia editar a mao continua valendo.
            with db.transaction() as con:
                modelos = NMOD.instalar(con, datetime.now().isoformat(timespec="seconds"))
            if modelos["novos"]:
                resultado["modelos_do_sistema"] = modelos["novos"]
            if modelos["atualizados"]:
                resultado["modelos_atualizados_para_o_padrao"] = modelos["atualizados"]
            db.set_settings({"nt_pasta_export": pasta})
            novos = {k: v for k, v in resultado.items()
                     if "ja_existentes" not in k and not k.startswith("rejeitados")}
            audit("NT_IMPORTADO", "NT_IMPORTACAO", None, resultado)
            flash("Carga concluída. " + (", ".join(f"{v} {k}" for k, v in sorted(novos.items()))
                                         or "nada novo entrou."), "success")
            return redirect(url_for("notas_painel"))

        achados = procurar_arquivos("firma_cartao.jsonl", limite=3)
        sugestao = str(achados[0].parent) if achados else \
            db.get_setting("nt_pasta_export", "")
        anteriores = q("""SELECT * FROM nt_importacoes ORDER BY id DESC LIMIT 5""")
        rejeitados = q("""SELECT tabela, COUNT(*) n FROM nt_rejeitados
                          GROUP BY tabela ORDER BY n DESC""")
        return render_template("notas_importar.html", sugestao=sugestao,
                               anteriores=anteriores, rejeitados=rejeitados)

    # ================================== pendencias das escrituras do acervo
    #
    # Duas coisas que so o registrador pode resolver, e que hoje seguram a
    # remessa a CEP:
    #
    #   1. O VALOR. `curValorTransacao` veio nulo nas 45 escrituras do
    #      E-Oficio. Na escritura o valor e o conteudo economico do ato — nao
    #      da para zerar como se faz na procuracao.
    #
    #   2. AS PARTES DE PROTOCOLO REPETIDO. Oito escrituras vieram de tres
    #      protocolos que rendem mais de um ato. As partes estao na quarentena
    #      porque o sistema nao sabe quem compareceu a qual, e adivinhar seria
    #      inventar quem esteve na sala.
    #
    # A tela mostra as duas juntas porque sao a mesma sessao de trabalho: o
    # registrador abre a escritura no papel e resolve as duas de uma vez.

    @app.route("/notas/escrituras/pendentes")
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_escrituras_pendentes():
        # PENDENCIA E DO QUE AINDA SE PODE FAZER — decisao do oficial em
        # 27/08/2026: «pendencias antigas e do e-oficio nao devem aparecer. Sao
        # atos que ja passaram, nao tem mais relevancia e nao devem constar mais
        # como pendencias atuais».
        #
        #   Medido: sao **47 escrituras sem valor**, e **45 vieram do
        #   E-Oficio** — 25 de 2020, 17 de 2022, 1 de 2023. A remessa daquelas
        #   saiu no tempo delas, pelo E-Oficio. Sao historia, e nao trabalho.
        #
        #   As duas que este sistema lavrou (17/08 e 27/08/2026) sao a
        #   pendencia de verdade, e eram as que se perdiam no meio das 45.
        #
        # NAO SE ESCONDE, SE SEPARA. Lista de quarenta e cinco itens que nunca
        # diminuem faz ninguem olhar a lista; apagar as quarenta e cinco faria
        # perder o que ainda pode ser corrigido no dia em que alguem precisar.
        # Elas ficam num quadro proprio, fechado, dizendo o que sao.
        def _partir_por_origem(linhas, chave=lambda x: x["origem"]):
            """Do sistema primeiro; do acervo depois."""
            nossas, do_acervo = [], []
            for x in linhas:
                (do_acervo if (chave(x) or "") == "EOFICIO" else nossas).append(x)
            return nossas, do_acervo

        todas_sem_valor = q("""SELECT a.id, a.data, a.livro, a.folha, a.natureza,
                                a.interessado, a.origem, a.origem_chave,
                                (SELECT COUNT(*) FROM nt_ato_partes p
                                  WHERE p.ato_id = a.id) partes
                           FROM nt_atos a
                          WHERE a.tipo = 'ESCRITURA' AND a.valor_transacao IS NULL
                          ORDER BY a.data DESC, a.id DESC""")
        sem_valor, sem_valor_do_acervo = _partir_por_origem(todas_sem_valor)

        # A CLASSIFICAÇÃO NÃO SE MEDE POR ESTAR VAZIA, E SIM POR ESTAR CERTA.
        #
        #     Filtrar `natureza_censec IS NULL` mostrava zero escrituras — e
        #     escondia o problema inteiro. As 45 JÁ ESTÃO classificadas, todas
        #     pelo modelo genérico do E-Ofício: 40 como ACORDO EXTRAJUDICIAL,
        #     que nenhuma é, e as 5 de divórcio como Separação.
        #
        #     Então a tela lista o que o teor CONTRADIZ, e não o que está em
        #     branco. Ato em branco também entra, claro.
        sem_natureza = []
        for r in q("""SELECT id, data, livro, folha, natureza_censec, tipo_cesdi,
                             origem, teor FROM nt_atos
                       WHERE tipo='ESCRITURA' ORDER BY data, id"""):
            s = NNAT.sugerir(r["teor"])
            vazio = r["natureza_censec"] is None and r["tipo_cesdi"] is None
            diverge = (
                (s["natureza_censec"] and s["natureza_censec"] != r["natureza_censec"])
                or (s["tipo_cesdi"] and s["tipo_cesdi"] != r["tipo_cesdi"])
                or bool(s["outro_tipo"])
            )
            if vazio or diverge:
                sem_natureza.append({"ato": dict(r) | {"teor": None},
                                     "sugestao": s, "diverge": bool(diverge)})
        sem_natureza, sem_natureza_do_acervo = _partir_por_origem(
            sem_natureza, chave=lambda x: x["ato"]["origem"])

        # UM ATO, UMA LINHA — e o quadro do acervo conta ATOS, e não faltas.
        #
        #   A escritura que está sem valor E sem natureza cai nas duas listas.
        #   Somando as duas, o quadro diria «20 escrituras» havendo 10 — e
        #   número que não bate com a lista embaixo dele é o tipo de coisa que
        #   faz a pessoa deixar de confiar na tela inteira.
        do_acervo = {}
        for e in sem_valor_do_acervo:
            do_acervo.setdefault(e["id"], {"ato": dict(e), "falta": []})
            do_acervo[e["id"]]["falta"].append("valor declarado")
        for x in sem_natureza_do_acervo:
            a = x["ato"]
            do_acervo.setdefault(a["id"], {"ato": dict(a), "falta": []})
            do_acervo[a["id"]]["falta"].append(
                "natureza da CENSEC — a classificação do E-Ofício contradiz o teor"
                if x["diverge"] else "natureza da CENSEC")
        do_acervo = sorted(do_acervo.values(),
                           key=lambda x: (x["ato"]["data"] or "", x["ato"]["id"]),
                           reverse=True)
        # O RESUMO CONTINUA SENDO DE TODAS, e de propósito: ele é o retrato da
        # classificação da casa, e o acervo faz parte dela.
        resumo_natureza = NNAT.resumo(
            [x["sugestao"] for x in sem_natureza + sem_natureza_do_acervo])
        # A quarentena guarda o protocolo em `chave` e o resto no conteudo.
        brutos = q("""SELECT id, chave, motivo, conteudo FROM nt_rejeitados
                       WHERE tabela = 'nt_ato_partes' AND motivo LIKE '%protocolo%'
                       ORDER BY chave, id""")
        ambiguas = []
        for r in brutos:
            try:
                dados = json.loads(r["conteudo"] or "{}")
            except ValueError:
                dados = {}
            ato_id = dados.get("ato_id")
            if ato_id and q1("SELECT 1 FROM nt_ato_partes WHERE ato_id=?", (ato_id,)):
                continue        # ja foi resolvida
            # Troca o cartao pelo nome: quem decide precisa ver a pessoa.
            partes = []
            for p in (dados.get("partes") or []):
                cartao_id = p.get("cartao_id") if isinstance(p, dict) else None
                nome = None
                if cartao_id:
                    achado = q1("SELECT nome, documento FROM nt_cartoes WHERE id=?",
                                (cartao_id,))
                    nome = achado["nome"] if achado else None
                partes.append({
                    "cartao_id": cartao_id,
                    "papel": p.get("papel") if isinstance(p, dict) else str(p),
                    "nome": nome or "— cartão não encontrado —",
                })
            # Os atos que o protocolo rendeu, para o registrador escolher.
            irmaos = q("""SELECT id, data, livro, folha FROM nt_atos
                           WHERE tipo='ESCRITURA' AND origem_chave IN (
                               SELECT origem_chave FROM nt_atos WHERE id=?)
                           OR (tipo='ESCRITURA' AND livro=? AND folha=?)
                           ORDER BY folha, id""", (ato_id, dados.get("livro"),
                                                   dados.get("folha")))
            ambiguas.append({"id": r["id"], "protocolo": r["chave"],
                             "motivo": r["motivo"], "ato_id": ato_id,
                             "livro": dados.get("livro"), "folha": dados.get("folha"),
                             "partes": partes, "irmaos": irmaos})
        return render_template("notas_escrituras_pendentes.html",
                               sem_valor=sem_valor, ambiguas=ambiguas,
                               sem_natureza=sem_natureza,
                               do_acervo=do_acervo,
                               resumo_natureza=resumo_natureza,
                               NATUREZA=NC.NATUREZA_ESCRITURA,
                               TIPO_CESDI=NC.TIPO_ATO_CESDI,
                               reais=reais)

    @app.route("/notas/escrituras/natureza", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_escrituras_natureza():
        """Grava a classificação que o registrador confirmou.

        Aceita o lote: a tela oferece "confirmar as 24 compras e venda", e ele
        confere duas ou três antes de marcar. O sistema não classifica sozinho
        — só grava o que foi confirmado.
        """
        escolhas = request.form.getlist("ato")
        if not escolhas:
            flash("Nada foi marcado.", "warning")
            return redirect(url_for("notas_escrituras_pendentes"))
        gravados = 0
        with db.transaction() as con:
            for bruto in escolhas:
                ato_id, campo, valor = bruto.split("|", 2)
                if campo == "cep":
                    con.execute("""UPDATE nt_atos SET natureza_censec=?,
                                       tipo_cesdi=NULL WHERE id=? AND tipo='ESCRITURA'""",
                                (int(valor), int(ato_id)))
                elif campo == "cesdi":
                    # Vai para a CESDI: a natureza da CEP tem de sair junto,
                    # senão o ato aparece nas duas centrais.
                    con.execute("""UPDATE nt_atos SET tipo_cesdi=?,
                                       natureza_censec=NULL
                                     WHERE id=? AND tipo='ESCRITURA'""",
                                (int(valor), int(ato_id)))
                elif campo == "tipo":
                    con.execute("UPDATE nt_atos SET tipo=? WHERE id=?",
                                (valor, int(ato_id)))
                else:
                    continue
                gravados += 1
        audit("NT_NATUREZA_CLASSIFICADA", "NT_ATO", None, {"atos": gravados})
        flash(f"{gravados} ato(s) classificados.", "success")
        return redirect(url_for("notas_escrituras_pendentes"))

    @app.route("/notas/escrituras/<int:ato_id>/valor", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_escritura_valor(ato_id):
        """Lanca o valor declarado no ato. Em centavos, como o resto do sistema."""
        bruto = (request.form.get("valor") or "").strip()
        digitos = "".join(c for c in bruto if c.isdigit())
        if not digitos:
            flash("Informe o valor declarado no ato.", "danger")
            return redirect(url_for("notas_escrituras_pendentes"))
        centavos = int(digitos)          # a tela envia em centavos
        with db.transaction() as con:
            con.execute("UPDATE nt_atos SET valor_transacao=? WHERE id=? "
                        "AND tipo='ESCRITURA'", (centavos, ato_id))
        audit("NT_ESCRITURA_VALOR", "NT_ATO", ato_id, {"valor_transacao": centavos})
        flash(f"Valor de {reais(centavos)} lançado na escritura.", "success")
        return redirect(url_for("notas_escrituras_pendentes"))

    @app.route("/notas/escrituras/quarentena/<int:rejeitado_id>", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_escritura_partes_ambiguas(rejeitado_id):
        """Prende as partes da quarentena ao ato que o registrador indicar.

        O sistema nao escolhe: a tela lista as partes do protocolo e os atos que
        ele rendeu, e quem marca e quem leu o livro.
        """
        linha = q1("SELECT * FROM nt_rejeitados WHERE id=?", (rejeitado_id,))
        if not linha:
            abort(404)
        try:
            dados = json.loads(linha["conteudo"] or "{}")
        except ValueError:
            dados = {}
        ato_id = int(request.form.get("ato_id") or dados.get("ato_id") or 0)
        escolhidas = request.form.getlist("parte")
        if not ato_id or not escolhidas:
            flash("Escolha o ato e ao menos uma parte.", "danger")
            return redirect(url_for("notas_escrituras_pendentes"))

        agora = datetime.now().isoformat(timespec="seconds")
        with db.transaction() as con:
            for ordem, bruto in enumerate(escolhidas, 1):
                cartao_id, qualificacao = bruto.split("|", 1)
                cartao = con.execute(
                    "SELECT nome, documento, tipo_pessoa FROM nt_cartoes WHERE id=?",
                    (int(cartao_id),)).fetchone()
                if not cartao:
                    continue
                con.execute(
                    """INSERT INTO nt_ato_partes
                       (ato_id, cartao_id, nome, nome_norm, documento, tipo_pessoa,
                        qualificacao, testemunha, ordem, criado_em)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (ato_id, int(cartao_id), cartao[0], NP.normalizar(cartao[0]),
                     cartao[1], cartao[2] or "F", qualificacao,
                     1 if qualificacao.upper() == "TESTEMUNHA" else 0, ordem, agora))
        audit("NT_PARTES_DISTRIBUIDAS", "NT_ATO", ato_id,
              {"quarentena": rejeitado_id, "partes": len(escolhidas)})
        flash(f"{len(escolhidas)} parte(s) lançadas na escritura.", "success")
        return redirect(url_for("notas_escrituras_pendentes"))

    # ============================================ remessa as centrais (CENSEC)
    #
    # A CENSEC fecha por quinzena, nao por mes: 1a do dia 01 ao 15, 2a do 16 ao
    # fim, com prazo ate o dia 5 e o dia 20 (Provimento CNJ 149/2023, art. 267).
    # A tela e organizada por quinzena por isso, e nao por gosto.
    #
    # A conta que a tela mostra e a MESMA que gera o arquivo — notas_censec.separar.
    # Duas contas parecidas acabariam divergindo, e a tela diria uma coisa
    # enquanto o arquivo levaria outra.

    def _cns_da_serventia() -> str:
        return (db.get_setting("ri_cns", "")
                or dados_serventia(db.get_settings)["ri_cns"])

    @app.route("/notas/remessas")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_remessas():
        """A fila: o que esta pendente em cada central, por quinzena."""
        hoje = date.today()
        ano = int(request.args.get("ano") or hoje.year)
        mes = int(request.args.get("mes") or hoje.month)
        quinzena = int(request.args.get("quinzena")
                       or NC.quinzena_de(hoje.isoformat())[2])

        painel = []
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            for central in CENTRAIS_COM_REMESSA:
                separado = NC.separar(con, central, ano, mes, quinzena)
                painel.append({
                    "central": central,
                    "nome": CENTRAIS[central],
                    "aptos": len(separado["aptos"]),
                    "impedidos": len(separado["impedidos"]),
                    "resumo": NC.resumo_impedimentos(separado["impedidos"]),
                    "periodo_inicio": separado["periodo_inicio"],
                    "periodo_fim": separado["periodo_fim"],
                    "prazo": separado["prazo"],
                })

        remessas = q("""SELECT * FROM nt_remessas ORDER BY id DESC LIMIT 20""")
        # QUAL CHAVE DA API ESTÁ INFORMADA — sem o segredo, só «sim» ou «não».
        chaves_censec = {amb: CRED.tem(CRED.CENSEC, amb)
                         for amb in CRED.ambientes_de(CRED.CENSEC)}
        return render_template(
            "notas_remessas.html", painel=painel, remessas=remessas,
            ano=ano, mes=mes, quinzena=quinzena, MESES=NC.MESES,
            hoje=hoje.isoformat(), atrasada=NC.prazo_de_fechamento(ano, mes, quinzena)
            < hoje.isoformat(), envelope_conferido=NC.ENVELOPE_CONFERIDO,
            SITUACOES_REMESSA=SITUACOES_REMESSA, chaves_censec=chaves_censec,
            aptos_total=sum(c["aptos"] for c in painel))

    @app.route("/notas/remessas/enviar-api", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def notas_remessa_enviar_api():
        """Envia a quinzena à CENSEC pela API (`POST /api/cargas/upload-json`).

        **CONFERIR E ENVIAR SÃO DOIS PASSOS**, como na remessa da CRA: a tela
        mostra o que está apto e o que está impedido, e só então alguém clica.
        **Em homologação nada se grava** em `nt_remessas` — o ato testado não
        pode sumir da fila da produção. Na produção a remessa e cada item ficam
        registrados com o que a Central respondeu, e o ato recusado volta.
        """
        ano = int(request.form.get("ano"))
        mes = int(request.form.get("mes"))
        quinzena = int(request.form.get("quinzena"))
        ambiente = (request.form.get("ambiente") or CRED.HOMOLOGACAO).upper()
        volta = redirect(url_for("notas_remessas", ano=ano, mes=mes, quinzena=quinzena))
        if ambiente not in CAPI.BASE_DO_AMBIENTE:
            abort(400)
        try:
            r = CAPI.enviar_quinzena(db, ano, mes, quinzena, cns=_cns_da_serventia(),
                                     ambiente=ambiente, por=usuario_nome() or "")
        except (CAPI.CensecError, CRED.CredencialError) as erro:
            audit("NT_REMESSA_API_RECUSADA", "NT_REMESSA", None,
                  {"ambiente": ambiente, "ano": ano, "mes": mes,
                   "quinzena": quinzena, "motivo": str(erro)[:500]})
            flash(str(erro), "danger")
            return volta
        linhas = []
        for central, res in r["por_central"].items():
            if central not in r["atos"]:
                continue
            texto = (f"{central}: {len(r['atos'][central])} ato(s), "
                     f"{'aceita' if res['sucesso'] else 'RECUSADA'}"
                     f" — situação na CENSEC: {res.get('situacao') or '?'}")
            if res.get("erro"):
                texto += f" ({res['erro']})"
            if res.get("recusas"):
                texto += "; recusados: " + ", ".join(
                    f"livro {x['livro']} fl. {x['folha']}" for x in res["recusas"][:10])
            linhas.append(texto)
        audit("NT_REMESSA_API", "NT_REMESSA",
              r["remessas"][0]["id"] if r["remessas"] else None,
              {"ambiente": ambiente, "ano": ano, "mes": mes, "quinzena": quinzena,
               "por_central": r["por_central"], "remessas": r["remessas"]})
        prefixo = ("[HOMOLOGAÇÃO — nada foi marcado como enviado] "
                   if ambiente != CRED.PRODUCAO else "")
        flash(prefixo + " · ".join(linhas)
              + (" A situação «AguardandoValidacao» quer dizer que a CENSEC importou "
                 "e ainda vai validar: confira o resultado final na tela dela."
                 if any(x.get("situacao") == "AguardandoValidacao"
                        for x in r["por_central"].values()) else ""),
              "success" if all(x["sucesso"] for x in r["por_central"].values())
              else "warning")
        return volta

    @app.route("/notas/remessas/<central>/pendencias")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_remessa_pendencias(central):
        """Ato por ato, o que falta. E daqui que sai a lista de trabalho."""
        central = central.upper()
        if central not in CENTRAIS_COM_REMESSA:
            abort(404)
        hoje = date.today()
        ano = int(request.args.get("ano") or hoje.year)
        mes = int(request.args.get("mes") or hoje.month)
        quinzena = int(request.args.get("quinzena")
                       or NC.quinzena_de(hoje.isoformat())[2])
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            separado = NC.separar(con, central, ano, mes, quinzena)
        return render_template("notas_remessa_pendencias.html",
                               central=central, nome=CENTRAIS[central],
                               separado=separado, ano=ano, mes=mes,
                               quinzena=quinzena, MESES=NC.MESES)

    @app.route("/notas/remessas/<central>/gerar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_remessa_gerar(central):
        """Gera o arquivo da quinzena e registra a remessa.

        A gravacao acontece dentro da transacao, com a contagem tirada do
        proprio arquivo: se o gerador e o registro discordarem, ninguem
        descobre depois olhando o relatorio.
        """
        central = central.upper()
        if central not in CENTRAIS_COM_REMESSA:
            abort(404)
        ano = int(request.form.get("ano"))
        mes = int(request.form.get("mes"))
        quinzena = int(request.form.get("quinzena"))
        agora = datetime.now().isoformat(timespec="seconds")

        with db.transaction() as con:
            con.row_factory = sqlite3.Row
            carga = NC.gerar(con, central, ano, mes, quinzena, _cns_da_serventia())
            if not carga["aptos"]:
                flash(f"Nenhum ato apto na {quinzena}ª quinzena de "
                      f"{NC.MESES[mes]}/{ano}. Veja as pendências.", "warning")
                return redirect(url_for("notas_remessa_pendencias", central=central,
                                        ano=ano, mes=mes, quinzena=quinzena))
            cur = con.execute(
                """INSERT INTO nt_remessas(central, competencia, ano_referencia,
                       mes_referencia, quinzena, periodo_inicio, periodo_fim,
                       situacao, quantidade, arquivo_nome, arquivo_sha256,
                       gerada_em, gerada_por, criado_em)
                   VALUES (?,?,?,?,?,?,?,'GERADA',?,?,?,?,?,?)""",
                (central, f"{ano:04d}-{mes:02d}", ano, mes, quinzena,
                 carga["periodo_inicio"], carga["periodo_fim"], carga["quantidade"],
                 carga["arquivo_nome"], carga["sha256"], agora, usuario_nome(), agora))
            remessa_id = cur.lastrowid
            for item in carga["aptos"]:
                con.execute("""INSERT INTO nt_remessa_itens(remessa_id, ato_id,
                                   situacao, criado_em) VALUES (?,?,'GERADA',?)""",
                            (remessa_id, item["ato"]["id"], agora))

        audit("NT_REMESSA_GERADA", "NT_REMESSA", remessa_id,
              {"central": central, "quantidade": carga["quantidade"],
               "sha256": carga["sha256"]})
        return Response(
            carga["texto"], mimetype="application/json; charset=utf-8",
            headers={"Content-Disposition":
                     f'attachment; filename="{carga["arquivo_nome"]}"'})

    @app.route("/notas/remessas/<int:remessa_id>/situacao", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_remessa_situacao(remessa_id):
        """Registra o que a central respondeu.

        Confirmada, o ato nao volta na proxima quinzena. Rejeitada, volta — que
        e o ponto de guardar item por item, e nao so o total da remessa.
        """
        situacao = (request.form.get("situacao") or "").upper()
        if situacao not in SITUACOES_REMESSA:
            abort(400)
        protocolo = (request.form.get("protocolo") or "").strip()
        mensagem = (request.form.get("mensagem") or "").strip()
        agora = datetime.now().isoformat(timespec="seconds")

        if situacao == "ENVIADA" and not NC.ENVELOPE_CONFERIDO:
            flash("Antes de marcar como enviada, confirme os nomes das listas do "
                  "envelope na documentação da CENSEC — vide notas_censec.py, "
                  "ENVELOPE_CHAVES. É o único ponto do layout que não pude "
                  "conferir contra fonte primária.", "warning")

        with db.transaction() as con:
            con.execute("""UPDATE nt_remessas SET situacao=?, protocolo_central=?,
                               mensagem=?, enviada_em=COALESCE(enviada_em, ?),
                               enviada_por=COALESCE(enviada_por, ?)
                           WHERE id=?""",
                        (situacao, protocolo or None, mensagem or None,
                         agora if situacao in ("ENVIADA", "CONFIRMADA") else None,
                         usuario_nome() if situacao in ("ENVIADA", "CONFIRMADA")
                         else None, remessa_id))
            con.execute("""UPDATE nt_remessa_itens SET situacao=?, mensagem=?
                           WHERE remessa_id=?""",
                        (situacao, mensagem or None, remessa_id))
        audit("NT_REMESSA_SITUACAO", "NT_REMESSA", remessa_id,
              {"situacao": situacao, "protocolo": protocolo})
        flash(f"Remessa marcada como {SITUACOES_REMESSA[situacao].lower()}.", "success")
        return redirect(url_for("notas_remessas"))


    # ===================================================== sinal publico
    #
    # ABERTURA NAO SELA — oficial, 07/09/2026. So metadados + PDF da central
    # (upload manual na fatia 1: nao ha cliente CNSIP no codigo).
    #
    # RECONHECIMENTO AUTONOMO sela com item 413 (mesmo «sinal, letra e firma»).
    # O checkbox «reconhecer tambem o sinal» no reconhecimento de firma NAO muda.

    def pasta_sinais() -> Path:
        """`arquivos/notas/sinais/` — mesma raiz que firmas e fichas do RI."""
        raiz = Path(db.get_setting("archive_root", "").strip()
                    or (Path(db.db_path).parent / "arquivos"))
        destino = raiz / "notas" / "sinais"
        destino.mkdir(parents=True, exist_ok=True)
        return destino

    def archive_root() -> Path:
        return Path(db.get_setting("archive_root", "").strip()
                    or (Path(db.db_path).parent / "arquivos"))

    def _caminho_absoluto_pdf(rel_ou_abs: str | None) -> Path | None:
        if not rel_ou_abs:
            return None
        p = Path(rel_ou_abs)
        if p.is_absolute():
            return p if _e_arquivo(p) else None
        cand = archive_root() / p
        return cand if _e_arquivo(cand) else None

    def selar_reconhecimento_sinal(rid: int, *, titular: str,
                                   documento: str | None) -> str:
        """Sela o reconhecimento AUTONOMO com item 413. Nao sela abertura.

        Mesmo caminho `/selo/notas/reconhecimento-firma` medido para firma —
        cx_servicos 413 cobre «Reconhecimento de sinal, letra e firma».
        """
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return SR.recado_pendente_selo()
        servico = SERVICOS["SINAL"]
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            linha = con.execute(
                "SELECT codigo_tj FROM cx_servicos WHERE codigo=?",
                (int(servico),)).fetchone()
        codigo_tj = (linha["codigo_tj"] if linha else None) or None
        if not codigo_tj:
            return (f" O ato foi lavrado SEM SELO: o serviço {servico} não tem "
                    f"item da tabela do TJMA no cadastro.")
        versao = AS.versao_da_tabela_de_custas(
            AS.CAMINHO_DAS_NOTAS["nt_sinais_reconhecimentos"],
            db.get_setting("selo_tabela_custas_em", ""))
        if not versao:
            return (" O ato foi lavrado SEM SELO: falta dizer de que data é a "
                    "tabela de custas em vigor, em Administrativo → "
                    "Configurações.")
        try:
            envelope = AS.envelope_das_notas(
                tabela="nt_sinais_reconhecimentos", codigo_tj=codigo_tj,
                escrevente=usuario_nome(), versao_tabela=versao,
                especie="SEMELHANCA",
                partes=[{"nome": titular, "documento": documento or ""}])
        except AS.AtoError as erro:
            return f" O ato foi lavrado SEM SELO: {erro}"
        r = AS.selar_o_ato_lavrado(
            db, Path(app.config["DATA_DIR"]),
            tabela="nt_sinais_reconhecimentos", ato_id=rid, tipo="ATO",
            atribuicao="NOTAS",
            agora=datetime.now().isoformat(timespec="seconds"),
            cns=db.get_setting("ri_cns", ""), usuario=usuario_nome(),
            dados=envelope,
            referencia=f"nt_sinais_reconhecimentos:{int(rid)}")
        if not r.get("selado"):
            return f" O ato foi lavrado SEM SELO: {r.get('motivo') or ''}"
        with db.transaction() as con:
            con.execute(
                """UPDATE nt_sinais_reconhecimentos
                      SET selo=?, servico_codigo=? WHERE id=?""",
                (r["numero"], servico, rid))
        return f" Selo {r['numero']}."

    @app.route("/notas/sinais", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_sinais():
        """Lista e abertura (cadastro) do sinal público — SEM selo."""
        if request.method == "POST" and request.form.get("acao") == "novo":
            if somente_leitura():
                flash("Perfil de auditoria não cadastra sinal.", "danger")
                return redirect(url_for("notas_sinais"))
            titular = (request.form.get("titular") or "").strip()
            if not titular:
                flash("Informe o titular do sinal.", "danger")
                return redirect(url_for("notas_sinais"))
            origem = (request.form.get("origem") or "MANUAL").strip().upper()
            if origem not in ORIGENS_SINAL:
                origem = "MANUAL"
            documento = "".join(
                c for c in (request.form.get("documento") or "") if c.isdigit()) or None
            data_abertura = (request.form.get("data_abertura") or "").strip() or date.today().isoformat()
            origem_chave = (request.form.get("origem_chave") or "").strip() or None
            observacao = (request.form.get("observacao") or "").strip() or None
            metadados = (request.form.get("metadados") or "").strip() or None
            agora = datetime.now().isoformat(timespec="seconds")
            with db.transaction() as con:
                cur = con.execute(
                    """INSERT INTO nt_sinais_publicos
                       (titular, titular_norm, documento, data_abertura, origem,
                        origem_chave, metadados, observacao, ativo,
                        criado_em, criado_por)
                       VALUES (?,?,?,?,?,?,?,?,1,?,?)""",
                    (titular, normalizar_nome_sinal(titular), documento,
                     data_abertura, origem, origem_chave, metadados,
                     observacao, agora, usuario_nome()))
                novo = int(cur.lastrowid)
            audit("NT_SINAL_ABERTO", "NT_SINAL", novo,
                  {"titular": titular, "origem": origem})
            # Anexa PDF no mesmo POST, se veio — ainda SEM selo.
            pdf = request.files.get("pdf")
            if pdf and pdf.filename:
                _guardar_pdf_sinal(novo, pdf)
            flash(f"Sinal público nº {novo} aberto para {titular}. "
                  f"(Abertura não sela — anexe o PDF da central.)", "success")
            return redirect(url_for("notas_sinal", sinal_id=novo))

        busca = (request.args.get("busca") or "").strip()
        achados = []
        if busca and len(busca) >= 2:
            like = f"%{normalizar_nome_sinal(busca)}%"
            dig = "".join(c for c in busca if c.isdigit())
            if dig:
                achados = q(
                    """SELECT * FROM nt_sinais_publicos
                        WHERE titular_norm LIKE ? OR documento LIKE ?
                        ORDER BY id DESC LIMIT ?""",
                    (like, f"%{dig}%", POR_PAGINA))
            else:
                achados = q(
                    """SELECT * FROM nt_sinais_publicos
                        WHERE titular_norm LIKE ?
                        ORDER BY id DESC LIMIT ?""",
                    (like, POR_PAGINA))
        resumo = q1("""SELECT COUNT(*) total,
                       COALESCE(SUM(CASE WHEN caminho_pdf IS NOT NULL THEN 1 ELSE 0 END),0) com_pdf
                       FROM nt_sinais_publicos WHERE ativo=1""")
        return render_template(
            "notas_sinais.html", busca=busca, achados=achados, resumo=resumo,
            origens=ORIGENS_SINAL)

    def _guardar_pdf_sinal(sinal_id: int, fs) -> str:
        """Grava o PDF em arquivos/notas/sinais/<id>/ e atualiza o cadastro."""
        nome_orig = Path(fs.filename or "sinal.pdf").name
        if not nome_orig.lower().endswith(".pdf"):
            flash("Anexe o PDF baixado da central (arquivo .pdf).", "danger")
            return ""
        dados = fs.read()
        if not dados:
            flash("Arquivo PDF vazio.", "danger")
            return ""
        if not dados[:5].startswith(b"%PDF"):
            flash("O arquivo não parece ser PDF.", "danger")
            return ""
        pasta = pasta_sinais() / str(sinal_id)
        pasta.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(dados).hexdigest()
        nome = f"sinal-{sinal_id}.pdf"
        alvo = pasta / nome
        alvo.write_bytes(dados)
        rel = str(alvo.relative_to(archive_root()))
        agora = datetime.now().isoformat(timespec="seconds")
        with db.transaction() as con:
            con.execute(
                """UPDATE nt_sinais_publicos
                      SET caminho_pdf=?, nome_arquivo_pdf=?, sha256=?, bytes=?,
                          atualizado_em=?, atualizado_por=?
                    WHERE id=?""",
                (rel, nome, digest, len(dados), agora, usuario_nome(), sinal_id))
        audit("NT_SINAL_PDF", "NT_SINAL", sinal_id,
              {"bytes": len(dados), "sha256": digest[:12]})
        return rel

    @app.route("/notas/sinais/<int:sinal_id>", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_sinal(sinal_id):
        """Ficha do sinal: editar metadados e anexar/substituir PDF. Sem selo."""
        s = q1("SELECT * FROM nt_sinais_publicos WHERE id=?", (sinal_id,))
        if not s:
            abort(404)
        if request.method == "POST":
            if somente_leitura():
                flash("Perfil de auditoria não altera sinal.", "danger")
                return redirect(url_for("notas_sinal", sinal_id=sinal_id))
            acao = request.form.get("acao") or "salvar"
            if acao == "pdf":
                pdf = request.files.get("pdf")
                if not pdf or not pdf.filename:
                    flash("Escolha o PDF baixado da central.", "danger")
                else:
                    _guardar_pdf_sinal(sinal_id, pdf)
                    flash("PDF do sinal guardado em disco (não redesenhado).", "success")
                return redirect(url_for("notas_sinal", sinal_id=sinal_id))
            titular = (request.form.get("titular") or "").strip()
            if not titular:
                flash("Informe o titular.", "danger")
                return redirect(url_for("notas_sinal", sinal_id=sinal_id))
            origem = (request.form.get("origem") or s["origem"] or "MANUAL").strip().upper()
            if origem not in ORIGENS_SINAL:
                origem = "MANUAL"
            documento = "".join(
                c for c in (request.form.get("documento") or "") if c.isdigit()) or None
            data_abertura = (request.form.get("data_abertura") or "").strip() or None
            origem_chave = (request.form.get("origem_chave") or "").strip() or None
            observacao = (request.form.get("observacao") or "").strip() or None
            metadados = (request.form.get("metadados") or "").strip() or None
            ativo = 0 if request.form.get("inativo") == "1" else 1
            agora = datetime.now().isoformat(timespec="seconds")
            with db.transaction() as con:
                con.execute(
                    """UPDATE nt_sinais_publicos
                          SET titular=?, titular_norm=?, documento=?,
                              data_abertura=?, origem=?, origem_chave=?,
                              metadados=?, observacao=?, ativo=?,
                              atualizado_em=?, atualizado_por=?
                        WHERE id=?""",
                    (titular, normalizar_nome_sinal(titular), documento,
                     data_abertura, origem, origem_chave, metadados,
                     observacao, ativo, agora, usuario_nome(), sinal_id))
            audit("NT_SINAL_EDITADO", "NT_SINAL", sinal_id, {})
            flash("Cadastro do sinal atualizado.", "success")
            return redirect(url_for("notas_sinal", sinal_id=sinal_id))

        recs = q("""SELECT * FROM nt_sinais_reconhecimentos
                     WHERE sinal_id=? ORDER BY id DESC LIMIT 40""", (sinal_id,))
        return render_template(
            "notas_sinal.html", s=s, reconhecimentos=recs, origens=ORIGENS_SINAL)

    @app.route("/notas/sinais/<int:sinal_id>/pdf")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_sinal_pdf(sinal_id):
        """Serve o PDF anexado — o da central, sem redesenhar."""
        from flask import send_file
        s = q1("SELECT * FROM nt_sinais_publicos WHERE id=?", (sinal_id,))
        if not s:
            abort(404)
        caminho = _caminho_absoluto_pdf(s["caminho_pdf"])
        if not caminho:
            flash("Este sinal ainda não tem PDF anexado.", "warning")
            return redirect(url_for("notas_sinal", sinal_id=sinal_id))
        return send_file(caminho, mimetype="application/pdf",
                         download_name=s["nome_arquivo_pdf"] or f"sinal-{sinal_id}.pdf",
                         as_attachment=False)

    @app.route("/notas/sinais/reconhecimento", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_sinal_reconhecimento():
        """Reconhecimento AUTONOMO do sinal — sela com 413."""
        if request.method == "POST" and request.form.get("acao") == "reconhecer":
            if somente_leitura():
                flash("Perfil de auditoria não reconhece.", "danger")
                return redirect(url_for("notas_sinal_reconhecimento"))
            sid = request.form.get("sinal_id")
            if not str(sid or "").isdigit():
                flash("Escolha o sinal público.", "danger")
                return redirect(url_for("notas_sinal_reconhecimento"))
            sid = int(sid)
            s = q1("SELECT * FROM nt_sinais_publicos WHERE id=? AND ativo=1", (sid,))
            if not s:
                flash("Sinal não encontrado ou inativo.", "danger")
                return redirect(url_for("notas_sinal_reconhecimento"))
            if not s["caminho_pdf"]:
                flash("Anexe o PDF da central antes de reconhecer o sinal.", "danger")
                return redirect(url_for("notas_sinal", sinal_id=sid))
            doc_desc = (request.form.get("documento_descricao") or "").strip() or None
            agora = datetime.now()
            texto = texto_reconhecimento_sinal(s["titular"])
            with db.transaction() as con:
                cur = con.execute(
                    """INSERT INTO nt_sinais_reconhecimentos
                       (sinal_id, data, hora, servico_codigo, documento_descricao,
                        texto, oficial, oficial_funcao, criado_em, criado_por)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (sid, agora.date().isoformat(),
                     agora.strftime("%H:%M:%S"), SERVICOS["SINAL"], doc_desc,
                     texto, usuario_nome(), usuario_funcao(),
                     agora.isoformat(timespec="seconds"), usuario_nome()))
                rid = int(cur.lastrowid)
            selado = selar_reconhecimento_sinal(
                rid, titular=s["titular"], documento=s["documento"])
            motivo_selo = motivo_da_falha_do_selo(selado)
            if motivo_selo:
                with db.transaction() as con:
                    con.execute("DELETE FROM nt_sinais_reconhecimentos "
                                "WHERE id=?", (rid,))
                audit("NT_SINAL_RECONHECIMENTO_NAO_LAVRADO_SELO_FALHOU",
                      "NT_SINAL_REC", rid,
                      {"sinal_id": sid, "servico": SERVICOS["SINAL"],
                       "motivo": motivo_selo})
                flash("Reconhecimento de sinal NÃO lavrado: o selo não saiu. "
                      f"Motivo: {motivo_selo}. Corrija o problema do "
                      "selo e lavre de novo — o ato fica suspenso até o selo "
                      "sair (relato #77).",
                      "danger")
                return redirect(url_for("notas_sinal_reconhecimento",
                                        busca=s["titular"]))
            audit("NT_SINAL_RECONHECIDO", "NT_SINAL_REC", rid,
                  {"sinal_id": sid, "servico": SERVICOS["SINAL"]})
            flash(f"Reconhecimento de sinal nº {rid} lavrado.{selado}",
                  "warning" if motivo_selo else "success")
            return redirect(url_for("notas_sinal_reconhecimento_ver",
                                    reconhecimento_id=rid))

        busca = (request.args.get("busca") or "").strip()
        sinais = []
        if busca and len(busca) >= 2:
            like = f"%{normalizar_nome_sinal(busca)}%"
            sinais = q(
                """SELECT * FROM nt_sinais_publicos
                    WHERE ativo=1 AND titular_norm LIKE ?
                    ORDER BY id DESC LIMIT 20""", (like,))
        lista = q("""SELECT r.*, s.titular, s.documento
                       FROM nt_sinais_reconhecimentos r
                       JOIN nt_sinais_publicos s ON s.id = r.sinal_id
                      WHERE r.cancelado=0
                      ORDER BY r.id DESC LIMIT 40""")
        preco = emolumento_do_servico(SERVICOS["SINAL"])
        return render_template(
            "notas_sinal_reconhecimento.html", busca=busca, sinais=sinais,
            lista=lista, preco=preco)

    @app.route("/notas/sinais/reconhecimento/<int:reconhecimento_id>")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def notas_sinal_reconhecimento_ver(reconhecimento_id):
        r = q1("""SELECT r.*, s.titular, s.documento, s.caminho_pdf, s.id AS sinal_id
                    FROM nt_sinais_reconhecimentos r
                    JOIN nt_sinais_publicos s ON s.id = r.sinal_id
                   WHERE r.id=?""", (reconhecimento_id,))
        if not r:
            abort(404)
        return render_template("notas_sinal_reconhecimento_ver.html", r=r)
