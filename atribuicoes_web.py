"""
As telas das quatro atribuicoes novas — Protesto, RCPN, RCPJ/RTD e Livro 3.

O QUE ESTAS TELAS FAZEM
    Consultam, carregam o acervo e LANCAM ATO na ficha — averbar, intimar,
    protestar, pagar, cancelar. O que ainda nao fazem e abrir registro NOVO:
    isso muda muito de uma atribuicao para outra, e cada uma vai querer o seu
    formulario.

A TELA NAO REPETE A REGRA DO DOMINIO
    A ficha so OFERECE os atos que cabem na situacao — mas quem recusa e o
    modulo de dominio, e ha teste que manda um ato que nao cabe direto para a
    rota, sem passar pela tela, so para ver o dominio recusar.

    Repetir a regra nos dois lugares e como os dois divergem. A tela esconde o
    botao por educacao; o dominio recusa por dever.

O SELO E OPCIONAL NO LANCAMENTO, E ISSO E DELIBERADO
    O selador e maquina da rede local, e cai. Ato sem selo entra e aparece em
    `ato_selado.atos_sem_selo` — que e melhor do que balcao parado, e melhor
    do que ato lavrado com selo inventado.

    Mas selo RECUSADO derruba o lancamento inteiro: a transacao volta atras, e
    nao sobra ato lavrado com selo que o sistema nao aceitou. Ha teste.

POR QUE UM MODULO PARA AS QUATRO
    Sao quatro listas com o mesmo esqueleto: filtra, pagina, abre a ficha. O
    que muda e a tabela e as colunas. Quatro modulos seriam quatro versoes
    divergentes da mesma paginacao — a licao do nucleo, agora na tela.

A CARGA MOSTRA O QUE FEZ, E O QUE NAO FEZ
    A tela de carga imprime `lidos`, `inseridos`, `repetidos`, `rejeitados` e
    `avisados`, com os motivos. Ja houve nesta casa uma tela que dizia 4.060
    cartoes numa rodada que inseriu zero, e tres respostas se perderam
    depurando o lugar errado. Numero que a tela mostra e numero conferido.
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
import time
import uuid
import zipfile
from datetime import date
from pathlib import Path

from flask import (Response, abort, flash, g, redirect, render_template,
                   session,
                   request, send_file, url_for)

import acervo_carga as AC
from bd_nativo import banco
import acervo_eo_vivo as EO_VIVO
import importar_padrao as IMPP
import ato_selado as AS
# O SELO DE BUSCA QUE VAI JUNTO COM A CERTIDÃO — pedido do oficial,
# 15/10/2026. As faixas e o envelope moram num lugar só para as atribuições.
import buscas as BU
import certidao_folhas as CFOLHAS
# A CERTIDÃO DAS NOTAS (15/10/2026) — o domínio; as rotas moram aqui, ao lado
# das outras certidões. O catálogo de modelos dá o texto do oficial.
import modelos_da_casa as MODELOS
import notas_certidao as NCE
import atrib_certidao as CE
import impressao_web as IMPW
import fraude as FR
import livro_nucleo as LN
import habilitacao as HAB
import hc_schema as HC
import ibge_geracao as IBGEG
import rc_anotacao as ANOT
import rc_anotacao_crc as ANOTCRC
import crc_carga as CRC
import crc_envios as CRCENVIOS
import crc_a3 as CRCA3
import crc_soap as CRCSOAP
import sirc_remessa as SIRC
import sirc_cliente as SC
import gestor_envios as GENV
import centrais_cred as CENTCRED
import cra21_api as CRAAPI
import rc_funai as FUNAI
import rc_obrigacoes as OBRIG
import inacabados as INAC
import retificacao_rcpn as RETRC
import rr_tjma as RRNORMA
import rc_dados_cadastrais as DADOS
import rc_registro_tardio as TARDIO
import rc_gemeos as GEMEOS
import rc_folha as FOLHA
import rc_modelos_do_livro as MODLIVRO
import rc_checklist as CHECK
import rc_comunicacoes as COM
import rc_termo as RCT
import rc_matricula as MAT
import rc_marcas_do_obito as MARCA
import rc_filiacao as FILI
import rc_obito_tardio as OBTARDIO
import rc_cabecalho as CAB
import rc_cpf as CPFRC
import rc_etiqueta_averbacao as RCETQ
import rc_textos as TEXTOS
import etiqueta as ETQ
import rascunho_de_tela as RASC
import ibge_remessa as IBGE
import papel_seguranca as PP
import protesto as PT
import protesto_arquivo as PA
import protesto_cra_xml as PCRAXML
import protesto_cra_imagens as PCIMG
import protesto_aviso as AV
import protesto_intimacoes_lote as PILOTE
import protesto_base_endereco as PBE
import arquivo_visivel as ARQVIS
import pastas_da_casa as PDC
import protesto_cenprot as PCEN
import protesto_cenprot_xml as PCXML
import protesto_roteiro as PROT
import protesto_certidao as PCE
import protesto_termo as PTERMO
import protesto_triduo as TRIDUO
import protesto_livros as PLIV
import protesto_cra as CRA
import protesto_desistencia as DS
import protesto_imagens as PIMG
import protesto_instrumento as PI
import protesto_remessa as PRM
import protesto_retorno as PRE
import protesto_cra_envio as PCRAENV
# A LISTA DOS TÍTULOS — pendentes, filtros, ordens e o próximo passo
# (pedido do oficial, 14/10/2026).
import protesto_lista as PLISTA
# O EMOLUMENTO A POSTERIORI (LG05, 19/10/2026): quem paga cada ato do título
# diferido, quando, e por qual tabela — CN-MA art. 925, §§ 11 e 12.
import protesto_posteriori as POST
import ra_correcoes as CORR
# A VARREDURA DA FICHA DO LIVRO 3 — e dela que sai a certidao por reproducao.
import ra_digitalizacao as RADIGI
import ra_expurgo as EXPU
import ra_minuta as MIN
# **`PT` JA ERA DO PROTESTO** (`import protesto as PT`, dezessete linhas
# acima), e importar `ra_parte as PT` o SOBRESCREVEU: as telas
# `/protesto/novo` e `/protesto/a-protestar` passaram a estourar com
# «module 'ra_parte' has no attribute 'especies_para_escolher'».
# Quem pegou foi o varredor «toda tela abre em instalacao nova», em
# 21/09/2026 — nenhum teste do Livro 3 veria isso.
import ra_parte as RAPT
import ra_registro as RA
import ra_revisao as RREV
# O SELO DO ATO DO LIVRO 3 mora em modulo proprio, com as medicoes do acervo
# que dizem por qual caminho ele sai e o que vai no envelope. Aqui so se leem
# os itens que a tela oferece.
import ra_selo as RS
import rc_assento as RC
import rc_certidao as RCE
import rc_certidao_quadro as RCQ
import rc_certidao_odt as RCODT
import modelos_moldes as MOLDES_ODT
import rc_certidao_inteiro_teor as RCIT
# O TERMO ASSINADO DIGITALIZADO (problema #121): a certidão reprográfica que
# sai dele, página a página.
import rc_digitalizacao as RCDIGI
import notas_selo as NSELO
import selo_no_papel as SNPAPEL
import rg_registro as RG
import rg_teor_rtdpj as RGTEOR
import rg_certidao_pdf as RGCERT
import ri_odt as RODT
from ri_odt import gerar_odt, html_para_odf
from ri_web import data_por_extenso
from serventia import dados as dados_serventia
from seguranca_web import PRATICA  # M2 (LX11): o AUDITOR vê e não grava
import seguranca_web as SEGWEB  # B2 (LX11): exceção inesperada não vai para a tela
from seguranca_web import destino_interno  # M1/B3 (LX11): o «volte para» só leva a caminho desta casa
# O número que a tela mandou (LD13): «abc», «²» e 5.000 dígitos não viram 500.
from seguranca_web import MAIOR_INTEGER, PAGINA_MAIS_ALTA, numero_digitado

POR_PAGINA = 50

# Cada painel: de onde le, o que mostra e por onde procura. E a unica coisa
# que muda de uma atribuicao para outra.
PAINEIS: dict[str, dict] = {
    "protesto": {
        "titulo": "Protesto — títulos",
        "tabela": "pt_titulos",
        "busca": ("numero_titulo", "nosso_numero", "cedente_nome"),
        # O DEVEDOR MORA NOUTRA TABELA, e e por ele que o balcao procura: a
        # pergunta do guiche e "fulano tem protesto?", nao "onde esta o
        # titulo 84713/1". Procurar so nas colunas de `pt_titulos` deixaria
        # essa pergunta sem resposta.
        "busca_junta": (
            ("EXISTS (SELECT 1 FROM pt_devedores d "
             "WHERE d.titulo_id = pt_titulos.id AND "
             "(d.nome ILIKE %s OR d.documento_numero ILIKE %s))"), 2),
        "select_extra": ("(SELECT string_agg(nome::text, ' · ' ORDER BY d.id) FROM pt_devedores d "
                         "WHERE d.titulo_id = pt_titulos.id) AS devedores"),
        "busca_diz": "nome ou CPF/CNPJ do devedor, número do título, cedente",
        "ordem": "id DESC",
        "situacoes": ("RECEBIDO", "APONTADO", "INTIMADO", "PROTESTADO",
                      "PAGO", "CANCELADO", "DESISTIDO"),
    },
    "rcpn": {
        "titulo": "Registro Civil das Pessoas Naturais — assentos",
        "tabela": "rc_assentos",
        "busca": ("nome", "matricula"),
        "ordem": "id DESC",
        "situacoes": ("ATIVO", "CANCELADO"),
    },
    "rcpj_rtd": {
        "titulo": "RCPJ e RTD — registros",
        "tabela": "rg_registros",
        "busca": ("requerente_nome", "natureza"),
        "ordem": "id DESC",
        "situacoes": ("ATIVO", "CANCELADO"),
        # AS DUAS ATRIBUICOES NA MESMA TABELA, E CADA UMA COM A SUA LISTA.
        #
        # O modulo e um so porque o acervo do E-Oficio ja guardava as duas
        # juntas (`livroTDPJ`) e porque o livro tem a mesma forma nas duas —
        # escrever dois modulos quase iguais seria o erro que o nucleo existe
        # para evitar.
        #
        # Mas o BALCAO pensa nelas separadas: quem procura um contrato de
        # aluguel nao quer sociedade civil no meio da lista. Entao o codigo
        # continua um, e a TELA se separa — que e onde a separacao importa.
        # Pedido do oficial em 27/08/2026.
        "atribuicoes": {
            "3": "RCPJ — Registro Civil das Pessoas Jurídicas",
            "4": "RTD — registro de títulos e documentos",
        },
    },
    "livro3": {
        "titulo": "Registro Auxiliar — Livro 3",
        "tabela": "ra_registros",
        "busca": ("numero", "titulo_numero", "titulo_tipo"),
        "ordem": "numero DESC",
        "situacoes": ("ATIVO", "CANCELADO"),
    },
}

# UMA PORTA PARA CADA ESPÉCIE DO RCPN.
#
# O código interno continua em caixa alta porque é assim que o domínio, o
# banco e o selador falam. A URL, porém, é o nome que o balcão reconhece. O
# mapa fechado faz duas coisas importantes: impede uma espécie inventada na
# URL e permite que a rota fixe a espécie sem confiar num campo editável do
# formulário.
RCPN_SLUG_DA_ESPECIE: dict[str, str] = {
    "NASCIMENTO": "nascimento",
    "CASAMENTO": "casamento",
    "CASAMENTO_RELIGIOSO": "casamento-religioso",
    "OBITO": "obito",
    "NATIMORTO": "natimorto",
    "PROCLAMAS": "proclamas",
    "AUSENCIA": "ausencia",
    "INTERDICAO": "interdicao",
    "TUTELA": "tutela",
    "EMANCIPACAO": "emancipacao",
    "UNIAO_ESTAVEL": "uniao-estavel",
    "OPCAO_NACIONALIDADE": "opcao-nacionalidade",
    "OUTRO": "outro-livro-e",
}
RCPN_ESPECIE_DO_SLUG = {slug: especie
                         for especie, slug in RCPN_SLUG_DA_ESPECIE.items()}

RCPN_GRUPOS_DE_ESPECIES = (
    ("Registros principais", (
        "NASCIMENTO", "CASAMENTO", "OBITO")),
    ("Livros auxiliares", (
        "CASAMENTO_RELIGIOSO", "NATIMORTO", "PROCLAMAS")),
    ("Livro E", (
        "AUSENCIA", "INTERDICAO", "TUTELA", "EMANCIPACAO",
        "UNIAO_ESTAVEL", "OPCAO_NACIONALIDADE", "OUTRO")),
)


def _inteiro(valor, padrao: int = 1, *, maximo: int | None = None) -> int:
    """O número de 1 para cima que a tela mandou; o que não é número vale
    `padrao`. Só calcula.

    PELA RÉGUA DA CASA DESDE O LD13 (21/10/2026). O `int()` daqui já tolerava
    o texto, mas o número de 30 dígitos passava inteiro: na página virava
    OFFSET fora do `bigint` e no período da certidão ia gravado — a tela de
    erro. `maximo` é o maior que ainda cabe onde o número vai.
    """
    numero = numero_digitado(valor, maximo=maximo)
    return padrao if numero is None else max(1, numero)


def _ponto_de_retorno(con, comando: str) -> None:
    """SAVEPOINT, RELEASE ou ROLLBACK TO do módulo, direto no PostgreSQL.

    PELA PONTE O SAVEPOINT SUMIA NA HORA (L056R, 17/10/2026). `con.execute` e
    o `bd` põem cada comando dentro de um savepoint de proteção deles
    (`cg_sp`, `cg_nativo`), e o RELEASE desse leva junto todo savepoint aberto
    depois dele, o do módulo também. O RELEASE seguinte estourava com
    «savepoint ... does not exist» e derrubava a lavratura inteira. Aqui o
    comando vai cru, na mesma conexão e na mesma transação da rota.

    O ERRO SOBE COMO O DO SQLITE3 (L056R, 18/10/2026), traduzido como a ponte e
    o `bd` traduzem: é o que o sistema apanha, e pelo `con.execute` de antes
    era assim.
    """
    bd = banco(con)          # no SQLite recusa aqui, antes do psycopg
    import psycopg
    import banco_pg

    bd._escrita()
    try:
        with bd._pg.cursor() as c:
            c.execute(comando)
    except psycopg.Error as erro:
        raise banco_pg._traduzir_erro(erro) from erro



def _vincular_anexos_rg_ato(db, *, ato_id: int, registro_id: int,
                            anexo_ids: list, user_id: int) -> int:
    """Cria linhas attachments RG_ATO reusando stored_path (sem copiar binário).

    Só aceita anexos já ligados ao RG_REGISTRO deste registro. Idempotente
    por stored_path: se o ato já aponta para o mesmo arquivo, não repete.
    """
    vinculados = 0
    existentes = {
        str(a["stored_path"]) for a in db.get_attachments("RG_ATO", ato_id)
    }
    for raw in anexo_ids or []:
        anexo_id = numero_digitado(raw)
        if anexo_id is None:
            continue
        src = db.get_attachment(anexo_id)
        if not src:
            continue
        if str(src["entity_type"]) != "RG_REGISTRO":
            continue
        if int(src["entity_id"]) != int(registro_id):
            continue
        caminho = str(src["stored_path"] or "")
        if not caminho or caminho in existentes:
            continue
        fileinfo = {
            "original_name": src["original_name"],
            "stored_name": src["stored_name"],
            "stored_path": src["stored_path"],
            "sha256": src["sha256"],
            "size_bytes": src["size_bytes"],
        }
        db.add_attachment(
            "RG_ATO", ato_id, fileinfo, user_id,
            src["description"] or "Anexo da averbação")
        existentes.add(caminho)
        vinculados += 1
    return vinculados


def _anexar_novos_arquivos_ao_registro(db, *, registro_id: int, serie: str,
                                       numero, arquivos: list,
                                       descricao: str,
                                       user_id: int,
                                       pasta_dos_arquivos) -> list[int]:
    """Salva os arquivos escolhidos NA HORA de lançar. ESCREVE.

    Pedido do oficial (11/09/2026): «não tem campo para juntar os arquivos
    que serão averbados» — até aqui, anexar exigia ir a uma seção separada
    («Imagens/anexos do livro»), subir o arquivo, e só depois voltar ao
    formulário de lançar para marcar a caixinha. Este é o mesmo caminho de
    `rcpj_rtd_registro_arquivo` (mesmo `entity_type` RG_REGISTRO, mesma
    pasta), só que chamado de DENTRO do lançamento — o arquivo já nasce
    ligado ao registro, e quem chama ainda liga ao ATO (`_vincular_anexos_
    rg_ato`), exatamente como um anexo marcado por checkbox.
    """
    from storage import safe_component, save_upload
    ids: list[int] = []
    destino = (pasta_dos_arquivos() / "RCPJ"
               / safe_component(str(serie or "RCPJ"))
               / safe_component(str(numero or registro_id)))
    for arquivo in arquivos or []:
        if not arquivo or not arquivo.filename:
            continue
        info = save_upload(arquivo, destino)
        anexo_id = db.add_attachment(
            "RG_REGISTRO", registro_id, info, user_id, descricao)
        ids.append(int(anexo_id))
    return ids


def _caminhos_imagens_anexos(anexos: list) -> list[Path]:
    caminhos: list[Path] = []
    for a in anexos:
        caminho = Path(a["stored_path"])
        if not caminho.is_file():
            continue
        ext = caminho.suffix.lower()
        if ext in RGTEOR.EXTENSOES_IMAGEM or ext in RGTEOR.EXTENSOES_PDF:
            caminhos.append(caminho)
    return caminhos


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura as telas das quatro atribuicoes no app ja construido."""

    # UM RELOGIO SO PARA O MODULO INTEIRO. `db.now()` e o mesmo que grava o
    # resto da casa; ler a hora de dois lugares faria o ato e o lancamento do
    # caixa discordarem por um segundo.
    def agora() -> str:
        return db.now()

    def acervo_no_disco() -> Path:
        return Path(app.config["DATA_DIR"]) / AC.NOME_ACERVO

    def sv() -> dict:
        return dados_serventia(db.get_settings)

    def hoje() -> str:
        return agora()[:10]

    def hoje_extenso() -> str:
        return data_por_extenso(date.fromisoformat(hoje()))

    usuario_nome = app.extensions["usuario_nome"]
    usuario_funcao = app.extensions["usuario_funcao"]
    usuario_id_do_sistema = app.extensions["usuario_id"]
    pasta_dos_arquivos = app.extensions["archive_root"]

    # O CAMPO DA BUSCA SE MONTA NA TELA, e não em cada rota — pedido do
    # oficial, 15/10/2026. As telas que emitem certidão são várias (a ficha do
    # assento, a prévia, a ficha da matrícula, os indicadores, o Protesto), e
    # passar o mesmo contexto por cinco rotas daria cinco versões dele.
    app.add_template_global(BU.para_a_tela, "busca_da_certidao")

    def _papel_atual() -> str:
        uid = session.get("user_id")
        if not uid:
            return ""
        u = db.get_user(int(uid))
        return (u["role"] if u else "") or ""

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    def _motivo_da_falha_do_selo(recado: str) -> str | None:
        """O motivo de uma falha que SUSPENDE o ato. Só LÊ.

        Recusa do aparelho, item de cobrança ausente, tabela sem data ou folha
        indisponível são causas diferentes da mesma decisão: o ato não fica
        ativo sem selo. O motivo é mostrado para o balcão corrigir a causa e
        tentar novamente.

        **QUEM DIZ A ESPÉCIE É A MARCA PRESA AO RECADO**, e não o texto dele
        — `ato_selado.RecadoDoSelo`. Adivinhar lendo a frase seria o varredor
        batendo na própria prosa, e aqui o custo é um ato que não se lavra.
        """
        texto = str(recado or "").strip()
        if not texto:
            return None
        if not AS.suspende_o_ato(recado):
            return None
        if "SEM SELO:" in texto:
            return texto.split("SEM SELO:", 1)[1].strip() or "falha sem detalhe"
        baixo = texto.lower()
        if "sem selo:" in baixo:
            return texto.split(":", 1)[1].strip() or "falha sem detalhe"
        if "sem selo" in baixo:
            return texto or "falha sem detalhe"
        return None

    def _gratuidade_do_form() -> tuple[str | None, str | None, bool]:
        """Código e motivo de gratuidade marcados no formulário. Só LÊ.

        Devolve `(gratuidade_codigo, motivo_gratuidade, isento_selo)`.
        A averbação de CPF (art. 347) força `ART_347_CPF` e selo gratuito —
        via `g.rcpn_gratuidade_override`, porque `request.form` é imutável.
        """
        override = getattr(g, "rcpn_gratuidade_override", None) or {}
        codigo = (override.get("codigo")
                  or _campo("gratuidade_codigo").upper() or None)
        motivo = (override.get("motivo")
                  or _campo("motivo_gratuidade")
                  or _campo("motivo_isencao") or None)
        marcado = bool(override) or (
            request.form.get("ato_gratuito") == "1"
            or request.form.get("selo_gratuito") == "1"
            or request.form.get("isento") == "1"
            or bool(_campo("gratuidade_codigo")))
        if marcado and not motivo:
            raise AS.AtoError(
                "Ato gratuito / selo gratuito precisa do motivo escrito — "
                "é ele que a conferência lê no selo e no caixa.")
        if marcado and not codigo:
            codigo = "HIPOSSUFICIENCIA"
        return (codigo if marcado else None,
                motivo if marcado else None,
                marcado)


    def _gratuidades_da_certidao():
        """Opcoes de isencao na emissao de certidao RCPN. So LE.

        Sem ART_347_CPF — aquele item e so da averbacao de CPF.
        """
        import custas as CU
        return tuple(
            g for g in CU.GRATUIDADES_POR_PESSOA
            if g.get("codigo") != "ART_347_CPF"
        )

    def _busca_do_form(atribuicao: str) -> str | None:
        """O item de busca que a tela da certidão mandou. Só LÊ; recusa vazio.

        **SEM `busca_formulario` NÃO HÁ BUSCA**, e é de propósito: é a chamada
        de antes do campo existir (a forma de `onus_formulario` no RI). Com o
        campo, a escolha é obrigatória — a tela vem com a faixa sugerida, e
        chegar vazio é ninguém ter escolhido onde não havia data do ato.
        Pedido do oficial, 15/10/2026.
        """
        if (request.form.get("busca_formulario") or "").strip() != "1":
            return None
        return BU.escolher(atribuicao, _campo("busca_item"))


    def _caixa_aberto(con) -> dict | None:
        """O caixa aberto de quem está usando o sistema. Só LÊ."""
        return banco(con).um(
            """SELECT * FROM cx_caixas
                WHERE operador_nome=%s AND situacao='ABERTO'
                ORDER BY data DESC, id DESC LIMIT 1""", (usuario_nome(),))

    def _cobrar_se_pedido(con, tabela: str, ato_id: int, tipo: str,
                          busca: str | None = None,
                          data_do_ato: str | None = None) -> str:
        """Lança no caixa os itens que o operador marcou. ESCREVE.

        A COBRANÇA É ESCOLHIDA, e não automática. A receita medida diz o que a
        casa costuma cobrar naquele ato — mas é média, e quem lavra decide o
        que cabe no caso. Cobrar sozinho pelo que costuma faria o balcão cobrar
        pela média em vez de pelo concreto.

        SEM CAIXA ABERTO NÃO SE COBRA. Lançamento sem caixa não aparece na
        gaveta de ninguém: o dinheiro entra no sistema e não entra na conferência
        do dia, e a diferença aparece no fechamento sem ter de onde vir. É a
        mesma regra do balcão de verdade — não se recebe com a gaveta fechada.

        **OS ITENS DO PROTOCOLO TAMBÉM PODEM SER COBRADOS DAQUI** — pedido do
        oficial em 11/09/2026: RCPJ/RTD não tem receita de cobrança MEDIDA
        para a maioria dos caminhos (o "Cobrar no caixa" de sempre não
        aparece), mas o item do protocolo já sabe o `servico_codigo` — o
        mesmo `cx_servicos.codigo` que a tela do Caixa usaria. `cobrar_
        protocolo_item` (o `id` de `cx_protocolo_atos`) é o item marcado
        nesta lista; o valor é recalculado por `AS.cobrar` na hora, pela
        tabela vigente — não é o `valor_total` congelado que o protocolo
        guarda, que pode ser de outra data.

        `data_do_ato` É A DATA DA TABELA, quando não é a de hoje (LG05): o
        desfecho do título diferido cobra pela tabela da protocolização ou do
        pedido de cancelamento (CN-MA art. 925, § 11). Sem ela, vale a de hoje,
        como sempre.
        """
        # O QUE NÃO É NÚMERO NÃO FOI MARCADO (LD13): a caixa de marcar manda
        # o código do serviço e o id do item; «abc», «²» ou 5.000 dígitos no
        # lugar deles eram a tela de erro no meio da lavratura.
        servicos = [str(n) for n in (numero_digitado(s)
                                     for s in request.form.getlist("cobrar"))
                    if n is not None]
        ids_protocolo_item = [n for n in (numero_digitado(x) for x in
                                          request.form.getlist("cobrar_protocolo_item"))
                              if n is not None]
        if not servicos and not ids_protocolo_item:
            return ""
        # A BUSCA ENTRA NA MESMA COBRANÇA DA CERTIDÃO — pedido do oficial,
        # 15/10/2026. Só quando se está cobrando (a cobrança continua
        # escolhida), só se o item gera selo (o «.9» não cobra), e só se a
        # busca já não está entre o que se marcou: duas vezes a mesma busca no
        # recibo seria o cliente pagando duas.
        if busca and BU.vira_selo(busca):
            ja_marcados = BU.codigos_dos_servicos(con, servicos)
            if ids_protocolo_item:
                lugares_b = ",".join(["%s"] * len(ids_protocolo_item))
                ja_marcados += [str(r["codigo_ato"]) for r in banco(con).ler(
                    f"""SELECT codigo_ato FROM cx_protocolo_atos
                         WHERE id IN ({lugares_b}) ORDER BY id""",
                    list(ids_protocolo_item)) if r["codigo_ato"]]
            if not BU.busca_entre(ja_marcados):
                servico_busca = BU.servico_da_busca(con, busca)
                if servico_busca is None:
                    raise AS.AtoError(
                        f"O item de busca {busca} não está na tabela de "
                        "emolumentos desta casa. Confira a tabela em "
                        "Administrativo → Caixa antes de cobrar.")
                servicos.append(str(servico_busca))
        caixa = _caixa_aberto(con)
        if not caixa:
            raise AS.AtoError(
                "Você não tem caixa aberto, e sem caixa o lançamento não "
                "aparece na conferência do dia. Abra o caixa em "
                "Administrativo → Caixa e lance o ato de novo — ou lance sem "
                "marcar cobrança, e cobre depois.")
        # O protocolo que não é número é o mesmo que nenhum (LD13); e o id que
        # passa do `integer` não é de protocolo nenhum, e estourava a gravação.
        protocolo = numero_digitado(_campo("protocolo_id"), maximo=MAIOR_INTEGER)
        total = 0
        grat_cod, grat_mot, _isento = _gratuidade_do_form()
        for servico in servicos:
            r = AS.cobrar(con, tabela=tabela, ato_id=ato_id,
                          servico=int(servico), agora=agora(),
                          hoje=hoje(),
                          hora=agora()[11:16],
                          caixa_id=int(caixa["id"]),
                          protocolo_id=protocolo,
                          pagador=_campo("pagador") or None,
                          forma_pagamento=_campo("forma_pagamento") or None,
                          descricao=f"{tipo} — {tabela}",
                          data_do_ato=data_do_ato,
                          gratuidade_codigo=grat_cod,
                          motivo_gratuidade=grat_mot,
                          usuario_id=None)
            total += r["total_centavos"]
        if ids_protocolo_item:
            lugares = ",".join(["%s"] * len(ids_protocolo_item))
            linhas = banco(con).ler(
                f"""SELECT id, servico_codigo, quantidade, descricao
                     FROM cx_protocolo_atos
                    WHERE id IN ({lugares}) AND protocolo_id=%s
                      AND servico_codigo IS NOT NULL
                    ORDER BY id""",
                list(ids_protocolo_item)
                + [protocolo if protocolo is not None else -1])
            for linha in linhas:
                r = AS.cobrar(con, tabela=tabela, ato_id=ato_id,
                              servico=int(linha["servico_codigo"]),
                              quantidade=max(1, int(linha["quantidade"] or 1)),
                              agora=agora(), hoje=hoje(), hora=agora()[11:16],
                              caixa_id=int(caixa["id"]),
                              protocolo_id=protocolo,
                              pagador=_campo("pagador") or None,
                              forma_pagamento=_campo("forma_pagamento") or None,
                              descricao=linha["descricao"] or f"{tipo} — {tabela}",
                              data_do_ato=data_do_ato,
                              gratuidade_codigo=grat_cod,
                              motivo_gratuidade=grat_mot,
                              usuario_id=None)
                total += r["total_centavos"]
        from caixa_schema import reais
        return f" Lançado no caixa: R$ {reais(total)}."

    def _diferir_se_pedido(con, titulo_id: int, ato_id: int, tipo: str) -> str:
        """Deixa DEVIDO o que o operador marcou, em vez de cobrar. ESCREVE.

        É o ato do título diferido antes do desfecho — protocolização,
        intimação, protesto (CN-MA art. 925, § 11). Os mesmos itens que a
        cobrança leria (`cobrar` e `cobrar_protocolo_item`) continuam selando
        o ato, por `_itens_para_selar`; o que muda é que não entram no caixa.
        E por isso não pedem caixa aberto: não há dinheiro entrando.
        """
        # O mesmo «não é número, não foi marcado» de `_cobrar_se_pedido` (LD13).
        itens = [{"servico": n} for n in (numero_digitado(s)
                                          for s in request.form.getlist("cobrar"))
                 if n is not None]
        ids_protocolo_item = [n for n in (numero_digitado(x) for x in
                                          request.form.getlist("cobrar_protocolo_item"))
                              if n is not None]
        protocolo = numero_digitado(_campo("protocolo_id"))
        if ids_protocolo_item and protocolo is not None:
            lugares = ",".join(["%s"] * len(ids_protocolo_item))
            for linha in banco(con).ler(
                    f"""SELECT servico_codigo, quantidade, descricao
                         FROM cx_protocolo_atos
                        WHERE id IN ({lugares}) AND protocolo_id=%s
                          AND servico_codigo IS NOT NULL
                        ORDER BY id""", ids_protocolo_item + [protocolo]):
                itens.append({"servico": int(linha["servico_codigo"]),
                              "quantidade": int(linha["quantidade"] or 1),
                              "descricao": linha["descricao"]})
        if not itens:
            return ""
        r = POST.diferir(con, titulo_id=titulo_id, ato_id=ato_id, tipo_ato=tipo,
                         itens=itens, data_do_ato=hoje(), agora=agora(),
                         usuario=usuario_nome())
        from caixa_schema import reais
        return (f" Emolumento a posteriori: R$ {reais(r['estimado_centavos'])} "
                f"fica devido e NÃO entrou no caixa (CN-MA art. 925, § 11).")

    def _cobrar_os_diferidos(con, titulo_id: int, ato_id: int,
                             cobranca: dict) -> str:
        """Lança no caixa o que o título ficou devendo, no desfecho. ESCREVE.

        Pela tabela que `cobranca["data_da_tabela"]` diz — a da protocolização
        no pagamento e na desistência, a do dia no cancelamento. Sem caixa
        aberto não se cobra, pela mesma regra de `_cobrar_se_pedido`.
        """
        if not POST.pendentes(con, titulo_id):
            return ""
        caixa = _caixa_aberto(con)
        if not caixa:
            raise AS.AtoError(
                "Você não tem caixa aberto, e sem caixa o emolumento a "
                "posteriori não aparece na conferência do dia. Abra o caixa, "
                "ou lance sem marcar a cobrança do que ficou devido.")
        r = POST.cobrar_pendentes(
            con, titulo_id, ato_do_desfecho_id=ato_id,
            data_da_tabela=cobranca["data_da_tabela"], caixa_id=int(caixa["id"]),
            agora=agora(), hoje=hoje(), hora=agora()[11:16],
            # vai gravado no lançamento: o que passa do `integer` é nenhum (LD13)
            protocolo_id=numero_digitado(_campo("protocolo_id"),
                                         maximo=MAIOR_INTEGER),
            pagador=_campo("pagador") or None,
            forma_pagamento=_campo("forma_pagamento") or None,
            usuario=usuario_nome())
        from caixa_schema import reais
        return (f" A posteriori: R$ {reais(r['total_centavos'])} cobrado(s) pela "
                f"tabela de {cobranca['data_da_tabela']}.")

    def _fraudes_de(con, pessoas: list[dict]) -> list[dict]:
        """A lista de atenção, conferida sobre as partes do ato. Só LÊ.

        UM HELPER SÓ PARA AS QUATRO, porque a pergunta é a mesma nas quatro:
        "alguém deste ato está na lista?". O que muda é ONDE cada atribuição
        guarda as pessoas, e isso cada ficha resolve montando a lista.

        `conferir_pessoas` não grava nada — o rastro se grava quando o operador
        reconhece o alerta, e não ao mostrá-lo.
        """
        return FR.conferir_pessoas(con, [
            p for p in pessoas if (p.get("nome") or p.get("documento"))])

    def _receitas_de(con, tabela: str, tipos: tuple[str, ...],
                     especie: str | None = None) -> dict:
        """O que a casa cobra em cada um daqueles atos. Só LÊ.

        **A ESPÉCIE SEPARA O QUE A TABELA NÃO SEPARA** — no civil ela é a
        espécie do assento; em `at_certidoes` é a **atribuição**, porque a
        mesma tabela serve RCPJ/RTD e Livro 3 e os dois atos se chamam
        `CERTIDAO`. Sem ela, a ficha do Livro 3 oferecia os itens do RTD/PJ.
        """
        saida = {}
        for tipo in tipos:
            caminho = AS.caminho_do_ato(tabela, tipo, especie)
            if caminho:
                saida[tipo] = AS.receita_de_custas(con, caminho)
        return saida

    def _cobrancas_de(con, tabela: str, atos: list) -> dict:
        """O que já foi cobrado por ato, para a ficha mostrar. Só LÊ.

        O recibo NÃO se emite aqui: `/caixa/recibo/<lancamento_id>` já faz
        isso, com numeração por exercício, teor congelado e hash. Duplicar
        aquela lógica daria duas versões da peça que o cliente leva para casa.
        A ficha aponta para lá.
        """
        saida = {}
        for a in atos:
            linhas = AS.lancamentos_do_ato(con, tabela, a["id"])
            if linhas:
                saida[a["id"]] = [dict(x) for x in linhas]
        return saida

    def _protocolos_abertos(con) -> list[dict]:
        """Os protocolos em aberto, para amarrar a cobrança a um deles. Só LÊ."""
        return banco(con).ler(
            """SELECT id, numero, interessado FROM cx_protocolos
                WHERE situacao NOT IN ('ENTREGUE','CANCELADO')
                ORDER BY id DESC LIMIT 60""")

    def _selar_se_pedido(con, tabela: str, ato_id: int, atribuicao: str) -> str:
        """Grava o selo que o escrevente digitou, se digitou. ESCREVE.

        O selo é OPCIONAL no lançamento, e isso é deliberado: o selador é
        máquina da rede local e cai. Ato sem selo entra e aparece em
        `atos_sem_selo` — que é melhor do que balcão parado, e melhor do que
        ato lavrado com selo inventado.
        """
        numero = _campo("selo")
        if not numero:
            return ""
        AS.registrar_selo_obtido_a_mao(
            con, numero, tabela=tabela, ato_id=ato_id, atribuicao=atribuicao,
            agora=agora(), cns=sv().get("ri_cns"), usuario=usuario_nome())
        return f" Selo {numero} gravado."

    def _especie_do_assento(assento_id) -> str:
        """A espécie do assento — nascimento, óbito, casamento. Só LÊ.

        É ela que decide o caminho do selo no civil: o contrato do selador tem
        uma família de caminhos por espécie, e selar registro de óbito pelo
        caminho do nascimento seria pior que não selar.
        """
        with db.connect() as con:
            linha = banco(con).um("SELECT especie FROM rc_assentos WHERE id=%s",
                                  (int(assento_id),))
        return (linha["especie"] if linha else "") or ""

    # **SÓ A AUTENTICAÇÃO DE CÓPIA CONTA POR UNIDADE** — correção do oficial
    # em 11/09/2026: *"quando colocamos um item com maior quantidade, é maior
    # quantidade de folhas naquele selo. ÚNICA exceção é a autenticação de
    # cópia — nela, 10 no item significa 10 selos diferentes. Todas as
    # outras, quantidade maior é UM selo com número de folhas maior"*. Este
    # projeto tinha generalizado errado: a medição de 27/08/2026 ("o
    # protocolo abriu um item 13.18 com quantidade 10, e saíram 10 selos")
    # era JUSTAMENTE o caso da exceção — `13.18` é o código TJ da
    # autenticação de cópia (`/selo/notas/autenticacao`, ver `atribuicoes.
    # CAMINHOS_USADOS_POR_ESTA_CASA`) — e virou regra geral por engano.
    CODIGO_TJ_AUTENTICACAO_COPIA = "13.18"

    def _itens_para_selar(con, ids_usados: list | None = None
                          ) -> list[tuple[str, int]]:
        """Os itens da tabela de emolumentos que viram selo. Só LÊ.

        Devolve pares `(codigo_tj, quantidade)` — um por SELO A PEDIR. Quem
        chama decide o que fazer com a quantidade: no RCPJ/RTD ela vai no
        campo `quantidade` do PRÓPRIO envelope (o selo já sai com o número de
        folhas certo, numa chamada só); Protesto e civil, que não têm esse
        campo no envelope, expandem cada par em `quantidade` selos de 1 —
        exatamente como sempre fizeram.

        A ORIGEM É O PROTOCOLO, e isso é correção do oficial em 27/08/2026:

            «No E-Ofício o selo é emitido com base no protocolo e caixa. Os
            itens que abriram o protocolo e caixa são os que são emitidos
            selos no fim.»

        **UM PROTOCOLO PODE SERVIR VÁRIOS ATOS — pedido do oficial em
        11/09/2026: «o normal é um protocolo para todo o trabalho pedido pelo
        cliente», e não um protocolo por ato.** Até aqui, escolher o protocolo
        sempre trazia TODOS os seus itens; certo quando ele cobre um ato só,
        errado quando cobre vários (duas averbações do mesmo pacote RCPJ/RTD,
        por exemplo) — a segunda pediria de novo os selos que a primeira já
        tomou. Agora:

        - se a tela mandou `protocolo_item_id` (o operador marcou quais itens
          valem para ESTE ato), pega só esses — e só os que ainda não foram
          usados por outro ato;
        - sem marcação explícita, cai no comportamento de sempre: todos os
          itens do protocolo ainda não usados (a maioria dos protocolos serve
          um ato só, e não há o que escolher).

        `ids_usados`, quando dado, recebe o `id` de cada linha de
        `cx_protocolo_atos` que este ato consumiu — é o que permite ao
        chamador marcar `usado_em`/`usado_por_ato_id` depois de o ato existir.

        SEM PROTOCOLO, VALE O QUE FOI MARCADO PARA COBRAR. Nem todo ato nasce
        de um protocolo — o balcão também lavra direto —, e nesses o item
        cobrado é a única coisa que existe. É o mesmo conteúdo por outro
        caminho: o item da tabela de emolumentos daquele atendimento.
        """
        # O NÚMERO QUE NÃO É NÚMERO (LD13). Isto roda DEPOIS de o ato estar
        # lavrado, e a tela de erro escondia que ele tinha saído. O protocolo
        # que não é número é nenhum. O item marcado que passa pelo `isdigit()`
        # e não é id do banco («²», 5.000 dígitos) vira -1, o id de ninguém: é
        # o «não achei» que o de 30 dígitos já dava. Tirá-lo da lista a
        # deixaria vazia — e lista vazia aqui quer dizer TODOS os itens.
        protocolo = numero_digitado(_campo("protocolo_id"))
        if protocolo is not None:
            marcados = [numero_digitado(x) or -1
                        for x in request.form.getlist("protocolo_item_id")
                        if str(x).strip().isdigit()]
            if marcados:
                lugares = ",".join(["%s"] * len(marcados))
                linhas = banco(con).ler(
                    f"""SELECT id, codigo_ato, quantidade FROM cx_protocolo_atos
                         WHERE protocolo_id=%s AND usado_em IS NULL
                           AND id IN ({lugares})
                           AND codigo_ato IS NOT NULL
                           AND TRIM(codigo_ato) <> ''
                         ORDER BY id""",
                    [protocolo] + marcados)
            else:
                linhas = banco(con).ler(
                    """SELECT id, codigo_ato, quantidade FROM cx_protocolo_atos
                        WHERE protocolo_id=%s AND usado_em IS NULL
                          AND codigo_ato IS NOT NULL
                          AND TRIM(codigo_ato) <> ''
                        ORDER BY id""",
                    (protocolo,))
            itens: list[tuple[str, int]] = []
            for r in linhas:
                codigo = str(r["codigo_ato"])
                quantidade = max(1, int(r["quantidade"] or 1))
                if codigo == CODIGO_TJ_AUTENTICACAO_COPIA:
                    # A EXCEÇÃO: dez cópias autenticadas são dez selos.
                    itens += [(codigo, 1)] * quantidade
                else:
                    # A REGRA: quantidade maior é UM selo com mais folhas.
                    itens.append((codigo, quantidade))
                if ids_usados is not None:
                    ids_usados.append(int(r["id"]))
            if itens:
                return itens
        servicos = [n for n in (numero_digitado(x)
                                for x in request.form.getlist("cobrar"))
                    if n is not None]
        if not servicos:
            return []
        lugares = ",".join(["%s"] * len(servicos))
        return [(r["codigo_tj"], 1) for r in banco(con).ler(
            f"""SELECT codigo_tj FROM cx_servicos WHERE codigo IN ({lugares})
                 AND codigo_tj IS NOT NULL AND TRIM(codigo_tj) <> ''
                 ORDER BY codigo""",
            servicos)]

    def _itens_para_selar_expandido(con, ids_usados: list | None = None
                                    ) -> list[str]:
        """`_itens_para_selar` achatada: um `codigo_tj` por selo A PEDIR.

        Para quem (Protesto, civil) NÃO tem campo de quantidade no envelope
        do selador — o de sempre, um selo por unidade.
        """
        return [codigo for codigo, quantidade in _itens_para_selar(con, ids_usados)
                for _ in range(max(1, quantidade))]

    def _marcar_itens_do_protocolo_como_usados(
            ids_usados: list, ato_id: int, tabela: str = "rg_atos") -> None:
        """Consome os itens do protocolo apontados para este ato. GRAVA.

        Sem isso, o mesmo item ficaria disponível para o PRÓXIMO ato lançado
        do mesmo protocolo — exatamente o defeito que o oficial relatou: a
        segunda averbação pedindo de novo os selos que a primeira já tomou.

        `tabela` diz em qual tabela `ato_id` existe (`rg_atos` para a
        averbação/registro, `at_certidoes` para a certidão) — achado em
        12/09/2026: os dois IDs colidem (há `rg_atos` id=2 e `at_certidoes`
        id=2, sem relação um com o outro), e sem essa marca a ficha do
        protocolo não tem como dizer com segurança quem consumiu o item.
        """
        if not ids_usados:
            return
        lugares = ",".join(["%s"] * len(ids_usados))
        with db.transaction() as con:
            banco(con).escrever(
                f"""UPDATE cx_protocolo_atos
                       SET usado_em=%s, usado_por_ato_id=%s, usado_por_tabela=%s
                     WHERE id IN ({lugares}) AND usado_em IS NULL""",
                [agora(), int(ato_id), tabela] + ids_usados)

    def _soltar_itens_da_certidao_cancelada(con, tabela: str,
                                            certidao_id: int) -> None:
        """O espelho da marca: a certidão que o selo não deixou de pé devolve
        o item ao protocolo (LD06). ESCREVE, na transação do cancelamento.

        Sem isto, a certidão cancelada levava o item: quitado e pedida de novo,
        a certidão do RTD não achava item nenhum e saía EMITIDA, SEM SELO e
        sem aviso (CN-MA art. 130, § 2º). A regra mora no caixa
        (`caixa_protocolo.soltar_itens_do_ato`), ao lado de quem conta o item.
        """
        import caixa_protocolo as CXP
        CXP.soltar_itens_do_ato(con, tabela, int(certidao_id))

    def _itens_ligados_ao_ato(con, tabela: str, ato_id: int) -> list[str]:
        """Os códigos dos itens que a tela já ligou a este ato, um por
        unidade — a forma de `_itens_para_selar_expandido`. Só LÊ."""
        return [str(r["codigo_ato"]) for r in banco(con).ler(
            """SELECT codigo_ato, quantidade FROM cx_protocolo_atos
                WHERE usado_por_tabela = %s AND usado_por_ato_id = %s
                  AND codigo_ato IS NOT NULL AND btrim(codigo_ato) <> ''
                ORDER BY id""", (str(tabela), int(ato_id)))
                for _ in range(max(1, int(r["quantidade"] or 1)))]

    def _selar_o_protesto(tabela: str, ato_id: int, tipo: str) -> str:
        """Um selo para cada item cobrado. FALA COM A REDE.

        FORA DA TRANSAÇÃO DO ATO, como todo pedido de selo desta casa.

        CADA ITEM TEM A SUA REFERÊNCIA — `pt_atos:12:17.4` —, e isso não é
        detalhe: é dela que sai o SID, e é o SID que faz o aparelho devolver o
        selo que já existe em vez de vender outro. Com uma referência só para
        os três itens, o aparelho devolveria o MESMO selo três vezes.
        """
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return SR.recado_pendente_selo()
        ids_do_protocolo: list[int] = []
        with db.connect() as con:
            # O envelope do Protesto não tem campo de quantidade — um selo
            # por unidade, como sempre (ver `_itens_para_selar_expandido`).
            itens = _itens_para_selar_expandido(con, ids_do_protocolo)
            # A BUSCA DA CERTIDÃO NÃO SAI POR AQUI — 15/10/2026. Os 51 selos de
            # busca do Protesto no acervo saíram por `atos-em-geral`, e não
            # pelo caminho da certidão; quem os sela é
            # `_selar_a_busca_da_certidao_do_protesto`, ainda que o item tenha
            # vindo do protocolo.
            if tabela == "pt_certidoes":
                itens = [c for c in itens if not BU.e_item_de_busca(c)]
            # A CERTIDÃO NÃO TEM TÍTULO — quem vai nas partes é a pessoa
            # pesquisada, como em 53 dos 57 envelopes do acervo (15/10/2026).
            pesquisado = (banco(con).um(
                "SELECT nome, documento FROM pt_certidoes WHERE id=%s",
                (int(ato_id),))
                if tabela == "pt_certidoes" else None)
            # O LIVRO DO SELO É O NÚMERO DO LIVRO, e não o `id` da tabela de
            # livros (LT04, 20/10/2026). Mandava-se `livro_id`: o selo do
            # primeiro protesto desta casa declarava «livro 2» (o 1 é o de
            # apontamento) enquanto o registro, o instrumento e a certidão
            # dizem Livro 1 — a consulta pública do selo apontava outro livro.
            dados = banco(con).um(
                f"""SELECT a.*, t.protocolo, t.valor_centavos, t.especie,
                           (SELECT v.numero FROM nu_livros v
                             WHERE v.id = a.livro_id) AS livro_numero
                      FROM {tabela} a
                      LEFT JOIN pt_titulos t ON t.id = a.titulo_id
                     WHERE a.id=%s""", (int(ato_id),))                 if tabela == "pt_atos" else None
            # O ATO DO TÍTULO LEVA O DEVEDOR NAS PARTES — é o que os 1.308
            # selos do protesto do acervo fizeram (`ato_selado.
            # envelope_do_protesto`: «com o nome em `parteAto`»). Ia vazio, e
            # a consulta do selo não dizia contra quem era o ato.
            devedores = (banco(con).ler(
                """SELECT nome, documento_numero FROM pt_devedores
                    WHERE titulo_id=%s ORDER BY id""", (int(dados["titulo_id"]),))
                if dados and dados.get("titulo_id") else [])
        # A CERTIDÃO LIGA O ITEM DO PROTOCOLO ESCOLHIDO ANTES DO SELO (LD06),
        # como a do RTD. O protocolo escolhido no formulário dava o código ao
        # envelope, mas a trava do selo procura o item LIGADO AO ATO — e, sem a
        # ligação, respondia «Ligar o ato a um protocolo do balcão» a quem
        # tinha acabado de escolher o protocolo, com o item pago, e a certidão
        # era cancelada. Liga todos os itens do pedido, a busca inclusive: ela
        # sai depois, por esta mesma certidão (`_itens_ligados_ao_ato`).
        if tabela == "pt_certidoes":
            _marcar_itens_do_protocolo_como_usados(
                ids_do_protocolo, int(ato_id), tabela="pt_certidoes")
        if not itens:
            # O ITEM E ESCOLHA DE QUEM ATENDE, mas sem ele o selo não pode ser
            # montado e o ato não fica ativo.
            return AS.recado_de_falta(
                " O ato foi lavrado SEM SELO: o selo sai pelos itens da "
                "tabela de emolumentos, e este ato não tem protocolo nem "
                "item marcado para cobrança.")
        caminho = AS.caminho_do_ato(tabela, tipo)
        versao = AS.versao_da_tabela_de_custas(
            caminho, db.get_setting("selo_tabela_custas_em", ""))
        saiu, faltou = [], []
        # A MARCA CONSERVA A ORIGEM DA FALHA para o aviso e a auditoria. Tanto
        # a recusa da rede quanto um envelope incompleto bloqueiam o ato.
        recusou_o_aparelho = False
        # **ÍNDICE POR OCORRÊNCIA, e não só por item** — mesma correção do
        # RCPJ/RTD: com `quantidade > 1` o mesmo `codigo_tj` se repete em
        # `itens`, e uma referência igual para as unidades repetidas faria
        # o aparelho devolver o MESMO selo em vez de vender um por unidade.
        ocorrencias: dict[str, int] = {}
        for codigo_tj in itens:
            ocorrencias[codigo_tj] = ocorrencias.get(codigo_tj, 0) + 1
            indice = ocorrencias[codigo_tj]
            try:
                # A INTIMAÇÃO SELA PELO MODO EM QUE ACONTECEU — por edital é
                # outra natureza (`ato_selado.NATUREZA_DA_INTIMACAO`). Sem o
                # modo, a lançada pela ficha selava sempre como pessoal.
                modo = (json.loads(dados["detalhe_json"] or "{}").get("modo")
                        if dados and tipo == "INTIMACAO" else None)
                envelope = AS.envelope_do_protesto(
                    tipo=tipo, tabela=tabela, codigo_tj=codigo_tj, modo=modo,
                    escrevente=usuario_nome(),
                    protocolo=(dados["protocolo"] if dados else None),
                    versao_tabela=versao,
                    livro=(dados["livro_numero"] if dados else None),
                    folha=(dados["folha"] if dados else None),
                    valor_centavos=(dados["valor_centavos"] if dados else None),
                    partes=([{"nome": pesquisado["nome"],
                              "documento": pesquisado["documento"]}]
                            if pesquisado and pesquisado["nome"] else
                            [{"nome": d["nome"], "documento": d["documento_numero"]}
                             for d in devedores if d["nome"]] or None))
            except AS.AtoError as erro:
                faltou.append(str(erro))
                continue
            r = AS.selar_o_ato_lavrado(
                db, Path(app.config["DATA_DIR"]), tabela=tabela, ato_id=ato_id,
                tipo=tipo, atribuicao="PROTESTO", agora=agora(),
                cns=sv().get("ri_cns"), usuario=usuario_nome(), dados=envelope,
                referencia=f"{tabela}:{int(ato_id)}:{codigo_tj}:{indice}")
            recusou_o_aparelho = recusou_o_aparelho or not r["selado"]
            (saiu if r["selado"] else faltou).append(
                r["numero"] if r["selado"] else r["motivo"])
        if saiu and not faltou:
            return f" {len(saiu)} selo(s) obtido(s): {', '.join(saiu)}."
        if saiu:
            return (f" {len(saiu)} selo(s) obtido(s), e {len(faltou)} não: "
                    f"{faltou[0]}")
        marcar = (AS.recado_de_recusa if recusou_o_aparelho
                  else AS.recado_de_falta)
        return marcar(
            f" O ato foi lavrado SEM SELO: {faltou[0] if faltou else ''}")

    def _selar_a_busca_da_certidao_do_protesto(certidao_id: int,
                                               busca: str | None,
                                               nome: str,
                                               documento: str) -> str:
        """O selo da BUSCA da certidão do Protesto. FALA COM A REDE.

        Pedido do oficial, 15/10/2026. **SELO PRÓPRIO, por
        `/selo/protesto/atos-em-geral`**: é o que os 51 selos de busca do
        Protesto no acervo fizeram (17.6.2 em 47), no mesmo protocolo da
        certidão e com a pessoa pesquisada nas partes.

        **SE O PROTOCOLO OU O CAIXA JÁ TRAZ A BUSCA, VALE ESSA** — é o «pelo
        protocolo» do pedido. E a certidão que já inclui a busca no preço
        (17.5.4, 17.5.5) não leva outra.

        A BUSCA QUE NÃO SAI NÃO DESFAZ A CERTIDÃO: ela já tem o seu selo, e a
        tela diz o que faltou — a regra do item da folha acrescida no RI.

        OS ITENS QUE A CERTIDÃO JÁ LIGOU CONTAM (LD06): ligados antes do selo
        da certidão, eles saem da lista dos ainda livres — e a busca que veio
        no protocolo é um deles.
        """
        with db.connect() as con:
            itens = (_itens_ligados_ao_ato(con, "pt_certidoes", certidao_id)
                     + _itens_para_selar_expandido(con))
        if BU.ja_inclui_busca(itens):
            return ""
        codigo = BU.busca_entre(itens) or busca
        if not codigo or not BU.vira_selo(codigo):
            return ""
        caminho = BU.CAMINHO_DO_SELO_DA_BUSCA["PROTESTO"]
        try:
            envelope = BU.envelope_da_busca(
                codigo=codigo, escrevente=usuario_nome(),
                versao_tabela=AS.versao_da_tabela_de_custas(
                    caminho, db.get_setting("selo_tabela_custas_em", "")),
                nome=nome, documento=documento)
        except BU.BuscaError as erro:
            return f" A busca {codigo} ficou SEM SELO: {erro}"
        r = AS.selar_o_ato_lavrado(
            db, Path(app.config["DATA_DIR"]), tabela="pt_certidoes",
            ato_id=certidao_id, tipo="BUSCA", atribuicao="PROTESTO",
            agora=agora(), cns=sv().get("ri_cns"), usuario=usuario_nome(),
            dados=envelope, caminho=caminho,
            referencia=f"pt_certidoes:{int(certidao_id)}:{codigo}:1")
        if r["selado"]:
            return f" Busca {codigo}: selo {r['numero']}."
        return f" A busca {codigo} ficou SEM SELO: {r['motivo']}"

    def _habilitacao_de_fora(ato_id) -> dict | None:
        """A habilitação de OUTRA serventia deste casamento, se houver. Só LÊ.

        É ESTA RESPOSTA QUE DECIDE COMPRAR OU REAPROVEITAR, e ela é uma coisa
        que o escrevente respondeu na tela — nunca uma dedução do sistema.
        Deduzir aqui seria arriscar cobrar do casal duas vezes.
        """
        try:
            with db.connect() as con:
                linha = banco(con).um(
                    """SELECT a.habilitacao_serventia s, a.habilitacao_selo selo
                         FROM rc_atos t JOIN rc_assentos a ON a.id = t.assento_id
                        WHERE t.id = %s""", (int(ato_id),))
        except sqlite3.Error:
            return None
        if not linha or not (linha["s"] or "").strip():
            return None
        return {"serventia": linha["s"].strip(),
                "selo": (linha["selo"] or "").strip() or None}

    def _habilitacao_do_livro_d(ato_id) -> bool:
        """O ato é o registro no Livro D do edital de uma habilitação desta
        casa? Só LÊ. (LD01 — ver `_selar_o_ato`.)"""
        with db.connect() as con:
            bd = banco(con)
            if not bd.tem_coluna("hc_habilitacoes", "proclamas_assento_id"):
                return False
            return bd.um(
                """SELECT h.id FROM rc_atos t
                     JOIN hc_habilitacoes h
                       ON h.proclamas_assento_id = t.assento_id
                    WHERE t.id = %s ORDER BY h.id LIMIT 1""",
                (int(ato_id),)) is not None

    def _habilitacao_do_assento(con, assento_id) -> dict | None:
        """A habilitação que autorizou aquele casamento, se ela é desta casa.

        DEVOLVE None SEM RECLAMAR quando não há — e não há em dois casos
        legítimos: o casamento lavrado à vista de certidão de habilitação de
        OUTRA serventia (item 14.1.6 da tabela), e o assento antigo trazido
        pela carga, de quando este sistema não existia. Nenhum dos dois é
        defeito, e nenhum dos dois pode impedir o selo de sair.

        A TABELA PODE AINDA NÃO EXISTIR neste banco, e por isso o `try`: quem
        atualizar o sistema sem ter passado pela migração da habilitação
        continua selando casamento como sempre selou.
        """
        try:
            h = banco(con).um(
                """SELECT numero, ano, tipo, selo, nubente1_nome, nubente2_nome
                     FROM hc_habilitacoes
                    WHERE casamento_assento_id = %s OR proclamas_assento_id = %s
                    ORDER BY id DESC LIMIT 1""",
                (int(assento_id), int(assento_id)))
        except sqlite3.Error:
            return None
        if not h:
            return None
        return {"tipo": h["tipo"], "selo": h["selo"],
                "nubente1_nome": h["nubente1_nome"],
                "nubente2_nome": h["nubente2_nome"],
                "processo": (f"{h['numero']}/{h['ano']}"
                             if h["numero"] and h["ano"] else None)}

    def _envelope_do_civil(tabela: str, ato_id: int, tipo: str, especie,
                           papel, codigo_tj=None,
                           habilitacao_de_fora: dict | None = None,
                           isento: bool = False,
                           motivo_isencao: str | None = None,
                           quantidade: int = 1) -> dict:
        """Monta o pacote que vai ao selador. Só LÊ o banco.

        O LIVRO, A FOLHA E O TERMO SAEM DO ATO, e é por isso que o selo do
        civil só se pede depois de o ato existir. O nome sai do assento, que é
        de quem o ato é.
        """
        habilitacao = None
        with db.connect() as con:
            if tabela == "rc_certidoes":
                linha = banco(con).um(
                    """SELECT c.*, a.numero termo_assento, a.livro_volume,
                              (SELECT t.rotulo FROM rc_atos t
                                WHERE t.assento_id = c.assento_id
                                  AND t.tipo = 'REGISTRO'
                                ORDER BY t.id LIMIT 1) folha,
                              (SELECT t.livro_id FROM rc_atos t
                                WHERE t.assento_id = c.assento_id
                                  AND t.tipo = 'REGISTRO'
                                ORDER BY t.id LIMIT 1) livro_id
                         FROM rc_certidoes c
                         JOIN rc_assentos a ON a.id = c.assento_id
                        WHERE c.id=%s""", (int(ato_id),))
                nome = (linha["nome"] if linha else "") or ""
            else:
                linha = banco(con).um(
                    """SELECT t.*, a.nome, a.numero termo_assento,
                              a.livro_volume
                         FROM rc_atos t JOIN rc_assentos a ON a.id = t.assento_id
                        WHERE t.id=%s""", (int(ato_id),))
                nome = (linha["nome"] if linha else "") or ""
                if linha is not None:
                    habilitacao = _habilitacao_do_assento(
                        con, linha["assento_id"])
            livro = ""
            if linha and linha["livro_volume"]:
                livro = str(linha["livro_volume"])
            elif linha and linha["livro_id"]:
                achado = banco(con).um(
                    "SELECT numero FROM nu_livros WHERE id=%s",
                    (linha["livro_id"],))
                livro = str(achado["numero"]) if achado else ""
            # CERTIDÃO DE ACERVO/ARQUIVO SEM ATO REGISTRO — a subquery de folha
            # no REGISTRO volta vazia (ex.: Eldo id 1222). Livro já veio de
            # `livro_volume`; folha/termo saem da matrícula.
            if (tabela == "rc_certidoes" and linha is not None
                    and not str(linha["folha"] or "").strip()):
                try:
                    p = MAT.partes(linha["matricula"])
                except MAT.MatriculaError:
                    p = None
                if p:
                    folha_m = str(int(p["folha"])) if str(p.get("folha") or "").strip() else ""
                    termo_m = str(int(p["termo"])) if str(p.get("termo") or "").strip() else ""
                    # a linha vira dict nosso, para completar.
                    linha = dict(linha)
                    linha["folha"] = folha_m or linha.get("folha")
                    if not str(linha.get("termo_assento") or "").strip() and termo_m:
                        linha["termo_assento"] = termo_m
                    if not livro:
                        num = str(int(p["livro"])) if str(p.get("livro") or "").strip() else ""
                        letra = str(p.get("livro_nome") or "").strip()
                        livro = f"{letra}-{num}" if letra and num else num
        if not linha:
            raise AS.AtoError("Não achei o ato para montar o selo.")
        versao = AS.versao_da_tabela_de_custas(
            AS.caminho_do_civil(especie, tipo),
            db.get_setting("selo_tabela_custas_em", ""))
        # ------------------------------------------- o segundo selo do casamento
        #
        # DOIS SELOS, UM NA HABILITAÇÃO E OUTRO NO ASSENTO — decisão do oficial
        # em 28/08/2026. Este é o segundo, e ele não tem a forma dos outros do
        # civil: `DadosSeloCasamento` pede `tipoCasamento` (obrigatório) e
        # aceita `seloReferencia`, que é o campo por onde o selo do assento
        # **cita o selo da habilitação** que o autorizou.
        #
        # SEM ESSE ELO, A CONFERÊNCIA TERIA DE JUNTAR OS DOIS PELO NOME DOS
        # NUBENTES — e nome junta errado: há homônimo, e há casal que casa duas
        # vezes. O contrato criou o campo justamente para não ser assim.
        #
        # A HABILITAÇÃO PODE NÃO ESTAR AQUI, e isso é caso real e previsto na
        # tabela: o item `14.1.6` é «lavratura de assento de casamento à vista
        # de certidão de habilitação emitida por OUTRA serventia». Aí não há
        # selo daqui a referenciar, e o campo fica de fora — que é o que
        # `optional` quer dizer. Não se inventa referência.
        # O REGISTRO DE PROCLAMAS NO LIVRO D SELA PELO CAMINHO DA HABILITAÇÃO
        # — é a mesma coisa: o edital é o ato da habilitação. E aquele caminho
        # pede `tipoCasamento`, que o envelope comum do civil não tem; mandado
        # pelo caminho comum, o aparelho recusaria. O item é o `14.1.2`
        # («afixação, publicação e arquivamento de edital de proclamas»), que
        # `codigo_do_ato_do_civil` já resolve.
        if (tabela == "rc_atos"
                and str(tipo or "").strip().upper() == "REGISTRO"
                and str(especie or "").strip().upper() == "PROCLAMAS"):
            return AS.envelope_da_habilitacao(
                escrevente=usuario_nome(), versao_tabela=versao,
                tipo=((habilitacao or {}).get("tipo") or "CIVIL"),
                livro=livro, folha=linha["folha"], termo=linha["termo_assento"],
                numero_processo=(habilitacao or {}).get("processo"),
                codigo_tj=(codigo_tj
                           or AS.codigo_do_ato_do_civil(especie, tipo)[0]),
                nubente1={"nome": (habilitacao or {}).get("nubente1_nome") or nome},
                nubente2={"nome": (habilitacao or {}).get("nubente2_nome")})
        # O CASAMENTO À VISTA DE HABILITAÇÃO DE OUTRA SERVENTIA — item 14.1.6,
        # e o único caso em que o assento compra selo. Decisão do oficial em
        # 28/08/2026: aqui não há selo desta casa a reaproveitar, porque quem
        # habilitou e selou foi o outro cartório.
        #
        # `seloReferencia` cita o selo de lá e `localRealizacaoHabilitacao` diz
        # onde a habilitação foi feita — os dois campos existem no contrato
        # exatamente para isto.
        de_fora = ((habilitacao_de_fora or {}) if tabela == "rc_atos" else {})
        if de_fora and str(tipo or "").strip().upper() == "REGISTRO":
            return AS.envelope_do_casamento(
                escrevente=usuario_nome(), versao_tabela=versao,
                tipo=("RELIGIOSO"
                      if str(especie).strip().upper() == "CASAMENTO_RELIGIOSO"
                      else "CIVIL"),
                livro=livro, folha=linha["folha"], termo=linha["termo_assento"],
                papel=papel, codigo_tj=codigo_tj,
                selo_da_habilitacao=de_fora.get("selo"),
                local_da_habilitacao=de_fora.get("serventia"),
                nubente1={"nome": nome})
        inteiro = False
        if tabela == "rc_certidoes":
            try:
                mod = (linha["modalidade"] if not isinstance(linha, dict)
                       else linha.get("modalidade"))
            except (KeyError, IndexError, TypeError):
                mod = None
            inteiro = RCIT.e_inteiro_teor(mod)
        # AVERBAÇÃO USA SCHEMA PRÓPRIO — DadosSeloAverbacaoRegistroCivil
        # (codigoAto + alteracao + tipoAverbacao), não codigoTipoAtoRegistro.
        folha_ato = str(linha["folha"] or "").strip()
        termo_ato = str(linha["termo_assento"] or "").strip()
        if (not folha_ato or not termo_ato or not livro) and linha is not None:
            mat = None
            try:
                mat = linha["matricula"] if "matricula" in linha.keys() else None
            except Exception:
                mat = None
            if not mat:
                try:
                    with db.connect() as _c:
                        aid = int(linha["assento_id"])
                        ass = banco(_c).um(
                            "SELECT matricula, numero, livro_volume, dados_json "
                            "FROM rc_assentos WHERE id=%s", (aid,))
                        if ass:
                            mat = ass["matricula"]
                            if not livro and ass["livro_volume"]:
                                livro = str(ass["livro_volume"])
                            if not termo_ato and ass["numero"]:
                                termo_ato = str(ass["numero"])
                            if (not folha_ato or not livro) and ass["dados_json"]:
                                try:
                                    dj = json.loads(ass["dados_json"] or "{}")
                                except (TypeError, ValueError):
                                    dj = {}
                                if not folha_ato and str(dj.get("folha") or "").strip():
                                    folha_ato = str(dj["folha"]).strip()
                                if not livro:
                                    lt = str(dj.get("livro_tipo") or "").strip()
                                    ln = str(dj.get("livro_numero") or "").strip()
                                    if lt and ln:
                                        livro = f"{lt}-{ln}"
                except Exception:
                    mat = None
            if mat:
                try:
                    p = MAT.partes(mat)
                except MAT.MatriculaError:
                    p = None
                if p:
                    if not folha_ato and str(p.get("folha") or "").strip():
                        folha_ato = str(int(p["folha"]))
                    if not termo_ato and str(p.get("termo") or "").strip():
                        termo_ato = str(int(p["termo"]))
                    if not livro:
                        num = (str(int(p["livro"]))
                               if str(p.get("livro") or "").strip() else "")
                        letra = str(p.get("livro_nome") or "").strip()
                        livro = f"{letra}-{num}" if letra and num else num

        if str(tipo or "").strip().upper() == "AVERBACAO":
            teor = ""
            try:
                teor = str(linha["teor"] or "").strip()
            except Exception:
                teor = ""
            if not teor:
                teor = (_campo("teor") or _campo("alteracao")
                        or _campo("texto") or "").strip()
            # Preferir natureza do select (chave → tipo_selo quando MEDIDO).
            # Compatível com tipo_averbacao numérico direto (API/legado).
            natureza_av = (_campo("natureza_averbacao") or "").strip()
            tipo_av = (_campo("tipo_averbacao")
                       or _campo("tipoAverbacao") or "")
            if natureza_av:
                resolvido = AS.tipo_selo_da_natureza_averbacao(natureza_av)
                if resolvido is not None:
                    tipo_av = resolvido
                elif not str(tipo_av).strip():
                    # SEM TIPO, O SELO FALHA — e falhar quer dizer que o
                    # ato nao fica: a caixa «lavrar mesmo se o selo
                    # falhar» saiu em 16/09/2026, pelo relato #77.
                    tipo_av = ""
            if not str(tipo_av).strip():
                desc = (teor + " " + str(motivo_isencao or "")).upper()
                if "CPF" in desc or "347" in desc or isento:
                    tipo_av = AS.TIPO_AVERBACAO_CPF_ART_347
            return AS.envelope_da_averbacao_civil(
                escrevente=usuario_nome(), livro=livro,
                folha=folha_ato, termo=termo_ato,
                versao_tabela=versao, alteracao=teor,
                tipo_averbacao=tipo_av,
                codigo_tj=codigo_tj or "14.4.1",
                isento=isento, motivo_isencao=motivo_isencao,
                quantidade=quantidade)

        return AS.envelope_do_civil(
            especie=especie, tipo=tipo,
            escrevente=usuario_nome(), livro=livro,
            folha=folha_ato or linha["folha"],
            termo=termo_ato or linha["termo_assento"],
            nome_parte=nome,
            versao_tabela=versao,
            papel=papel, codigo_tj=codigo_tj,
            isento=isento, motivo_isencao=motivo_isencao,
            inteiro_teor=inteiro)


    def _envelope_do_rtdpj(tabela: str, ato_id: int, tipo: str, serie,
                           codigo_tj=None, quantidade=1) -> tuple[dict, str]:
        """Monta o pacote RTDPJ e devolve (envelope, caminho). Só LÊ.

        A SERIE decide o caminho da averbação (PJ vs título). Sem protocolo
        na averbação específica, cai em `atos-em-geral` — medido, e sem
        inventar número de protocolo.

        `quantidade` É FOLHAS, E NÃO SELOS — correção do oficial em
        11/09/2026: item de tabela com quantidade maior (`15.9.2`, por
        exemplo — "por folha que exceder") pede UM selo com mais folhas, e
        não vários selos. Vai direto no campo `quantidade` do envelope
        (`AS.envelope_do_rtdpj`), que o contrato do selador já tem para isso.
        """
        with db.connect() as con:
            bd = banco(con)
            linha = bd.um(
                """SELECT a.*, r.serie, r.natureza, r.requerente_nome,
                          r.requerente_documento, r.numero AS registro_numero,
                          r.titulo_id,
                          (SELECT numero FROM nu_livros WHERE id = a.livro_id)
                              AS livro_numero
                     FROM rg_atos a
                     JOIN rg_registros r ON r.id = a.registro_id
                    WHERE a.id=%s""", (int(ato_id),))
            protocolo = None
            # 1) o protocolo do formulário (caixa geral)
            pid = numero_digitado(_campo("protocolo_id"))   # LD13: texto é nenhum
            if pid is not None:
                achado = bd.um(
                    "SELECT numero FROM cx_protocolos WHERE id=%s",
                    (pid,))
                if achado and achado["numero"]:
                    protocolo = str(achado["numero"]).strip()
            # 2) o protocolo do título amarrado ao registro
            if not protocolo and linha and linha["titulo_id"]:
                tit = bd.um(
                    "SELECT numero FROM rg_titulos WHERE id=%s",
                    (int(linha["titulo_id"]),))
                if tit and tit["numero"] is not None:
                    protocolo = str(tit["numero"]).strip()
            # 3) protocolo_id já gravado no próprio ato
            if not protocolo and linha and linha["protocolo_id"]:
                achado = bd.um(
                    "SELECT numero FROM cx_protocolos WHERE id=%s",
                    (int(linha["protocolo_id"]),))
                if achado and achado["numero"]:
                    protocolo = str(achado["numero"]).strip()
        if not linha:
            raise AS.AtoError("Não achei o ato para montar o selo do RCPJ/RTD.")
        serie_u = str(serie or linha["serie"] or "").strip().upper()
        caminho = AS.caminho_do_rtdpj(tipo, serie_u)
        if not caminho:
            raise AS.AtoError(
                f"Não há caminho de selo para {tipo} no RCPJ/RTD.")
        # Sem protocolo na averbação específica: não inventa — usa o caminho
        # genérico medido (atos-em-geral), que não pede protocolo.
        if (caminho != AS.CAMINHO_RTDPJ_GERAL
                and not str(protocolo or "").strip()):
            caminho = AS.CAMINHO_RTDPJ_GERAL
        versao = AS.versao_da_tabela_de_custas(
            caminho, db.get_setting("selo_tabela_custas_em", ""))
        if not versao:
            raise AS.AtoError(
                "Falta dizer de que data é a tabela de custas em vigor, em "
                "Administrativo → Configurações.")
        if not codigo_tj:
            raise AS.AtoError(
                "O selo do RCPJ/RTD sai pelos itens da tabela de emolumentos, "
                "e este ato não tem item marcado.")
        partes = []
        nome = (linha["requerente_nome"] or "").strip()
        if nome:
            partes.append({"nome": nome,
                           "documento": linha["requerente_documento"] or ""})
        return AS.envelope_do_rtdpj(
            caminho=caminho, codigo_tj=codigo_tj, escrevente=usuario_nome(),
            versao_tabela=versao, partes=partes,
            natureza_descricao=linha["natureza"] or tipo,
            livro=linha["livro_numero"] or "",
            folha=linha["folha"],
            protocolo=protocolo,
            registro_averbacao=(linha["numero_ordem"]
                                if linha["numero_ordem"] is not None
                                else linha["registro_numero"]),
            quantidade=quantidade), caminho

    # O código TJ do arquivamento — 1ª averbação do pacote, selo à parte
    # (`rg_teor_rtdpj.SELO_FAIXA_ROTULO_ARQUIVAMENTO`). É o mesmo literal
    # que `cx_protocolo_atos.codigo_ato` traz e que `tem_selo_arquivamento`
    # já procurava dentro do texto do selo — aqui ele decide para qual
    # coluna o número vai, e não só qual rótulo mostrar.
    CODIGO_TJ_ARQUIVAMENTO_RTDPJ = "15.22"

    def _selar_o_rtdpj(tabela: str, ato_id: int, tipo: str, atribuicao: str,
                      serie=None) -> str:
        """Pede o selo RTDPJ ao aparelho DEPOIS de o ato existir. FALA COM A REDE.

        Mesma regra do civil e do protesto: fora da transação do ato; um selo
        por item; se a máquina cair, o ato fica sem selo (atos_sem_selo) —
        nunca com número inventado.

        **CADA AVERBAÇÃO TEM O SEU PRÓPRIO SELO, E A 1ª DO PACOTE TAMBÉM
        COMPRA O DE ARQUIVAMENTO** — dois números, não um. `selar_o_ato_lavrado`
        grava cada resposta em `rg_atos.selo` (`vincular_ao_ato`), e chamá-lo
        duas vezes para o MESMO ato — uma para o item da averbação, outra para
        o `15.22` — fazia a segunda sobrescrever a primeira: o registro 361
        (Santa Isabel) ficou só com o selo de arquivamento, e o da averbação
        sumiu da coluna (continuava em `sd_selos`, sem lugar na ficha nem na
        etiqueta). A correção de baixo não muda o pedido ao aparelho — muda
        só para onde cada resposta vai depois: `selo` é sempre o da própria
        averbação; `selo_arquivamento` é gravado à parte.
        """
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return SR.recado_pendente_selo()
        ids_do_protocolo: list[int] = []
        with db.connect() as con:
            itens = _itens_para_selar(con, ids_do_protocolo)
            if not serie:
                linha = banco(con).um(
                    """SELECT r.serie FROM rg_atos a
                         JOIN rg_registros r ON r.id = a.registro_id
                        WHERE a.id=%s""", (int(ato_id),))
                serie = (linha["serie"] if linha else "") or ""
        # OS ITENS APONTADOS PARA ESTE ATO SE CONSOMEM AQUI — antes de pedir
        # selo, e não depois: é o apontamento do operador (protocolo_item_id)
        # que decide, e um selo que falhe não devolve o item ao protocolo (o
        # ato já reivindicou aquele item da tabela de emolumentos).
        _marcar_itens_do_protocolo_como_usados(ids_do_protocolo, int(ato_id))
        if not itens:
            return AS.recado_de_falta(
                " O ato foi lavrado SEM SELO: o selo sai pelos itens da "
                "tabela de emolumentos, e este ato não tem protocolo nem "
                "item marcado para cobrança.")
        saiu, faltou = [], []
        recusou_o_aparelho = False      # ver o Protesto, acima
        selos_por_codigo: list[tuple[str, str]] = []
        # **A REFERÊNCIA PRECISA SER ÚNICA POR OCORRÊNCIA, E NÃO SÓ POR
        # ITEM** — achado do oficial em 11/09/2026, ao ver selo com valor
        # "totalmente errado ao orçamento". Isso valia enquanto o mesmo
        # `codigo_tj` repetia N vezes em `itens` para uma quantidade N — o
        # que ele mesmo corrigiu no mesmo dia: **quantidade maior é UM selo
        # com mais folhas**, e não N selos (a única exceção é a autenticação
        # de cópia, que `_itens_para_selar` já expande à parte). Por isso o
        # índice de ocorrência quase nunca é usado agora — mas continua
        # existindo para o caso raro de o MESMO código aparecer em mais de
        # um item do protocolo (duas linhas de `15.9.1`, por exemplo).
        ocorrencias: dict[str, int] = {}
        for codigo_tj, quantidade in itens:
            ocorrencias[codigo_tj] = ocorrencias.get(codigo_tj, 0) + 1
            indice = ocorrencias[codigo_tj]
            try:
                envelope, caminho = _envelope_do_rtdpj(
                    tabela, ato_id, tipo, serie, codigo_tj,
                    quantidade=quantidade)
            except (AS.AtoError, sqlite3.Error) as erro:
                faltou.append(str(erro))
                continue
            # caminho_do_ato(rg_atos, …) já resolve pela série; selar_o_ato_lavrado
            # consulta de novo — passamos especie=serie para bater com o envelope.
            r = AS.selar_o_ato_lavrado(
                db, Path(app.config["DATA_DIR"]), tabela=tabela, ato_id=ato_id,
                tipo=tipo, atribuicao=atribuicao, agora=agora(),
                cns=sv().get("ri_cns"), usuario=usuario_nome(),
                especie=serie, dados=envelope, caminho=caminho,
                referencia=f"{tabela}:{int(ato_id)}:{codigo_tj}:{indice}")
            recusou_o_aparelho = recusou_o_aparelho or not r["selado"]
            if r["selado"]:
                saiu.append(r["numero"])
                selos_por_codigo.append((str(codigo_tj), r["numero"]))
            else:
                faltou.append(r["motivo"])
        # QUAL SELO É O DA AVERBAÇÃO: o primeiro que não é prenotação (15.1)
        # nem arquivamento (15.22). Até 09/10/2026 era «o primeiro que não é
        # arquivamento», e a prenotação, que vem antes na lista do protocolo,
        # ficou na coluna da averbação 378 — e na etiqueta impressa seis vezes.
        selo_averbacao, selo_arquivamento = RG.papel_dos_selos(selos_por_codigo)
        if tabela == "rg_atos" and (selo_averbacao or selo_arquivamento):
            # Corretivo, DEPOIS do laço: cada chamada acima já escreveu em
            # `selo` por conta própria (vincular_ao_ato); aqui garantimos que
            # o valor final é o certo em cada coluna, não o que sobrou por
            # último ter sido processado.
            with db.transaction() as con:
                if selo_averbacao:
                    banco(con).escrever("UPDATE rg_atos SET selo=%s WHERE id=%s",
                                        (selo_averbacao, int(ato_id)))
                if selo_arquivamento:
                    banco(con).escrever(
                        "UPDATE rg_atos SET selo_arquivamento=%s WHERE id=%s",
                        (selo_arquivamento, int(ato_id)))
        if not saiu:
            marcar = (AS.recado_de_recusa if recusou_o_aparelho
                      else AS.recado_de_falta)
            return marcar(
                f" O ato foi lavrado SEM SELO: {faltou[0] if faltou else ''}")
        recado = f" {len(saiu)} selo(s): {', '.join(saiu)}."
        if faltou:
            recado += f" ({len(faltou)} item(ns) sem selo: {faltou[0]})"
        return recado

    def _selar_a_certidao_rtdpj(certidao_id: int, registro_id: int,
                               atribuicao: str, ja_dito: str,
                               busca: str | None = None) -> str:
        """Pede selo para a certidão RCPJ/RTD, pelos itens do protocolo.

        FALA COM A REDE — fora da transação da certidão, mesma regra de
        sempre. Achado do oficial em 11/09/2026: emitir certidão **não
        selava nada** — a tela nunca tinha o campo de escolher protocolo
        nem itens (corrigido em `_certidao.html`), e a rota só sabia pedir
        selo se o operador digitasse o número à mão
        (`_selar_se_pedido`). Este é o caminho automático, espelhando
        `_selar_o_rtdpj`, mas pelo caminho genérico do selador — a
        certidão não tem livro/folha/protocolo de averbação para o
        schema `RtdpjSemValorDeclarado` exigir.
        """
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return SR.recado_pendente_selo()
        if ja_dito:
            return ja_dito
        ids_do_protocolo: list[int] = []
        with db.connect() as con:
            itens = _itens_para_selar(con, ids_do_protocolo)
            linha = banco(con).um(
                """SELECT requerente_nome, requerente_documento
                     FROM rg_registros WHERE id=%s""", (int(registro_id),)
            )
        _marcar_itens_do_protocolo_como_usados(
            ids_do_protocolo, int(certidao_id), tabela="at_certidoes")
        if not itens:
            # O PROTOCOLO ESCOLHIDO SEM ITEM PARA A CERTIDÃO NÃO PASSA CALADO
            # (LD06). Devolver vazio aqui fazia a certidão sair EMITIDA e SEM
            # SELO, sem aviso nenhum (LT05) — e nenhum ato sujeito a selo se
            # expede sem ele (CN-MA art. 130, § 2º). Quem escolheu o protocolo
            # esperava o selo dele; a falta cancela a certidão e diz o porquê.
            if _campo("protocolo_id"):
                return AS.recado_de_falta(
                    " A certidão saiu SEM SELO: o protocolo escolhido não tem "
                    "item disponível para ela — os itens já foram usados por "
                    "outros atos. Acrescente o item da certidão ao protocolo e "
                    "peça de novo.")
            return ""
        # A BUSCA DO RTD/PJ É MAIS UM ITEM PELO MESMO `atos-em-geral` —
        # decisão do oficial, 15/10/2026 (o acervo não tem nenhuma). Se o
        # protocolo já trouxe a busca, ela já está entre os itens e vale ela.
        if (busca and BU.vira_selo(busca)
                and not BU.busca_entre(itens, "RTDPJ")):
            itens = list(itens) + [(busca, 1)]
        versao = AS.versao_da_tabela_de_custas(
            AS.CAMINHO_RTDPJ_GERAL, db.get_setting("selo_tabela_custas_em", ""))
        if not versao:
            # FALTA DE CONFIGURACAO: ninguem disse de que data e a tabela.
            return AS.recado_de_falta(
                " A certidão saiu SEM SELO: falta dizer de que data é a "
                "tabela de custas em vigor, em Administrativo → "
                "Configurações.")
        partes = []
        if linha and linha["requerente_nome"]:
            partes.append({"nome": linha["requerente_nome"],
                           "documento": linha["requerente_documento"] or ""})
        saiu, faltou = [], []
        recusou_o_aparelho = False      # ver o Protesto, acima
        ocorrencias: dict[str, int] = {}
        for codigo_tj, quantidade in itens:
            ocorrencias[codigo_tj] = ocorrencias.get(codigo_tj, 0) + 1
            indice = ocorrencias[codigo_tj]
            envelope = AS.envelope_do_rtdpj(
                caminho=AS.CAMINHO_RTDPJ_GERAL, codigo_tj=codigo_tj,
                escrevente=usuario_nome(), versao_tabela=versao, partes=partes,
                quantidade=quantidade)
            r = AS.selar_o_ato_lavrado(
                db, Path(app.config["DATA_DIR"]), tabela="at_certidoes",
                ato_id=certidao_id, tipo="CERTIDAO", atribuicao=atribuicao,
                agora=agora(), cns=sv().get("ri_cns"), usuario=usuario_nome(),
                dados=envelope, caminho=AS.CAMINHO_RTDPJ_GERAL,
                referencia=f"at_certidoes:{int(certidao_id)}:{codigo_tj}:{indice}")
            recusou_o_aparelho = recusou_o_aparelho or not r["selado"]
            if r["selado"]:
                saiu.append(r["numero"])
            else:
                faltou.append(r["motivo"])
        if not saiu:
            marcar = (AS.recado_de_recusa if recusou_o_aparelho
                      else AS.recado_de_falta)
            return marcar(
                f" A certidão saiu SEM SELO: {faltou[0] if faltou else ''}")
        recado = f" {len(saiu)} selo(s): {', '.join(saiu)}."
        if faltou:
            recado += f" ({len(faltou)} item(ns) sem selo: {faltou[0]})"
        return recado

    def _selar_a_certidao_do_livro3(certidao_id: int, registro_id: int,
                                    folhas: int, ja_dito: str,
                                    busca: str | None = None) -> str:
        """Pede o selo da certidão do Livro 3. FALA COM A REDE.

        **ELA NUNCA SELOU SOZINHA, e havia caminho medido** — 21/09/2026. O
        comentário desta rota dizia que «só o RCPJ/RTD tem o caminho genérico
        medido; o Livro 3 continua como estava». A medição do acervo desmentiu:
        as **9** certidões deste livro têm selo de `/selo/imovel/certidao` no
        protocolo delas, e em duas não há outro caminho no protocolo inteiro.

        **FORA DA TRANSAÇÃO, e sem derrubar o que já existe** — a certidão está
        gravada, com número e hash, quando esta função é chamada. O campo de
        digitar o selo à mão fica, porque o selador é máquina da rede local e
        cai; se o operador digitou, aqui não se pede outro.

        **A QUANTIDADE É O NÚMERO DE FOLHAS**, como nos 667 envelopes do RI. Na
        certidão por reprodução ela é contada do arquivo; na de texto é uma,
        que é o que a casa manda quando não sabe dizer outra coisa.
        """
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return SR.recado_pendente_selo()
        if ja_dito:
            return ja_dito
        try:
            versao = AS.versao_da_tabela_de_custas(
                RS.CAMINHO_DA_CERTIDAO,
                db.get_setting("selo_tabela_custas_em", ""))
            if not versao:
                raise AS.AtoError(
                    "falta dizer de que data é a tabela de custas em vigor, em "
                    "Administrativo → Configurações.")
            with db.connect() as con:
                c = banco(con).um(
                    """SELECT requerente, requerente_documento, registro_numero
                         FROM at_certidoes WHERE id=%s""",
                    (int(certidao_id),))
            #  UM SELO POR ITEM — medido: a certidão de mais de uma folha
            #  saiu com DOIS selos (o inteiro teor e a folha acrescida) em 99
            #  dos protocolos do acervo. Ver `ra_selo.itens_da_certidao`.
            #
            #  **CADA ITEM LEVA A SUA PRÓPRIA REFERÊNCIA**: é dela que sai o
            #  SID, e uma referência só para dois itens faria o aparelho
            #  devolver o mesmo selo duas vezes.
            saiu, faltou = [], []
            recusou = False
            for codigo, quantidade in RS.itens_da_certidao(folhas):
                envelope = RS.envelope_da_certidao(
                    escrevente=usuario_nome(), versao_tabela=versao,
                    registro_numero=(c["registro_numero"] if c else ""),
                    quantidade=quantidade, codigo=codigo,
                    requerente=(c["requerente"] if c else None),
                    requerente_documento=(
                        c["requerente_documento"] if c else None))
                r = AS.selar_o_ato_lavrado(
                    db, Path(app.config["DATA_DIR"]), tabela="at_certidoes",
                    ato_id=certidao_id, tipo="CERTIDAO", atribuicao="LIVRO3",
                    agora=agora(), cns=sv().get("ri_cns"),
                    usuario=usuario_nome(), dados=envelope,
                    caminho=RS.CAMINHO_DA_CERTIDAO,
                    referencia=f"at_certidoes:{int(certidao_id)}:{codigo}")
                recusou = recusou or not r["selado"]
                (saiu if r["selado"] else faltou).append(
                    r["numero"] if r["selado"] else r["motivo"])
        except (AS.AtoError, ValueError) as erro:
            return AS.recado_de_falta(f" A certidão saiu SEM SELO: {erro}")
        if not saiu:
            marcar = AS.recado_de_recusa if recusou else AS.recado_de_falta
            return marcar(
                f" A certidão saiu SEM SELO: {faltou[0] if faltou else ''}")
        recado = f" {len(saiu)} selo(s): {', '.join(saiu)}."
        if faltou:
            recado += f" ({len(faltou)} item(ns) sem selo: {faltou[0]})"
        # A BUSCA DO LIVRO 3 SEGUE A DO RESTO DO RI — resposta do oficial,
        # 15/10/2026: selo próprio por `/selo/imovel/atos-em-geral`, depois da
        # certidão, e a do protocolo vale antes da escolhida na tela.
        with db.connect() as con:
            busca = BU.busca_entre(_itens_para_selar(con), "IMOVEL") or busca
        if busca and BU.vira_selo(busca):
            caminho_b = BU.CAMINHO_DO_SELO_DA_BUSCA["IMOVEL"]
            try:
                envelope_b = BU.envelope_da_busca(
                    codigo=busca, escrevente=usuario_nome(),
                    versao_tabela=AS.versao_da_tabela_de_custas(
                        caminho_b, db.get_setting("selo_tabela_custas_em", "")),
                    nome=((c["requerente"] if c else None)
                          or f"REGISTRO {(c['registro_numero'] if c else '')}"),
                    documento=(c["requerente_documento"] if c else None))
            except BU.BuscaError as erro:
                return recado + f" A busca {busca} ficou SEM SELO: {erro}"
            rb = AS.selar_o_ato_lavrado(
                db, Path(app.config["DATA_DIR"]), tabela="at_certidoes",
                ato_id=certidao_id, tipo="BUSCA", atribuicao="LIVRO3",
                agora=agora(), cns=sv().get("ri_cns"), usuario=usuario_nome(),
                dados=envelope_b, caminho=caminho_b,
                referencia=f"at_certidoes:{int(certidao_id)}:{busca}")
            recado += (f" Busca {busca}: selo {rb['numero']}." if rb["selado"]
                       else f" A busca {busca} ficou SEM SELO: {rb['motivo']}")
        return recado

    def _selo_para_teor(con, numero: str | None) -> dict | None:
        """O que o selo declara, pronto para o carimbo do teor. SÓ LÊ.

        NO MODELO DO RI: o teor não recebe uma etiqueta à parte para colar —
        recebe o que o selo já declarou (`sd_selos.texto`), a mesma régua de
        `selo_no_papel` da certidão do RCPN e da etiqueta de firma. Sem selo
        (prévia, ou ato que ainda não selou), devolve `None` e a faixa
        continua sendo a moldura «cole aqui» de sempre — não se inventa selo.
        """
        numero = str(numero or "").strip()
        if not numero:
            return None
        linha = banco(con).um(
            "SELECT texto FROM sd_selos WHERE numero=%s ORDER BY id",
            (numero,))
        texto = str((linha["texto"] if linha else "") or "").strip()
        # O QR LEVA O ENDERECO DA CONSULTA DAQUELE SELO — 24/09/2026. O
        # `qr_token` do aparelho saiu do caminho: token cru nao e link, e o
        # portal procura pelo NUMERO. Ver `notas_selo`.
        marca = NSELO.marca_do_selo(numero)
        return {"numero": numero, "texto": texto,
                "qr_texto": marca["qr_texto"]}

    def _selos_extras_para_teor(con, tabela: str,
                                ato_id: int,
                                ja_mostrados: set) -> list[dict]:
        """Os selos do ato que NÃO couberam em `selo`/`selo_arquivamento`.

        Achado do oficial em 11/09/2026: um ato pode ter vários itens da
        tabela de emolumentos (`15.1` + `15.9.1` no mesmo ato, por exemplo),
        e cada um vira o SEU PRÓPRIO selo — mas `rg_atos` só guarda dois
        números. `AS.selos_do_ato` traz TODOS; aqui filtramos os que já vão
        aparecer nas duas caixas nomeadas, para não imprimir duas vezes.
        """
        extras = []
        for linha in AS.selos_do_ato(con, tabela, ato_id):
            numero = str(linha["numero"] or "").strip()
            if not numero or numero in ja_mostrados:
                continue
            # O código TJ mora na referência: "{tabela}:{ato_id}:{codigo}:{i}".
            partes = str(linha["referencia"] or "").split(":")
            rotulo = partes[2] if len(partes) >= 3 else "selo"
            marca = NSELO.marca_do_selo(numero)
            extras.append({
                "rotulo": rotulo, "numero": numero,
                "texto": str(linha["texto"] or "").strip(),
                "qr_texto": marca["qr_texto"]})
        return extras

    def _destino_apos_selar_rtdpj(ato_id: int, registro_id: int):
        """Para onde ir depois de lavrar: a etiqueta do título, se saiu selo.

        «gerar também uma etiqueta para colar no título original, que será
        devolvido, dizendo que foi averbado/registrado» — pedido do oficial
        em 11/09/2026. `rcpj_rtd_etiqueta` já é essa etiqueta (90×40mm, com
        livro/folha/número/selo, pensada desde 03/09 para colar «no título de
        papel»); o que faltava era ninguém precisar lembrar de ir buscá-la.
        Sem selo (aparelho caiu, sem item a cobrar), não há o que declarar
        na etiqueta — volta para a ficha, como sempre.
        """
        with db.connect() as con:
            tem_selo = banco(con).um(
                "SELECT 1 AS tem FROM rg_atos WHERE id=%s AND COALESCE(selo,'')<>''",
                (int(ato_id),))
        if tem_selo:
            # 307, e não 302: a etiqueta é POST (M8, LX11), e o 307 leva o
            # mesmo POST — com o token — até ela.
            return redirect(url_for("rcpj_rtd_etiqueta", ato_id=int(ato_id)), code=307)
        return redirect(url_for("rcpj_rtd_registro", registro_id=registro_id))

    def _selar_o_ato(tabela: str, ato_id: int, tipo: str, atribuicao: str,
                     ja_dito: str, especie=None,
                     folha_escolhida: str | None = None,
                     reselagem: int = 0,
                     busca: str | None = None) -> str:
        # `busca` (15/10/2026) e o item de busca escolhido na tela da
        # certidao: vira MAIS UM selo, pelo mesmo caminho da segunda via.
        # HOTFIX-2026-10-09-05: `reselagem` > 0 so vem de «Selar novamente»
        # (selo anterior CANCELADO): muda o SID com o sufixo `:R<n>`.
        """Pede o selo ao aparelho DEPOIS de o ato existir. FALA COM A REDE.

        «O selo deve ser emitido quando praticado o ato. Igual o E-Ofício» —
        decisão do oficial em 27/08/2026.

        UM SELO PARA CADA ITEM DA TABELA DE EMOLUMENTOS — decisão dele no mesmo
        dia: *"todos os selos são automáticos, escolhendo pelo item da tabela de
        emolumentos"*. É o que o E-Ofício fazia, e é o que amarra o selo ao que
        foi **cobrado**, e não à média do que a casa costuma cobrar.

        O ITEM DA LEI VALE QUANDO NÃO HÁ ESCOLHA. O registro de nascimento e o
        de óbito são **isentos** por lei, e o item deles (`14.a`, `14.c`) não é
        escolha de ninguém: quando nada foi marcado, é ele que sela. Nos demais
        atos, sem item marcado não sai selo — e a tela diz por quê.

        FORA DA TRANSAÇÃO DO ATO, e é por isso que esta função é chamada depois
        do `with db.transaction()`: a chamada ao aparelho tem prazo de vinte
        segundos, e segurar o `BEGIN IMMEDIATE` da casa por vinte segundos poria
        todo outro balcão no `busy_timeout`.

        SE O ESCREVENTE JÁ DIGITOU UM SELO, não se pede outro. Dois selos para
        o mesmo ato é o dinheiro da serventia saindo duas vezes.

        A FOLHA DE SEGURANÇA É UMA SÓ, mesmo com dois selos. Ela é o papel em
        que a certidão é impressa — e o oficial já disse: *"atos como averbação
        e certidão, vai dois selos na certidão, não há problema nisso"*. Dois
        selos, um papel.

        A FOLHA PODE SER ESCOLHIDA NA CERTIDÃO — pedido do oficial em
        08/09/2026. Se `folha_escolhida` vier preenchida, ela é usada no lugar
        de `PP.proxima_folha` (validada: tem de estar EM BRANCO no estoque);
        sem ela, o comportamento é o de sempre. Ver o módulo `papel_seguranca`.
        """
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return SR.recado_pendente_selo()
        if ja_dito:
            return ja_dito

        # RCPJ / RTD — mesmo padrão do civil, envelope e caminho próprios.
        if tabela == "rg_atos":
            return _selar_o_rtdpj(tabela, ato_id, tipo, atribuicao,
                                 serie=especie)

        # O ASSENTO DE CASAMENTO NAO COMPRA SELO — decisão do oficial em
        # 28/08/2026: *«o selo é emitido uma vez apenas; ele é reaproveitado
        # apenas no assento, mas já foi emitido na habilitação»*. E a tabela
        # concorda: o item `14.1.1` cobre «habilitação **e registro**» — um
        # item, um selo.
        #
        # O NÚMERO CHEGA AQUI PELO OUTRO LADO: ao amarrar o assento à
        # habilitação, `habilitacao.espelhar_o_selo_no_assento` copia o selo
        # dela para cá. Comprar um aqui gastaria o dinheiro do casal duas vezes.
        if (tabela == "rc_atos"
                and str(tipo or "").strip().upper() == "REGISTRO"
                and str(especie or "").strip().upper() in (
                    "CASAMENTO", "CASAMENTO_RELIGIOSO")
                and not _habilitacao_de_fora(ato_id)):
            return (" O casamento não compra selo: o selo é o da habilitação, "
                    "que já foi emitido. Ele é anotado aqui ao amarrar este "
                    "assento à habilitação, em Registro Civil → Habilitações.")

        # O REGISTRO DO EDITAL DE UMA HABILITAÇÃO DESTA CASA NÃO COMPRA SELO —
        # LD01, 21/10/2026, pela mesma razão do casamento: o selo é o da
        # habilitação (item 14.1.1), cujo envelope leva o livro, a folha e o
        # termo deste registro, e `habilitacao.espelhar_o_selo_no_livro_d` o
        # anota aqui quando sai. O proclama recebido de outra serventia não
        # tem habilitação daqui, e continua comprando o seu (14.1.2).
        if (tabela == "rc_atos"
                and str(tipo or "").strip().upper() == "REGISTRO"
                and str(especie or "").strip().upper() == "PROCLAMAS"
                and _habilitacao_do_livro_d(ato_id)):
            # É «sem selo» de propósito, e não «selado»: o registro continua
            # pendente até a habilitação ser selada, e a tela tem de dizê-lo.
            return AS.recado_de_falta(
                " O registro do edital não compra selo — continua SEM SELO: "
                "o selo é o da habilitação (item 14.1.1), que leva este "
                "livro, folha e termo, e é anotado aqui quando a habilitação "
                "é selada, em Registro Civil → Habilitações.")

        # 1a CERTIDAO DO NASCIMENTO/OBITO/NATIMORTO — 09/09/2026:
        # gratuita, usa o selo do REGISTRO (REGNAS...), nao compra CERTID.
        if tabela == "rc_certidoes":
            with db.connect() as _con_pc:
                _cert = banco(_con_pc).um(
                    "SELECT assento_id, COALESCE(selo,'') selo FROM rc_certidoes WHERE id=%s",
                    (int(ato_id),))
                if _cert:
                    _aid = int(_cert["assento_id"])
                    _esp = str(especie or "").strip().upper() or _especie_do_assento(_aid)
                    if RCE.eh_primeira_certidao_do_registro(
                            _con_pc, _aid, certidao_id=int(ato_id), especie=_esp):
                        _selo = RCE.espelhar_selo_do_registro_na_certidao(
                            _con_pc, int(ato_id), _aid)
                        _con_pc.commit()
                        if _selo:
                            return (
                                f" 1ª certidão gratuita: usa o selo do registro "
                                f"{_selo} (sem CERTID / segunda-via)."
                            )
                        return (
                            " A 1ª certidão é gratuita e deveria usar o selo do "
                            "registro, mas o REGISTRO ainda não tem selo. "
                            "Sele o registro primeiro; não compre CERTID."
                        )


        do_civil = tabela in ("rc_atos", "rc_certidoes")
        # A FOLHA SE GASTA QUANDO O ENVELOPE A LEVA, e não em todo ato do
        # civil — correção de 28/08/2026, achada medindo o contrato: `papelMoeda`
        # está em **19 dos 100** caminhos do civil.
        #
        # Antes, uma averbação à margem reservava e dava baixa numa folha que
        # ninguém imprimia; e com o estoque vazio ela era lavrada SEM SELO,
        # dizendo que faltava folha para um ato que não usa nenhuma. Estoque
        # acabado passava a travar o selo de metade do Registro Civil.
        precisa_folha = do_civil and AS.gasta_folha_de_seguranca(
            AS.caminho_do_ato(tabela, tipo, especie=especie))
        folha_escolhida = str(folha_escolhida or "").strip() or None
        with db.connect() as con:
            # Averbação RCPN (oficial 15/09/2026): só 14.4.1; se houver 14.12
            # no protocolo, UM selo com quantidade=N (não CERTID/BURCXX/RETIFI,
            # não ARQUIV×N). Sem UI de escolha de selos.
            eh_averbacao_rcpn = (
                tabela == "rc_atos"
                and str(tipo or "").strip().upper() == "AVERBACAO")
            if eh_averbacao_rcpn:
                itens_qtd = AS.itens_selo_averbacao_rcpn(
                    _itens_para_selar(con))
                itens = [c for c, _q in itens_qtd]
                _qtd_por_codigo = {c: q for c, q in itens_qtd}
            else:
                # Demais atos do civil: um selo por unidade, como sempre.
                itens = _itens_para_selar_expandido(con)
                _qtd_por_codigo = {}
            folha = None
            folha_invalida = None
            if precisa_folha:
                if folha_escolhida:
                    linha_folha = PP.ler(con, folha_escolhida)
                    if linha_folha and linha_folha["situacao"] == "EM BRANCO":
                        folha = linha_folha["codigo"]
                    elif linha_folha:
                        folha_invalida = (
                            f"a folha {folha_escolhida} já está "
                            f"{linha_folha['situacao'].lower()}")
                    else:
                        folha_invalida = (
                            f"a folha {folha_escolhida} não está no estoque")
                else:
                    # Pedido do oficial (09/09/2026): no nascimento (e demais
                    # registros que gastam folha) a folha DEVE ser pedida na
                    # tela. Escolher sozinho pegava a menor em branco, e nao
                    # a que estava na gaveta — o mesmo defeito da certidao
                    # antes de 08/09. Sem escolha explicita, nao sela.
                    folha = None
                    folha_invalida = (
                        "escolha a folha de seguranca na tela de conferencia "
                        "(nao se escolhe sozinha)")
        if precisa_folha and folha_invalida:
            # A FOLHA E ESTOQUE, E NAO O APARELHO: falta.
            return AS.recado_de_falta(
                f" O ato foi lavrado SEM SELO: {folha_invalida}. "
                f"Escolha outra folha em branco no estoque.")
        if precisa_folha and not folha:
            return AS.recado_de_falta(
                " O ato foi lavrado SEM SELO: não há folha de segurança em "
                "branco no estoque.")
        if not itens:
            if not do_civil:
                return AS.recado_de_falta(
                    " O ato foi lavrado SEM SELO: o selo sai pelos itens "
                    "da tabela de emolumentos, e este ato não tem "
                    "protocolo nem item marcado para cobrança.")
            # O ITEM DA LEI: isento não se marca, e sela do mesmo jeito.
            itens = [None]

        # A BUSCA É SELO PRÓPRIO, PELO CAMINHO DA SEGUNDA VIA — pedido do
        # oficial, 15/10/2026, na forma do precedente mais novo do E-Ofício
        # (protocolo 2026.07.276, 30/07/2026): `14.5.1` e `14.6.6` em dois
        # pedidos pelo mesmo caminho, com o mesmo livro, folha e termo e a
        # MESMA folha de segurança. Vai depois da certidão, como lá foi.
        #
        # **SE O PROTOCOLO JÁ TRAZ A BUSCA, VALE A DO PROTOCOLO** — é o «pelo
        # protocolo» do pedido —, e não se vende outra por cima. E a certidão
        # eletrônica (`14.5.7`) já traz a busca no preço.
        if (busca and BU.vira_selo(busca)
                and tabela == "rc_certidoes"
                and not BU.busca_entre(itens)
                and not BU.ja_inclui_busca(itens)):
            itens = list(itens) + [busca]

        saiu, faltou = [], []
        recusou_o_aparelho = False      # ver o Protesto, acima
        try:
            _grat_cod, _grat_mot, selo_isento = _gratuidade_do_form()
        except AS.AtoError as erro:
            # GRATUIDADE SEM MOTIVO ESCRITO: falta o que a tela pergunta.
            return AS.recado_de_falta(
                f" O ato foi lavrado SEM SELO: {erro}")
        motivo_selo = _grat_mot
        # **ÍNDICE POR OCORRÊNCIA** — achado do oficial em 11/09/2026, sobre
        # selo com valor "totalmente errado ao orçamento": com
        # `quantidade > 1` o mesmo `codigo_tj` se repete em `itens`, e uma
        # referência igual faria o aparelho devolver o MESMO selo para as
        # unidades repetidas em vez de vender uma para cada.
        ocorrencias: dict[str, int] = {}
        for codigo_tj in itens:
            if codigo_tj:
                ocorrencias[codigo_tj] = ocorrencias.get(codigo_tj, 0) + 1
                indice = ocorrencias[codigo_tj]
            try:
                q_item = int(_qtd_por_codigo.get(codigo_tj, 1) or 1)
                envelope = _envelope_do_civil(tabela, ato_id, tipo, especie,
                                              folha, codigo_tj,
                                              _habilitacao_de_fora(ato_id),
                                              isento=selo_isento,
                                              motivo_isencao=motivo_selo,
                                              quantidade=q_item)
            except (AS.AtoError, sqlite3.Error) as erro:
                faltou.append(str(erro))
                continue
            r = AS.selar_o_ato_lavrado(
                db, Path(app.config["DATA_DIR"]), tabela=tabela, ato_id=ato_id,
                tipo=tipo, atribuicao=atribuicao, agora=agora(),
                cns=sv().get("ri_cns"), usuario=usuario_nome(), especie=especie,
                dados=envelope,
                # CADA ITEM COM A SUA REFERÊNCIA: é dela que sai o SID, e é o
                # SID que faz o aparelho devolver o selo que já existe em vez
                # de vender outro. Uma referência só para dois itens traria o
                # MESMO selo duas vezes.
                referencia=((f"{tabela}:{int(ato_id)}:{codigo_tj}:{indice}"
                             if codigo_tj else f"{tabela}:{int(ato_id)}")
                            + (f":R{int(reselagem)}" if reselagem else "")))
            recusou_o_aparelho = recusou_o_aparelho or not r["selado"]
            (saiu if r["selado"] else faltou).append(
                r["numero"] if r["selado"] else r["motivo"])

        if not saiu:
            marcar = (AS.recado_de_recusa if recusou_o_aparelho
                      else AS.recado_de_falta)
            return marcar(
                f" O ato foi lavrado SEM SELO: {faltou[0] if faltou else ''}")

        recado = f" {len(saiu)} selo(s): {', '.join(saiu)}."
        if folha:
            # A FOLHA SAIU DA GAVETA AGORA, e não antes: o selo existe. Uma
            # folha só, ainda que os selos sejam dois.
            try:
                with db.transaction() as con:
                    PP.usar(con, folha, tabela=tabela, ato_id=ato_id,
                            selo=saiu[0], agora=agora(), usuario=usuario_nome())
                recado += f" Na folha de segurança {folha}."
            except PP.PapelError as erro:
                recado += f" A folha {folha} não deu baixa: {erro}"
        if faltou:
            recado += f" ({len(faltou)} item(ns) sem selo: {faltou[0]})"
        return recado

    def _pessoas_do_formulario(especie: str) -> list[dict]:
        """As pessoas digitadas, no papel que a espécie manda. Só LÊ o pedido.

        O PAPEL SAI DA ESPÉCIE, E NÃO DO FORMULÁRIO. É a mesma regra da série:
        deixar o balcão escolher o papel é deixar gravar um NUBENTE num assento
        de óbito. A tela mostra os campos com o nome certo, e aqui eles são
        amarrados ao papel que cabe.

        O BLOCO DE UMA PESSOA SÓ SERVE OS DOIS CASOS — o registrado e o
        falecido —, porque os campos são exatamente os mesmos. Duas cópias do
        mesmo bloco divergiriam no primeiro conserto.

        NADA DIGITADO, NADA GRAVADO: quem não perguntar ao declarante não
        inventa linha de pessoa. Ela aparece no que falta para o IBGE, que é
        onde ela tem de aparecer.
        """
        papeis = RC.PAPEIS_DA_ESPECIE.get(
            str(especie or "").strip().upper(), ())
        if not papeis:
            return []
        saida = []
        # A SEGUNDA TESTEMUNHA (LD01) é outra gaveta do mesmo papel:
        # `prefixos_do_papel` dá as gavetas de cada papel, na ordem. No
        # NASCIMENTO ela é papel próprio, TESTEMUNHA2 (o registro tardio).
        gavetas = [(papel, prefixo) for papel in papeis
                   for prefixo in RC.prefixos_do_papel(papel, especie)]
        for papel, prefixo in gavetas:
            campos = {c: _campo(f"{prefixo}_{c}")
                      for c in RC.CAMPOS_DA_PESSOA}
            # «não tem — ignorado»: declaração, não branco. Sem isto o POST
            # iria vazio e a lavratura recusaria o que a lei exige.
            if _campo(f"nao_tem_{prefixo}") and not campos.get("nome"):
                campos["nome"] = "IGNORADO"
            # TESTEMUNHA_FANTASMA_20261009: o <select> do tipo de documento
            # (_pessoa_do_assento.html) nao tem opcao vazia - o navegador manda
            # «CPF» em TODA gaveta, preenchida ou nao. Contar esse campo como
            # digitado criava uma TESTEMUNHA so com documento_tipo=CPF, e
            # `RC.registrar_pessoa` punha nela o nome do registrado (assentos
            # 8371 e 8373, 09/10/2026).
            if not any(v for c, v in campos.items()
                       if c not in ("documento_tipo",)):
                continue
            # A IDADE NA OCASIÃO DO FATO SE CALCULA — relato #37, item 5.
            #
            #   E **só quando o balcão não a informou**: se o declarante disse
            #   29 e a conta dá 30, quem assina o termo é o oficial, e a
            #   divergência é assunto dele. Sobrescrever seria a máquina
            #   corrigindo o declarante dentro de um papel assinado.
            #
            #   Onde falta uma das duas datas, `idade_na_data` devolve None e
            #   o campo continua como veio — que é o comportamento de antes.
            if not campos.get("idade_no_fato"):
                anos = RC.idade_na_data(campos.get("data_nascimento"),
                                        _campo("data_fato"))
                if anos is not None:
                    campos["idade_no_fato"] = str(anos)
            saida.append({"papel": papel,
                          **{c: v for c, v in campos.items() if v}})
        return saida

    def _devedores_do_formulario() -> list[dict]:
        """Os devedores digitados, no vocabulário do contrato da CRA.

        O ENDEREÇO SÓ ENTRA SE FOR ESCRITO, e isso é de propósito: `protesto_
        cra.conferir_titulo` recusa devedor sem endereço com a frase certa —
        "sem ele não há como intimar, e o protesto sai por edital". Mandar um
        endereço vazio de brinde faria a conferência passar e o defeito
        aparecer só na hora da intimação.
        """
        def em(lista: list[str], i: int) -> str:
            return (lista[i] or "").strip() if i < len(lista) else ""

        nomes = request.form.getlist("devedor_nome")
        tipos = request.form.getlist("devedor_documento_tipo")
        numeros = request.form.getlist("devedor_documento")
        enderecos = request.form.getlist("devedor_endereco")
        bairros = request.form.getlist("devedor_bairro")
        ceps = request.form.getlist("devedor_cep")
        cidades = request.form.getlist("devedor_cidade")
        ufs = request.form.getlist("devedor_uf")

        saida = []
        for i, nome in enumerate(nomes):
            if not (nome or "").strip():
                continue
            endereco = {"endereco": em(enderecos, i), "bairro": em(bairros, i),
                        "cep": em(ceps, i), "cidade": em(cidades, i),
                        "uf": em(ufs, i)}
            devedor: dict = {"nome": nome.strip(),
                             "enderecos": [endereco] if any(endereco.values()) else []}
            tipo = em(tipos, i).upper()
            devedor["CNPJ" if tipo == "CNPJ" else "CPF"] = em(numeros, i)
            saida.append(devedor)
        return saida

    def _para_cobrar(con, tabela: str, tipo: str) -> dict:
        """O que a macro `quadro()` precisa para oferecer a cobrança. Só LÊ.

        As telas de abrir registro novo também cobram: o ato de REGISTRO nasce
        junto com o registro, e é selável e cobrável como qualquer outro. Ato
        lavrado e não cobrado é receita que some sem ninguém ver.
        """
        return {"receita": _receitas_de(con, tabela, (tipo,)).get(tipo),
                "caixa": _caixa_aberto(con),
                "protocolos": _protocolos_abertos(con)}

    def _listar(chave: str):
        """A lista de um painel: filtra, conta e pagina. So LE."""
        painel = PAINEIS[chave]
        termo = (request.args.get("q") or "").strip()
        situacao = (request.args.get("situacao") or "").strip()
        pagina = _inteiro(request.args.get("pagina"), maximo=PAGINA_MAIS_ALTA)

        # O FILTRO FIXO VALE TAMBEM PARA A CONTAGEM POR SITUACAO, e por isso
        # ele e montado a parte. Contar o RCPJ e o RTD juntos embaixo de uma
        # lista que mostra so um dos dois seria a tela dizendo um numero que
        # nao e o dela.
        fixo, params_fixos = [], []
        atribuicoes = painel.get("atribuicoes") or {}
        atribuicao = (request.args.get("atribuicao") or "").strip()
        if atribuicao in atribuicoes:
            fixo.append("atribuicao = %s")
            params_fixos.append(int(atribuicao))
            painel = {**painel, "titulo": atribuicoes[atribuicao]}

        onde, params = list(fixo), list(params_fixos)
        if termo:
            campos = [f"{c}::text ILIKE %s" for c in painel["busca"]]
            params += [f"%{termo}%"] * len(painel["busca"])
            junta = painel.get("busca_junta")
            if junta:
                sql, quantos = junta
                campos.append(sql)
                params += [f"%{termo}%"] * quantos
            onde.append("(" + " OR ".join(campos) + ")")
        if situacao in painel["situacoes"]:
            onde.append("situacao = %s")
            params.append(situacao)
        filtro = (" WHERE " + " AND ".join(onde)) if onde else ""
        extra = painel.get("select_extra")
        colunas = f"*, {extra}" if extra else "*"

        with db.connect() as con:
            bd = banco(con)
            total = int(bd.valor(
                f"SELECT COUNT(*) n FROM {painel['tabela']}{filtro}",
                params))
            linhas = bd.ler(
                f"SELECT {colunas} FROM {painel['tabela']}{filtro} "
                f"ORDER BY {painel['ordem']} LIMIT %s OFFSET %s",
                (*params, POR_PAGINA, (pagina - 1) * POR_PAGINA))
            recorte = (" WHERE " + " AND ".join(fixo)) if fixo else ""
            por_situacao = [
                {**r, "n": int(r["n"])} for r in bd.ler(
                    f"SELECT situacao, COUNT(*) n FROM {painel['tabela']}{recorte} "
                    f"GROUP BY situacao ORDER BY n DESC, situacao", params_fixos)]
        return {
            "chave": chave, "painel": painel, "linhas": linhas,
            "total": total, "pagina": pagina,
            "paginas": max(1, -(-total // POR_PAGINA)),
            "termo": termo, "situacao": situacao, "atribuicao": atribuicao,
            "por_situacao": por_situacao,
        }

    # ------------------------------------------------------------ Protesto

    # AS PEÇAS DO PROTESTO NÃO SÃO JINJA (LF06E): são `{claro}` do
    # `str.format`, e o conferidor geral aprovaria `{claro_inventado}` — que só
    # estouraria na hora do papel, com o cliente no balcão. A régua é a de
    # quem preenche (`protesto_pecas.conferir`). Fica aqui, no começo do
    # Protesto, e não junto dos termos do civil: é do Protesto.
    import protesto_pecas as _PECAS
    app.extensions.setdefault("conferidores_de_modelo", {})
    for _ch in _PECAS.chaves_conferidas():
        app.extensions["conferidores_de_modelo"][_ch] = (
            lambda corpo, _c=_ch: _PECAS.conferir(_c, corpo))

    @app.route("/protesto/titulos")
    @login_required
    def protesto_titulos_legacy():
        """Bookmark antigo — a lista mora em `/protesto`, não neste caminho."""
        return redirect(url_for("protesto_titulos"))

    @app.route("/protesto")
    @login_required
    def protesto_titulos():
        """Os títulos do Protesto, abrindo nos PENDENTES. Só LÊ.

        Pedido do oficial em 14/10/2026, o primeiro dia do protesto no
        sistema: «não consigo ver, filtrar e ordenar os títulos realmente
        pendentes». A lista genérica (`_listar`) mostrava os 1.374 títulos em
        `id DESC`, com os 28 que ainda pedem alguma coisa afogados entre os
        que já acabaram. Quem separa, filtra, ordena e diz o próximo passo é
        `protesto_lista`; a rota só liga os fios.

        O FILTRO VOLTA COM QUEM VOLTA. Sem nada no endereço — a volta da
        ficha, o redirecionamento depois de lançar um ato —, reabre o último
        filtro desta pessoa, guardado na sessão (cookie, e não banco: GET não
        abre transação de escrita). «Limpar» manda `vista=pendentes`, e por
        isso nunca cai nesta volta.
        """
        args = request.args
        lembrado = False
        if not any(k in args for k in (*PLISTA.CAMPOS_DO_FILTRO, "pagina")):
            guardado = session.get("protesto_lista_filtro")
            if isinstance(guardado, dict) and guardado:
                args, lembrado = guardado, True
        filtro = PLISTA.ler_filtro(args)
        pagina = _inteiro(args.get("pagina"), maximo=PAGINA_MAIS_ALTA)
        with db.connect() as con:
            r = PLISTA.listar(con, filtro, hoje=hoje(), pagina=pagina)
            apresentantes = PLISTA.apresentantes(con)
        session["protesto_lista_filtro"] = PLISTA.params(
            filtro, pagina=r["pagina"] if r["pagina"] > 1 else None)
        contagem_vistas = r.pop("vistas")
        return render_template(
            "protesto_titulos.html", filtro=filtro, lembrado=lembrado,
            apresentantes=apresentantes, vistas=PLISTA.VISTAS,
            contagem_vistas=contagem_vistas,
            ordens=PLISTA.ORDENS, filtro_sustado=PLISTA.FILTRO_SUSTADO,
            params=PLISTA.params, ordenar_por=PLISTA.ordenar_por, **r)

    @app.route("/protesto/novo", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_titulo_novo():
        """Cadastra pelo balcão o título que não veio pela CRA. ESCREVE.

        93% DOS TÍTULOS ENTRAM PELO ARQUIVO — 1.268 pela CRA e 91 pelo
        CENPROT, contra 7 digitados em seis anos. Esta tela é para esses
        sete: o particular que traz a nota promissória no guichê, e não o
        lote diário do banco.

        O TÍTULO NASCE `RECEBIDO`, E NÃO APONTADO. `cadastrar_titulo` não
        lavra ato nenhum — o apontamento é ato à parte, com lugar no Livro
        de Apontamento, número de ordem, selo e custas próprios, e lança-se
        na ficha como todos os outros. Juntar os dois numa tela só faria o
        balcão apontar sem querer, e apontamento não se desfaz.

        QUEM RECUSA É O CONTRATO DA CRA, e não esta rota:
        `protesto_cra.conferir_titulo` cobra espécie, número, datas, valor,
        saldo, praça e ao menos um devedor com documento e endereço. Repetir
        essa lista aqui daria duas versões dela.
        """
        def tela(**extra):
            return render_template(
                "atrib_protesto_novo.html",
                especies=PT.especies_para_escolher(),
                tipos_protesto=CRA.TIPOS_DE_PROTESTO,
                motivos=CRA.MOTIVOS_DE_PROTESTO,
                endossos=CRA.TIPOS_DE_ENDOSSO,
                moedas=CRA.TIPOS_DE_MOEDA, ufs=CRA.UFS,
                cidade_da_casa=(sv().get("ri_cidade") or "").upper(),
                uf_da_casa=(sv().get("ri_uf") or "").upper(),
                form=request.form, **extra)

        if request.method != "POST":
            return tela()

        dados = {
            "especie": _campo("especie"),
            "numero_titulo": _campo("numero_titulo"),
            "nosso_numero": _campo("nosso_numero") or None,
            "data_emissao": _campo("data_emissao"),
            "data_vencimento": _campo("data_vencimento"),
            # O SALDO NÃO SE DEDUZ DO VALOR. Medido nos 102 títulos que não
            # vieram da CRA: em 31 deles o saldo é diferente do valor de
            # face, porque traz juros e encargos. Preencher sozinho poria o
            # protesto no valor errado, e o valor do protesto é o que a
            # certidão diz e o que o devedor paga.
            "valor": _campo("valor"),
            "saldo": _campo("saldo"),
            "praca_protesto": _campo("praca_protesto"),
            "tipo_protesto": _campo("tipo_protesto") or None,
            "motivo_protesto": _campo("motivo_protesto") or None,
            "tipo_endosso": _campo("tipo_endosso") or None,
            "tipo_moeda": _campo("tipo_moeda") or "1",
            "aceite": _campo("aceite") or None,
            # O APRESENTANTE (LD04, 21/10/2026) — quem traz o título ao
            # balcão: o próprio credor, ou quem o representa. Lei 9.492/1997,
            # art. 22, II, e CN-MA arts. 884, I, 914, III, e 920: ele vai ao
            # aviso, ao registro e ao instrumento. Esta tela não o pedia, e o
            # aviso saía «Apresentante: não informado». Na CRA ele vem no
            # cabeçalho da remessa.
            #
            # O CPF/CNPJ E O ENDEREÇO DELE (LD08, 21/10/2026) — CN-MA art.
            # 884, I: o apresentante os informa «no requerimento a protesto».
            # O aviso leva o documento (art. 923), e o registro e o
            # instrumento, o endereço (Lei 9.492, art. 22, II). Na CRA eles
            # vêm do cadastro dos apresentantes, pelo código
            # (`protesto.apresentante_do_titulo`).
            "apresentante_nome": _campo("apresentante_nome") or None,
            "apresentante_documento": _campo("apresentante_documento") or None,
            "apresentante_endereco": _campo("apresentante_endereco") or None,
            "cedente": {
                "nome": _campo("cedente_nome") or None,
                "documento": _campo("cedente_documento") or None,
                "endereco": _campo("cedente_endereco") or None,
                "cep": _campo("cedente_cep") or None,
                "cidade": _campo("cedente_cidade") or None,
                "uf": _campo("cedente_uf") or None,
            },
            "devedores": _devedores_do_formulario(),
        }
        try:
            with db.transaction() as con:
                titulo_id = PT.cadastrar_titulo(
                    con, dados, origem="MANUAL", agora=agora(),
                    usuario=usuario_nome())
        except PT.ProtestoError as erro:
            flash(str(erro), "danger")
            return tela()
        # `audit` abre transação própria: FORA do `with`, como no resto da casa.
        audit("PROTESTO_TITULO_NOVO", "pt_titulos", titulo_id,
              {"numero_titulo": dados["numero_titulo"],
               "especie": dados["especie"], "origem": "MANUAL"})
        flash(f"Título {dados['numero_titulo']} cadastrado. Ele está "
              f"RECEBIDO: o apontamento é o próximo ato, e sai aqui embaixo.",
              "success")
        return redirect(url_for("protesto_titulo", titulo_id=titulo_id))

    # -------------------------------------------- a certidão de protesto

    @app.route("/protesto/certidoes")
    @login_required
    def protesto_certidoes():
        """Buscar quem tem protesto, e emitir a certidão. Só LÊ.

        É O QUE O BALCÃO MAIS PEDE. A busca é por nome ou por CPF/CNPJ — e por
        muito tempo não teve resposta, porque a carga do acervo trazia os 1.366
        títulos e nenhum devedor.

        O GET NÃO EMITE NADA. Ele mostra o que a busca achou e qual certidão
        cabe; emitir é o POST, com selo e cobrança. Buscar e emitir na mesma
        ação faria sair certidão de quem só quis conferir.
        """
        nome = (request.args.get("nome") or "").strip()
        documento = (request.args.get("documento") or "").strip()
        # o período vai gravado na certidão (`periodo_anos`, `integer`): LD13
        anos = _inteiro(request.args.get("anos"), PCE.PERIODO_PADRAO_ANOS,
                        maximo=MAIOR_INTEGER)
        desde = PCE.data_limite(hoje(), anos)

        achados, cabivel, erro = [], None, None
        do_protocolo: list[dict] = []
        if nome or documento:
            try:
                with db.connect() as con:
                    achados = PCE.buscar(
                        con, nome=nome, documento=documento, desde=desde,
                        autorizacao=request.args.get("autorizacao") or None)
                    # O LIVRO DE PROTOCOLO QUE A AUTORIZAÇÃO TRAZ (LD12) — a
                    # mesma conta da emissão, para o aviso de quem entrou só
                    # pelo nome valer também para o apontamento, que esta
                    # tela não lista.
                    do_protocolo = PCE.protocolo_a_certificar(
                        con, nome=nome, documento=documento, desde=desde,
                        achados=achados,
                        autorizacao=request.args.get("autorizacao") or None)
                cabivel = PCE.tipo_para(achados)
            except PCE.CertidaoError as e:
                erro = str(e)
        # QUEM ENTROU SÓ PELO NOME (LD12): o devedor gravado sem CPF/CNPJ. A
        # tela avisa antes de emitir; o teor da certidão não muda.
        so_pelo_nome = PCE.titulos_so_pelo_nome(achados, do_protocolo)

        with db.connect() as con:
            emitidas = [dict(r) for r in PCE.listar(
                con, termo=(request.args.get("q") or ""), limite=60)]
            contexto = _para_cobrar(con, "pt_certidoes",
                                    cabivel or "NEGATIVA")
            # AS ORDENS SEM A MARCA DO CNN art. 263-K (LH13): lançadas antes
            # de 21/10/2026, o protesto delas fica fora da certidão até alguém
            # dizer se a decisão é provisória. A tela avisa antes de emitir.
            sem_marca = PT.ordens_sem_marca(con)
        if erro:
            flash(erro, "danger")
        return render_template(
            "protesto_certidoes.html", nome=nome, documento=documento,
            anos=anos, desde=desde, achados=achados, cabivel=cabivel,
            buscou=bool(nome or documento), emitidas=emitidas,
            aviso_pelo_nome=(PCE.aviso_so_pelo_nome(so_pelo_nome)
                             if so_pelo_nome else ""),
            protocolo_pelo_nome=[l for l in do_protocolo
                                 if l.get("so_pelo_nome")],
            tipos=PCE.TIPOS, q=(request.args.get("q") or ""),
            autorizacoes=PCE.AUTORIZACOES,
            autorizacao=(request.args.get("autorizacao") or ""),
            autorizacao_ref=(request.args.get("autorizacao_ref") or ""),
            ordens_sem_marca=sem_marca, **contexto)

    @app.route("/protesto/certidoes/emitir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_certidao_emitir():
        """Emite a certidão, com número do exercício e teor congelado. ESCREVE.

        A BUSCA ROLA DE NOVO AQUI DENTRO, e não se confia no que veio da tela:
        entre o GET e o POST alguém pode ter lavrado protesto, e certidão
        negativa emitida sobre busca velha é a certidão que faz o banco
        emprestar para quem não devia. Quem recusa é o domínio.
        """
        nome = _campo("nome")
        documento = _campo("documento")
        anos = _inteiro(_campo("anos"), PCE.PERIODO_PADRAO_ANOS,
                        maximo=MAIOR_INTEGER)
        desde = PCE.data_limite(hoje(), anos)
        # A BUSCA — pedido do oficial, 15/10/2026. A faixa vem do PERÍODO
        # pesquisado (cinco anos dão 17.6.2), e a escolha se confere antes de
        # numerar a certidão.
        try:
            busca = _busca_do_form("PROTESTO")
        except BU.BuscaError as _erro_busca:
            flash(str(_erro_busca), "danger")
            return redirect(url_for("protesto_certidoes", nome=nome,
                                    documento=documento, anos=anos))
        try:
            with db.transaction() as con:
                achados = PCE.buscar(con, nome=nome, documento=documento,
                                     desde=desde,
                                     autorizacao=_campo("autorizacao") or None)
                r = PCE.emitir(
                    con, nome=nome, documento=documento or None,
                    achados=achados, hoje=hoje(), agora=agora(),
                    tipo=_campo("tipo") or None, periodo_anos=anos,
                    desde=desde, requerente=_campo("requerente") or None,
                    finalidade=_campo("finalidade") or None,
                    usuario=usuario_nome(),
                    autorizacao=_campo("autorizacao") or None,
                    autorizacao_ref=_campo("autorizacao_ref") or None)
                selo_a_mao = _selar_se_pedido(con, "pt_certidoes",
                                              r["certidao_id"], "PROTESTO")
                aviso = selo_a_mao
                aviso += _cobrar_se_pedido(con, "pt_certidoes",
                                           r["certidao_id"], r["tipo"],
                                           busca=busca)
        except (PCE.CertidaoError, AS.AtoError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_certidoes", nome=nome,
                                    documento=documento, anos=anos))
        # O SELO SAI AGORA — um para cada item cobrado, como no ato.
        recado_do_selo = ""
        if not selo_a_mao:
            # O TIPO E O DA CERTIDAO — negativa, positiva, de cancelamento —,
            # e nao a palavra «CERTIDAO»: e por ele que sai o caminho do selo.
            recado_do_selo = _selar_o_protesto("pt_certidoes",
                                               r["certidao_id"], r["tipo"])
            aviso += recado_do_selo
        # **QUEM DECIDE LE O RECADO DO SELO**, e nao a soma dos avisos: a
        # marca da especie nao sobrevive a concatenacao, e nao deveria mesmo.
        motivo_selo = _motivo_da_falha_do_selo(recado_do_selo)
        if motivo_selo:
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE pt_certidoes
                          SET cancelada=1, motivo_cancelamento=%s,
                              cancelada_em=%s, cancelada_por=%s
                        WHERE id=%s""",
                    (f"Selo não emitido: {motivo_selo}", agora(),
                     usuario_nome(), r["certidao_id"]))
                _soltar_itens_da_certidao_cancelada(con, "pt_certidoes",
                                                    r["certidao_id"])
            audit("PROTESTO_CERTIDAO_NAO_EMITIDA_SELO_FALHOU",
                  "pt_certidoes", r["certidao_id"],
                  {"numero": r["numero"], "ano": r["ano"],
                   "tipo": r["tipo"], "motivo": motivo_selo})
            flash("Certidão NÃO emitida: o selo não saiu. "
                  f"Motivo: {motivo_selo}. Corrija o problema do "
                  "selo e tente de novo.",
                  "danger")
            return redirect(url_for("protesto_certidoes", nome=nome,
                                    documento=documento, anos=anos))
        # A BUSCA SAI DEPOIS DA CERTIDÃO, e só se a certidão ficou de pé: o
        # selo da busca acompanha o da certidão, como nos 51 do acervo. Com o
        # selo digitado à mão, quem sela a busca também é a mão. Sem escolha
        # na tela ainda vale a busca que veio no protocolo — tirada do laço da
        # certidão em `_selar_o_protesto`, ela sai aqui.
        if not selo_a_mao:
            aviso += _selar_a_busca_da_certidao_do_protesto(
                r["certidao_id"], busca, nome, documento)
        # `audit` abre transação própria: FORA do `with`, como no resto da casa.
        audit("PROTESTO_CERTIDAO", "pt_certidoes", r["certidao_id"],
              {"numero": r["numero"], "ano": r["ano"], "tipo": r["tipo"],
               "achados": r["achados"], "hash": r["hash"],
               **({"busca": busca} if busca else {}),
               # a data do ato que o pedido indicou, e que marca o «.9»
               **({"busca_data_do_ato": _campo("busca_data_do_ato")}
                  if _campo("busca_data_do_ato") else {}),
               # quantos títulos entraram só pelo nome (LD12)
               **({"so_pelo_nome": r["so_pelo_nome"]}
                  if r["so_pelo_nome"] else {})})
        flash(f"Certidão {r['tipo'].lower()} n. {r['numero']}/{r['ano']} "
              f"emitida.{aviso}", "success")
        # O AVISO DE QUEM ENTROU SÓ PELO NOME (LD12) repete o da tela de busca:
        # quem emitiu sem ter buscado antes também precisa vê-lo.
        if r["so_pelo_nome"]:
            flash(PCE.aviso_so_pelo_nome(r["so_pelo_nome"]), "warning")
        return redirect(url_for("protesto_certidao",
                                certidao_id=r["certidao_id"]))

    @app.route("/protesto/certidoes/<int:certidao_id>")
    @login_required
    def protesto_certidao(certidao_id: int):
        """A certidão como saiu — para conferir, imprimir e reimprimir."""
        with db.connect() as con:
            linha = PCE.certidao(con, certidao_id)
            if not linha:
                flash("Certidão não encontrada.", "danger")
                return redirect(url_for("protesto_certidoes"))
            certidao = dict(linha)
        certidao["achados_lista"] = json.loads(certidao["achados_json"] or "[]")
        return render_template("protesto_certidao.html", certidao=certidao,
                               sv=sv(), hoje_extenso=hoje_extenso())

    @app.route("/protesto/certidoes/<int:certidao_id>/odt")
    @login_required
    def protesto_certidao_odt(certidao_id: int):
        """A certidão em .odt, para imprimir e assinar.

        Papel que o cliente leva para casa sai em arquivo, e não em tela — é a
        mesma forma do recibo do caixa e dos termos dos livros, que já rodam
        nesta casa. O rodapé leva o número, a data e o sha256: é por eles que
        se confere depois se a via apresentada é a que saiu daqui.
        """
        import protesto_pecas as PECAS
        with db.connect() as con:
            linha = PCE.certidao(con, certidao_id)
            # A MOLDURA É TEXTO DO OFICIAL (LF06E): título, número, local e
            # data e o rodapé de autenticidade são a peça `PT_MOLDURAS`.
            m = PECAS.rotulos(con, "PT_MOLDURAS")
        if not linha:
            abort(404)
        s = sv()
        cancelada = ('<p align="center"><b>'
                     + m("certidao_cancelada",
                         motivo=linha["motivo_cancelamento"] or "")
                     + "</b></p>" if int(linha["cancelada"] or 0) else "")
        # O CABEÇALHO É O DA CASA — `cabecalho_certidao_completo_odf`, o mesmo
        # das certidões do RI e do RCPJ/RTD/Livro 3 (brasão, República,
        # Comarca, serventia, endereço, telefone, CNPJ, titular, CNS). Até
        # 14/10/2026 esta rota montava um timbre próprio de três linhas.
        # E A DATA É A DA EMISSÃO: a segunda via não muda de dia.
        from datetime import date as _date
        try:
            emitida_extenso = data_por_extenso(
                _date.fromisoformat(str(linha["emitida_em"])[:10]))
        except (TypeError, ValueError):
            emitida_extenso = hoje_extenso()
        html = (f'<p align="center"><b>{m("certidao_titulo", tipo=linha["tipo"])}</b></p>'
                f'<p align="center">'
                f'{m("certidao_numero", numero=linha["numero"], ano=linha["ano"])}</p>'
                f'{cancelada}'
                f'<p></p><p>{linha["teor"]}</p><p></p>'
                f'<p>{m("local_e_data", cidade=s.get("ri_cidade", ""), uf=s.get("ri_uf", ""), data=emitida_extenso)}'
                f'</p><p></p><p></p>'
                f'<p align="center">_________________________________</p>'
                f'<p align="center">{s["serventia_titular"]}</p>'
                f'<p align="center">{s["serventia_titulo"]}</p><p></p>'
                f'<p><font size="8">'
                f'{m("certidao_autenticidade", numero=linha["numero"], ano=linha["ano"], emitida_em=linha["emitida_em"], hash=linha["hash_certidao"])}'
                f'</font></p>')
        # **O CARIMBO DO SELO — 17/09/2026, e ele nao existia aqui.** Esta
        # rota montava o teor e parava; medido no razao, esta casa comprou
        # **57 selos** em `/selo/protesto/certidao`, e nenhum aparecia no
        # papel. Selo comprado que nao sai impresso e o inverso do carimbo
        # sem valores: os dois fazem a certidao afirmar menos do que o selo diz.
        with db.connect() as con:
            etiqueta = AS.etiqueta_do_ato(
                con, "pt_certidoes", certidao_id,
                dict(linha).get("selo") or "")
        frag_do_selo, imagens_do_selo = RODT.carimbo_da_certidao_odf(etiqueta)
        cab_odf, cab_imgs = RODT.cabecalho_certidao_completo_odf(s)
        todas = dict(cab_imgs or {})
        todas.update(imagens_do_selo or {})
        arquivo = gerar_odt(html_para_odf(html) + frag_do_selo,
                            titulo=f"Certidão {linha['numero']}/{linha['ano']}",
                            cabecalho_odf=cab_odf, imagens=todas or None,
                            cabecalho_altura_min="2.0cm",
                            cabecalho_margem_baixo="0.25cm",
                            cabecalho_borda=False)
        audit("PROTESTO_CERTIDAO_ODT", "pt_certidoes", certidao_id,
              {"numero": linha["numero"], "ano": linha["ano"]})
        nome = f"certidao-protesto-{linha['numero']}-{linha['ano']}"
        return IMPW.resposta_do_papel(
            arquivo, nome=nome, get_setting=db.get_setting,
            voltar_para=url_for("protesto_certidao", certidao_id=certidao_id))

    @app.route("/protesto/certidoes/<int:certidao_id>/cancelar",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_certidao_cancelar(certidao_id: int):
        """Cancela a certidão emitida. ESCREVE. O teor fica.

        Certidão errada não se apaga: apagá-la deixaria a via que o cliente
        levou sem par no banco — e é justamente essa via que alguém confere.
        """
        try:
            with db.transaction() as con:
                resultado = PCE.cancelar(
                    con, certidao_id, motivo=_campo("motivo"),
                    agora=agora(), usuario=usuario_nome(),
                    selo_cancelado_tjma=_campo("selo_cancelado_tjma"))
        except PCE.CertidaoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_certidao",
                                    certidao_id=certidao_id))
        audit("PROTESTO_CERTIDAO_CANCELADA", "pt_certidoes", certidao_id,
              {"motivo": _campo("motivo"), "declaracao_selo_tjma": True,
               **resultado})
        folhas = resultado.get("folhas_recuperadas") or []
        recado = (f" Folha(s) {', '.join(folhas)} devolvida(s) ao estoque."
                  if folhas else "")
        flash("Certidão cancelada. O teor fica gravado, como saiu." + recado,
              "success")
        return redirect(url_for("protesto_certidao", certidao_id=certidao_id))

    # ============================================ A CERTIDÃO DAS NOTAS
    #
    # Pedido do oficial, 15/10/2026: «precisa emitir certidão do notas, com
    # selo e etc, inclusive busca quando não disser o ato». MORA AQUI, e não
    # em `notas_web`, porque é aqui que moram as peças das outras certidões —
    # a cobrança pelo protocolo e pelo caixa, a gratuidade, o campo da busca
    # e a regra que cancela a certidão quando o selo não sai. Duas cópias
    # dessas peças divergiriam no primeiro conserto. O domínio é
    # `notas_certidao.py`.

    def _receita_da_certidao_das_notas(con) -> dict:
        """A receita medida de `atos-em-geral`, só com os itens da certidão.

        O caminho é o guarda-chuva do balcão das Notas (712 dos 739 envelopes
        são arquivamento, 13.30): oferecê-lo inteiro na certidão poria o
        arquivamento no alto da lista de cobrança.
        """
        r = AS.receita_de_custas(con, NCE.CAMINHO_DO_SELO)
        return dict(r, itens=[i for i in r.get("itens", [])
                              if str(i.get("codigo_tj") or "").startswith(
                                  "13.12")])

    def _selar_a_certidao_das_notas(certidao_id: int, *, folhas: int,
                                    eletronica: bool, busca: str | None,
                                    parte: dict, isento: bool,
                                    motivo: str | None) -> str:
        """Os selos da certidão das Notas. FALA COM A REDE.

        UM SELO POR ITEM, pelo caminho medido (`/selo/notas/atos-em-geral`):
        `13.12.1` × 1 e, com mais folhas, `13.12.3` × o excedente — ou a
        eletrônica `13.12.4` sozinha. **O PROTOCOLO VEM PRIMEIRO**: os itens
        13.12 e 13.13 que ele traz valem no lugar dos calculados, e ficam
        marcados como usados por esta certidão.

        A BUSCA (13.13) VAI POR ÚLTIMO, selo próprio pelo mesmo caminho —
        decisão do oficial de 15/10/2026 —, e não vai com a eletrônica, que
        já a inclui. Sem precedente no acervo: zero selos de busca das Notas.
        """
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return SR.recado_pendente_selo()
        protocolo = numero_digitado(_campo("protocolo_id"))   # LD13
        do_protocolo: list = []
        if protocolo is not None:
            with db.connect() as con:
                do_protocolo = [
                    (r["id"], r["codigo_ato"], r["quantidade"])
                    for r in banco(con).ler(
                        """SELECT id, codigo_ato, quantidade FROM cx_protocolo_atos
                            WHERE protocolo_id=%s AND usado_em IS NULL
                              AND (codigo_ato ILIKE '13.12.%%'
                                   OR codigo_ato ILIKE '13.13.%%')
                            ORDER BY id""",
                        (protocolo,))]
        itens = [(c, max(1, int(q or 1))) for _i, c, q in do_protocolo
                 if c in NCE.ITENS_DA_CERTIDAO]
        if not itens:
            itens = NCE.itens_do_selo(folhas, eletronica=eletronica)
        busca_final = BU.busca_entre([c for _i, c, _q in do_protocolo],
                                     "NOTAS") or busca
        if (busca_final and BU.vira_selo(busca_final)
                and not BU.ja_inclui_busca([c for c, _q in itens])):
            itens.append((busca_final, 1))
        _marcar_itens_do_protocolo_como_usados(
            [int(i) for i, _c, _q in do_protocolo], int(certidao_id),
            tabela="nt_certidoes")
        versao = AS.versao_da_tabela_de_custas(
            NCE.CAMINHO_DO_SELO, db.get_setting("selo_tabela_custas_em", ""))
        saiu, faltou = [], []
        recusou = False
        for codigo, quantidade in itens:
            try:
                corpo = NCE.envelope(
                    codigo=codigo, quantidade=quantidade,
                    escrevente=usuario_nome(), versao_tabela=versao,
                    parte=parte, isento=isento, motivo_isencao=motivo)
            except NCE.CertidaoNotasError as erro:
                faltou.append(str(erro))
                continue
            r = AS.selar_o_ato_lavrado(
                db, Path(app.config["DATA_DIR"]), tabela="nt_certidoes",
                ato_id=certidao_id, tipo="CERTIDAO", atribuicao="NOTAS",
                agora=agora(), cns=sv().get("ri_cns"), usuario=usuario_nome(),
                dados=corpo, caminho=NCE.CAMINHO_DO_SELO,
                referencia=f"nt_certidoes:{int(certidao_id)}:{codigo}:1")
            recusou = recusou or not r["selado"]
            (saiu if r["selado"] else faltou).append(
                r["numero"] if r["selado"] else r["motivo"])
        if not saiu:
            marcar = AS.recado_de_recusa if recusou else AS.recado_de_falta
            return marcar(
                f" A certidão saiu SEM SELO: {faltou[0] if faltou else ''}")
        recado = f" {len(saiu)} selo(s): {', '.join(saiu)}."
        if faltou:
            recado += f" ({len(faltou)} item(ns) sem selo: {faltou[0]})"
        return recado

    @app.route("/notas/certidoes")
    @login_required
    def notas_certidoes():
        """Buscar e emitir a certidão das Notas. Só LÊ: emitir é o botão."""
        nome = (request.args.get("nome") or "").strip()
        documento = (request.args.get("documento") or "").strip()
        de = (request.args.get("de") or "").strip()
        ate = (request.args.get("ate") or "").strip()
        ato_id = (request.args.get("ato_id") or "").strip()
        ato_linha, achados, buscou = None, [], bool(nome or documento)
        with db.connect() as con:
            if ato_id.isdigit():
                try:
                    # sem o teor, o ato ainda tem breve relato (LD02): a tela
                    # oferece só ele, e `emitir` recusa o inteiro teor. O
                    # «²» e os 5.000 dígitos passam pelo `isdigit()` e não
                    # são id do banco: -1, o «Ato não encontrado.» (LD13)
                    ato_linha = NCE.ato(con, numero_digitado(ato_id) or -1,
                                        exige_teor=False)
                except NCE.CertidaoNotasError as erro:
                    flash(str(erro), "danger")
            if buscou:
                try:
                    achados = NCE.buscar(con, nome=nome, documento=documento,
                                         periodo_de=de, periodo_ate=ate)
                except NCE.CertidaoNotasError as erro:
                    flash(str(erro), "danger")
                    buscou = False
            receita = _receita_da_certidao_das_notas(con)
            caixa = _caixa_aberto(con)
            protocolos = _protocolos_abertos(con)
            emitidas = NCE.listar(con)
            # a mesma frase que `emitir` põe na certidão: com o ajuste da casa
            periodo = NCE.frase_do_periodo(de, ate, con=con)
        return render_template(
            "notas_certidoes.html", ato=ato_linha,
            rotulo_tipo=(NCE._rotulo_tipo(ato_linha["tipo"])
                         if ato_linha else ""),
            nome=nome, documento=documento, de=de, ate=ate, buscou=buscou,
            achados=achados, cabivel=NCE.tipo_para(achados),
            # O SIGILO DO TESTAMENTO (LG04): a tela pede o requerimento ou a
            # certidão de óbito só quando há testamento no pedido.
            sob_sigilo=(NCE.e_testamento(ato_linha)
                        or any(NCE.e_testamento(x) for x in achados)),
            periodo=periodo, receita=receita,
            caixa=caixa, protocolos=protocolos, emitidas=emitidas)

    @app.route("/notas/certidoes/emitir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_certidao_emitir():
        """Emite a certidão das Notas. ESCREVE, e FALA COM A REDE depois.

        As recusas de balcão — gratuidade sem motivo, busca sem escolha — vêm
        ANTES de numerar. O selo sai fora da transação; se não sair, a
        certidão é cancelada com o motivo, como as outras desta casa.
        """
        ato_id = _campo("ato_id")
        ato_id_n = numero_digitado(ato_id)
        volta = url_for("notas_certidoes", ato_id=ato_id or None,
                        nome=_campo("nome") or None,
                        documento=_campo("documento") or None,
                        de=_campo("de") or None, ate=_campo("ate") or None)
        try:
            grat_cod, motivo, isento = _gratuidade_do_form()
            busca = _busca_do_form("NOTAS")
        except (AS.AtoError, BU.BuscaError) as erro:
            flash(str(erro), "danger")
            return redirect(volta)
        eletronica = request.form.get("eletronica") == "1"
        if eletronica:
            # A ELETRÔNICA JÁ INCLUI A BUSCA (13.12.4): nada a mais.
            busca = None
        # DO ATO IDENTIFICADO, A FORMA É A QUE O PEDIDO DIZ (LD02): inteiro
        # teor, quando não diz, ou breve relato — a cópia resumida do art. 851.
        tipo_previsto = ((_campo("tipo") or NCE.TIPOS_DO_ATO[0]).upper()
                         if ato_id else None)
        try:
            with db.transaction() as con:
                modelo = None
                try:
                    if tipo_previsto:
                        modelo = MODELOS.corpo_de(
                            con, NCE.CHAVE_DO_MODELO[tipo_previsto])
                except Exception:                         # noqa: BLE001
                    modelo = None
                r = NCE.emitir(
                    con, hoje=hoje(), agora=agora(),
                    # o que não é dígito é «sem ato», como sempre; o que é e
                    # não cabe no banco é o «Ato não encontrado.» (LD13)
                    ato_id=(ato_id_n if ato_id_n is not None else -1)
                    if ato_id.isdigit() else None,
                    tipo=tipo_previsto,
                    nome=_campo("nome") or None,
                    documento=_campo("documento") or None,
                    periodo_de=_campo("de") or None,
                    periodo_ate=_campo("ate") or None,
                    requerente=_campo("requerente") or None,
                    requerente_documento=_campo("requerente_documento") or None,
                    finalidade=_campo("finalidade") or None,
                    eletronica=eletronica, busca_item=busca,
                    isento=isento, motivo_isencao=motivo,
                    usuario=usuario_nome(), usuario_funcao=usuario_funcao(),
                    modelo=modelo if ato_id else _modelo_da_busca(con),
                    # O SIGILO DO TESTAMENTO (LG04): o requerimento escrito do
                    # testador ou a certidão de óbito — `NCE.fundamento_do_sigilo`.
                    requerimento_escrito=(
                        request.form.get("requerimento_escrito") == "1"),
                    obito_apresentado=_campo("obito_apresentado") or None)
                selo_a_mao = _selar_se_pedido(con, "nt_certidoes",
                                              r["certidao_id"], "NOTAS")
                aviso = selo_a_mao + _cobrar_se_pedido(
                    con, "nt_certidoes", r["certidao_id"], "CERTIDAO",
                    busca=busca)
        except (NCE.CertidaoNotasError, AS.AtoError) as erro:
            flash(str(erro), "danger")
            return redirect(volta)
        try:
            folhas_tela = int(_campo("folhas") or 0) or None
        except ValueError:
            folhas_tela = None
        folhas = CFOLHAS.decidir_folhas_antes_de_emitir(
            fonte="TEXTO", corpo_html=r["teor"],
            folhas_informadas=folhas_tela, get_setting=db.get_setting)
        with db.transaction() as con:
            banco(con).escrever("UPDATE nt_certidoes SET folhas=%s WHERE id=%s",
                                (int(folhas), r["certidao_id"]))
        recado_do_selo = ""
        if not selo_a_mao:
            recado_do_selo = _selar_a_certidao_das_notas(
                r["certidao_id"], folhas=folhas, eletronica=eletronica,
                busca=busca, parte=r["parte"], isento=isento, motivo=motivo)
            aviso += recado_do_selo
        motivo_selo = _motivo_da_falha_do_selo(recado_do_selo)
        if motivo_selo:
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE nt_certidoes SET cancelada=1,
                           motivo_cancelamento=%s, cancelada_em=%s,
                           cancelada_por=%s WHERE id=%s""",
                    (f"Selo não emitido: {motivo_selo}", agora(),
                     usuario_nome(), r["certidao_id"]))
                # o mesmo defeito do RTD: a das Notas também marca antes do selo
                _soltar_itens_da_certidao_cancelada(con, "nt_certidoes",
                                                    r["certidao_id"])
            audit("NOTAS_CERTIDAO_NAO_EMITIDA_SELO_FALHOU", "nt_certidoes",
                  r["certidao_id"], {"numero": r["numero"], "ano": r["ano"],
                                     "motivo": motivo_selo})
            flash("Certidão NÃO emitida: o selo não saiu. "
                  f"Motivo: {motivo_selo}. Corrija o problema do selo e "
                  "tente de novo.", "danger")
            return redirect(volta)
        audit("NOTAS_CERTIDAO", "nt_certidoes", r["certidao_id"],
              {"numero": r["numero"], "ano": r["ano"], "tipo": r["tipo"],
               "achados": r["achados"], "hash": r["hash"],
               "folhas": folhas, **({"busca": busca} if busca else {})})
        flash(f"{NCE.nome_do_tipo(db.connect)[r['tipo']]} n. {r['numero']}/{r['ano']} "
              f"emitida.{aviso}", "success")
        return redirect(url_for("notas_certidao",
                                certidao_id=r["certidao_id"]))

    def _modelo_da_busca(con) -> str | None:
        """O texto do catálogo da certidão por busca — o tipo só se sabe
        depois da busca, e por isso o modelo se escolhe pelo que ela achar."""
        try:
            achados = NCE.buscar(con, nome=_campo("nome") or None,
                                 documento=_campo("documento") or None,
                                 periodo_de=_campo("de") or None,
                                 periodo_ate=_campo("ate") or None)
            return MODELOS.corpo_de(
                con, NCE.CHAVE_DO_MODELO[NCE.tipo_para(achados)])
        except Exception:                                 # noqa: BLE001
            return None

    @app.route("/notas/certidoes/<int:certidao_id>")
    @login_required
    def notas_certidao(certidao_id: int):
        """A certidão como saiu — para conferir e reimprimir."""
        with db.connect() as con:
            linha = NCE.certidao(con, certidao_id)
            if not linha:
                abort(404)
            selos = AS.etiquetas_do_ato(con, "nt_certidoes", certidao_id,
                                        linha.get("selo") or "")
            nomes = NCE.nome_do_tipo(con)
        return render_template("notas_certidao.html", certidao=linha,
                               selos=selos,
                               nome_do_tipo=nomes.get(
                                   linha["tipo"], linha["tipo"]))

    @app.route("/notas/certidoes/<int:certidao_id>/odt")
    @login_required
    def notas_certidao_odt(certidao_id: int):
        """A certidão em PDF (ou .odt), com o cabeçalho e o carimbo da casa.

        O carimbo é o das outras certidões (`carimbo_da_certidao_odf`, que
        pede a `selo_no_papel` o que escrever): todos os selos da certidão —
        a primeira folha, a folha acrescida e a busca —, cada um com os
        valores que declara.
        """
        with db.connect() as con:
            linha = NCE.certidao(con, certidao_id)
            if not linha:
                abort(404)
            etiqueta = AS.etiqueta_do_ato(con, "nt_certidoes", certidao_id,
                                          linha.get("selo") or "")
            # o título é moldura, refeita a cada impressão (como o cabeçalho
            # e a cidade): segue o ajuste da casa; o teor é o congelado
            nomes = NCE.nome_do_tipo(con)
        s = sv()
        cancelada = ("<p align=\"center\"><b>CERTIDÃO CANCELADA — "
                     f"{linha['motivo_cancelamento'] or ''}</b></p>"
                     if int(linha["cancelada"] or 0) else "")
        try:
            emitida_extenso = data_por_extenso(
                date.fromisoformat(str(linha["emitida_em"])[:10]))
        except (TypeError, ValueError):
            emitida_extenso = hoje_extenso()
        titulo = nomes.get(linha["tipo"], "Certidão").upper()
        # A EMISSÃO NO RODAPÉ É DATA DE PAPEL (LD02, 21/10/2026): saía
        # «2026-10-20T10:30:00», como o banco a guarda (CN-MA art. 795, § 4º);
        # agora «20/10/2026 às 10:30:00», a forma do carimbo do selo.
        emitida = str(linha["emitida_em"] or "")
        emitida_papel = (NCE.data_de_papel(emitida[:10])
                         + (f" às {emitida[11:19]}" if len(emitida) >= 19 else ""))
        html = (f'<p align="center"><b>{titulo}</b></p>'
                f'<p align="center">n. {linha["numero"]}/{linha["ano"]}</p>'
                f'{cancelada}<p></p>{linha["teor"]}<p></p>'
                f'<p>{s.get("ri_cidade", "")}-{s.get("ri_uf", "")}, '
                f'{emitida_extenso}.</p><p></p>'
                f'<p align="center">{linha["emitida_por"] or ""}</p>'
                f'<p align="center">{linha["emitida_por_funcao"] or ""}</p>'
                f'<p></p><p><font size="8">Certidão n. {linha["numero"]}/'
                f'{linha["ano"]}, emitida em {emitida_papel}. '
                f'Autenticidade: {linha["hash_certidao"]}</font></p>')
        frag_do_selo, imagens_do_selo = RODT.carimbo_da_certidao_odf(
            etiqueta, rotulo="SELO DA CERTIDÃO")
        cab_odf, cab_imgs = RODT.cabecalho_certidao_completo_odf(s)
        todas = dict(cab_imgs or {})
        todas.update(imagens_do_selo or {})
        arquivo = gerar_odt(html_para_odf(html) + frag_do_selo,
                            titulo=f"Certidão {linha['numero']}/{linha['ano']}",
                            cabecalho_odf=cab_odf, imagens=todas or None,
                            cabecalho_altura_min="2.0cm",
                            cabecalho_margem_baixo="0.25cm",
                            cabecalho_borda=False)
        audit("NOTAS_CERTIDAO_ODT", "nt_certidoes", certidao_id,
              {"numero": linha["numero"], "ano": linha["ano"]})
        return IMPW.resposta_do_papel(
            arquivo, nome=f"certidao-notas-{linha['numero']}-{linha['ano']}",
            get_setting=db.get_setting,
            voltar_para=url_for("notas_certidao", certidao_id=certidao_id))

    @app.route("/notas/certidoes/<int:certidao_id>/cancelar",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_certidao_cancelar(certidao_id: int):
        """Cancela a certidão. ESCREVE. O teor fica.

        Com selo, a declaração de que ele foi cancelado no portal do TJMA é
        obrigatória — a regra da certidão do Protesto.
        """
        with db.connect() as con:
            linha = NCE.certidao(con, certidao_id)
            selos = AS.etiquetas_do_ato(con, "nt_certidoes", certidao_id,
                                        (linha or {}).get("selo") or "")
        if not linha:
            abort(404)
        if selos and _campo("selo_cancelado_tjma") != "1":
            flash("Antes de cancelar, cancele o selo no portal do Selo "
                  "Eletrônico do TJMA e marque a declaração.", "danger")
            return redirect(url_for("notas_certidao", certidao_id=certidao_id))
        try:
            with db.transaction() as con:
                NCE.cancelar(con, certidao_id, motivo=_campo("motivo"),
                             agora=agora(), usuario=usuario_nome())
        except NCE.CertidaoNotasError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("notas_certidao", certidao_id=certidao_id))
        audit("NOTAS_CERTIDAO_CANCELADA", "nt_certidoes", certidao_id,
              {"motivo": _campo("motivo"),
               "declaracao_selo_tjma": bool(selos)})
        flash("Certidão cancelada. O teor fica gravado, como saiu.",
              "success")
        return redirect(url_for("notas_certidao", certidao_id=certidao_id))

    def _modelo_do_termo(con, chave: str | None = None) -> str | None:
        """O termo do protesto que o oficial editou no catálogo, ou None.

        Até 14/10/2026 as duas rotas que protestam não o passavam, e editar
        `PT_TERMO_PROTESTO` na tela de modelos não tinha efeito nenhum no
        livro — o carimbo que mente na tela de edição. O termo do
        cancelamento (`PT_TERMO_CANCELAMENTO`, LD04) chega pelo mesmo caminho.
        """
        try:
            import modelos_da_casa as MODELOS
            return MODELOS.corpo_de(con, chave or PTERMO.CHAVE_NO_CATALOGO) or None
        except Exception:                       # noqa: BLE001 — cai no padrão
            return None

    @app.route("/protesto/<int:titulo_id>/lancar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_lancar(titulo_id: int):
        """Lança o próximo ato da vida do título. ESCREVE.

        Uma rota para os cinco atos, e não cinco rotas: o que muda é qual
        função do domínio se chama, e o domínio é quem sabe se o ato cabe na
        situação em que o título está. A tela não repete essa regra — repetir
        regra de domínio na tela é como as duas divergem.
        """
        ato = _campo("ato")
        # O ROBÔ NÃO CANCELA NEM CUMPRE ORDEM JUDICIAL (revisão de segurança,
        # 26/10/2026): ele alcança esta rota para lavrar, e a recusa é aqui
        # dentro, antes de abrir a transação.
        import selo_robo as SR
        if SR.lancamento_vedado_ao_robo(ato):
            abort(403)
        voltar = redirect(url_for("protesto_titulo", titulo_id=titulo_id))
        situacao_antes = situacao_depois = None
        try:
            with db.transaction() as con:
                # A SITUAÇÃO DE ANTES DO ATO, lida com a linha presa — é para
                # ela que o título volta se o selo não sair (ver abaixo). O
                # domínio prende a mesma linha logo em seguida, na mesma
                # transação: a ordem das travas não muda.
                antes = PT.titulo_para_gravar(con, titulo_id)
                situacao_antes = antes["situacao"] if antes else None
                if ato == "APONTAMENTO":
                    r = PT.lancar_apontamento(con, titulo_id, sv=sv(),
                                              agora=agora(),
                                              data_extenso=hoje_extenso(),
                                              usuario=usuario_nome())
                elif ato == "INTIMACAO":
                    r = PT.lancar_intimacao(
                        con, titulo_id, modo=_campo("modo") or "PESSOAL",
                        agora=agora(), usuario=usuario_nome(),
                        digital=bool(request.form.get("digital")),
                        codigo_edital=_campo("codigo_edital") or None,
                        comprovante=_campo("comprovante") or None)
                elif ato == "PROTESTO":
                    # O TRÍDUO (tarefa 56): antes do termo inicial recusa;
                    # depois do termo final exige o motivo do atraso.
                    r = PT.lancar_protesto(con, titulo_id, sv=sv(),
                                           agora=agora(),
                                           data_extenso=hoje_extenso(),
                                           usuario=usuario_nome(),
                                           modelo_do_termo=_modelo_do_termo(con),
                                           conferir_triduo=True,
                                           motivo_atraso=_campo("motivo_atraso") or None)
                elif ato == "DESISTENCIA":
                    r = PT.lancar_desistencia(con, titulo_id,
                                              motivo=_campo("motivo"),
                                              agora=agora(),
                                              usuario=usuario_nome())
                elif ato == "PAGAMENTO":
                    r = PT.lancar_pagamento(
                        con, titulo_id, sv=sv(), agora=agora(),
                        data_extenso=hoje_extenso(),
                        valor_pago=_campo("valor_pago") or None,
                        usuario=usuario_nome(),
                        forma_pagamento=_campo("forma_pagamento") or None,
                        forma_identificacao=_campo("forma_identificacao") or None,
                        emolumentos=_campo("emolumentos") or None)
                elif ato == "CANCELAMENTO":
                    r = PT.lancar_cancelamento(
                        con, titulo_id, hipotese=_campo("hipotese"),
                        fundamento=_campo("fundamento"), agora=agora(),
                        usuario=usuario_nome(),
                        modelo_do_termo=_modelo_do_termo(
                            con, PTERMO.CHAVE_DO_CANCELAMENTO))
                elif ato == "SUSTACAO":
                    # A ORDEM JUDICIAL QUE IMPEDE O PROTESTO — Lei 9.492/1997,
                    # art. 17. Ela nao sela e nao cobra: nao e ato da
                    # serventia, e o cumprimento de uma ordem de fora.
                    r = PT.lancar_sustacao(
                        con, titulo_id, juizo=_campo("juizo"),
                        processo=_campo("processo"), agora=agora(),
                        recebido_em=_campo("recebido_em") or None,
                        observacao=_campo("observacao") or None,
                        usuario=usuario_nome())
                elif ato == "EFEITO_SUSPENSIVO":
                    # A ordem que chega DEPOIS do protesto: o registro fica, e
                    # a publicidade dele para. E o unico dos dois institutos
                    # que esta casa usou — uma vez, em 18/08/2025.
                    #
                    # COM A MARCA DO CNN art. 263-K (LH13, 21/10/2026): o
                    # caráter da decisão, se ela manda emitir negativa e se o
                    # processo é sigiloso — é o que a certidão lê.
                    r = PT.lancar_efeito_suspensivo(
                        con, titulo_id, juizo=_campo("juizo"),
                        processo=_campo("processo"), agora=agora(),
                        carater=_campo("carater") or None,
                        manda_negativa=bool(request.form.get("manda_negativa")),
                        segredo_de_justica=bool(
                            request.form.get("segredo_de_justica")),
                        recebido_em=_campo("recebido_em") or None,
                        observacao=_campo("observacao") or None,
                        usuario=usuario_nome())
                elif ato == "REVOGACAO_EFEITO_SUSPENSIVO":
                    r = PT.lancar_revogacao_efeito_suspensivo(
                        con, titulo_id, agora=agora(),
                        recebido_em=_campo("recebido_em") or None,
                        observacao=_campo("observacao") or None,
                        usuario=usuario_nome())
                elif ato == "REVOGACAO_SUSTACAO":
                    # E a data que conta e a do RECEBIMENTO, que e de onde o
                    # § 2o faz correr o prazo de um dia util.
                    r = PT.lancar_revogacao_sustacao(
                        con, titulo_id, agora=agora(),
                        recebido_em=_campo("recebido_em") or None,
                        observacao=_campo("observacao") or None,
                        usuario=usuario_nome())
                else:
                    raise PT.ProtestoError(
                        f"Ato desconhecido: {ato!r}.")
                depois = PT.titulo(con, titulo_id)
                situacao_depois = depois["situacao"] if depois else None
                # O SELO DIGITADO A MAO FICA NUMA VARIAVEL PROPRIA, e nao
                # somado ao resto: e ele, e so ele, que impede o pedido
                # automatico. Perguntar por `aviso` faria a cobranca —
                # que tambem escreve nele — cancelar o selo automatico
                # justamente quando ela e o que o dispara.
                selo_a_mao = _selar_se_pedido(con, "pt_atos", r["ato_id"],
                                              "PROTESTO")
                aviso = selo_a_mao
                # O EMOLUMENTO A POSTERIORI (LG05). No título diferido, o ato
                # antes do desfecho sela e fica DEVENDO; o desfecho cobra o
                # que se marcou e o que ficou devido, pela tabela que o CN-MA
                # art. 925, § 11 manda. Título antecipado: como sempre.
                cobranca = (POST.cobranca_do_ato(con, titulo_id, ato,
                                                 hoje=hoje())
                            if ato in POST.MOMENTO_DO_ATO else None)
                if cobranca and cobranca["diferir"]:
                    aviso += _diferir_se_pedido(con, titulo_id, r["ato_id"], ato)
                else:
                    aviso += _cobrar_se_pedido(
                        con, "pt_atos", r["ato_id"], ato,
                        data_do_ato=(cobranca or {}).get("data_da_tabela"))
                    if (cobranca and cobranca["cobra_diferidos"]
                            and request.form.get("cobrar_diferidos")):
                        aviso += _cobrar_os_diferidos(con, titulo_id,
                                                      r["ato_id"], cobranca)
        except (PT.ProtestoError, AS.AtoError, LN.LivroError,
                PTERMO.TermoError, POST.PosterioriError) as erro:
            flash(str(erro), "danger")
            return voltar
        # O SELO SAI AGORA, com o ato lavrado — um para cada item cobrado.
        recado_do_selo = ""
        # Ordens judiciais não são atos cobrados/selados da serventia. Elas
        # apenas suspendem ou restabelecem os efeitos do protesto; pedir selo
        # aqui faria a ausência correta de item parecer falha do aparelho e
        # apagaria justamente a ordem que deve impedir o protesto.
        #
        # E O APONTAMENTO TAMBÉM NÃO SELA — 21/10/2026. Medido: dos 1.409
        # apontamentos do E-Ofício, 1.161 não têm selo nenhum, e os 248 que têm
        # trazem o do ato POSTERIOR (LIQTIT 184, PROTIT 64); o apontamento da
        # remessa da CRA também não sela. Pedir selo aqui fazia o 900001/1
        # (ato 4043) sair lavrado no livro e marcado cancelado, com o título
        # já APONTADO — o estado que nenhuma tela desfaz.
        atos_sem_selo_proprio = {
            "SUSTACAO", "REVOGACAO_SUSTACAO", "EFEITO_SUSPENSIVO",
            "REVOGACAO_EFEITO_SUSPENSIVO", "APONTAMENTO",
        }
        if not selo_a_mao and ato not in atos_sem_selo_proprio:
            recado_do_selo = _selar_o_protesto("pt_atos", r["ato_id"], ato)
            aviso += recado_do_selo
        motivo_selo = _motivo_da_falha_do_selo(recado_do_selo)
        if motivo_selo:
            situacao_restaurada = None
            with db.transaction() as con:
                # A LINHA DO TÍTULO PRESA PRIMEIRO (FOR UPDATE), na mesma ordem
                # do lançamento — título, depois o ato —, e lida de novo: é a
                # situação de AGORA que decide se a volta cabe (ver abaixo).
                no_titulo = PT.titulo_para_gravar(con, titulo_id)
                banco(con).escrever(
                    """UPDATE pt_atos
                          SET cancelado=1, motivo_cancelamento=%s
                        WHERE id=%s""",
                    (f"Selo não emitido: {motivo_selo}", r["ato_id"]))
                # O TÍTULO VOLTA À SITUAÇÃO DE ANTES (LT04, 20/10/2026). Até
                # aqui só o ato se anulava, e o título ficava PROTESTADO, PAGO
                # ou CANCELADO por um ato que não existiu: o «tente de novo» do
                # recado era recusado pelo domínio («só se protesta título já
                # intimado»), a intimação anulada deixava o título INTIMADO e
                # o protesto cabia sem intimação válida. A condição na
                # situação de depois é a guarda: se outro balcão já mexeu no
                # título nesse meio-tempo, a volta não passa por cima dele.
                # A auditoria diz para onde ele VOLTOU (`situacao_restaurada`,
                # o nome da produção desde 21/10/2026), e None quando a guarda
                # não deixou voltar.
                agora_esta = no_titulo["situacao"] if no_titulo else None
                if situacao_antes and agora_esta == situacao_antes:
                    situacao_restaurada = situacao_antes
                elif (situacao_antes and situacao_depois
                        and agora_esta == situacao_depois):
                    banco(con).escrever(
                        "UPDATE pt_titulos SET situacao=%s WHERE id=%s",
                        (situacao_antes, titulo_id))
                    situacao_restaurada = situacao_antes
            audit("PROTESTO_ATO_NAO_LAVRADO_SELO_FALHOU", "pt_atos",
                  r["ato_id"], {"ato": ato, "motivo": motivo_selo,
                                "situacao_restaurada": situacao_restaurada})
            flash("Ato NÃO lançado: o selo não saiu. "
                  f"Motivo: {motivo_selo}. Corrija o problema do "
                  "selo e tente de novo.",
                  "danger")
            return voltar
        # `audit` abre transação própria: FORA do `with`, como no resto da casa.
        audit("PROTESTO_ATO", "pt_atos", r["ato_id"], {"ato": ato, **{
            k: v for k, v in r.items() if k != "ato_id"}})
        onde = (f" Livro {r.get('livro_numero')}, fl. {r.get('rotulo')}, "
                f"nº {r.get('numero_ordem')}." if r.get("numero_ordem") else "")
        flash(f"{ato.capitalize()} lançado.{onde}{aviso}", "success")
        return voltar

    @app.route("/protesto/<int:titulo_id>")
    @login_required
    def protesto_titulo(titulo_id: int):
        """A ficha do título: os dados, os devedores e os atos da vida dele."""
        with db.connect() as con:
            bd = banco(con)
            titulo = bd.um("SELECT * FROM pt_titulos WHERE id=%s",
                           (titulo_id,))
            if not titulo:
                flash("Título não encontrado.", "danger")
                return redirect(url_for("protesto_titulos"))
            devedores = bd.ler(
                "SELECT * FROM pt_devedores WHERE titulo_id=%s ORDER BY id",
                (titulo_id,))
            # A IMAGEM DO TÍTULO, ONDE O ATO ACONTECE. Quem lavra o protesto
            # precisa do documento à vista — é a mesma razão do relato #25,
            # sobre o título apresentado na prenotação do RI.
            imagens = PIMG.imagens_do_titulo(con, titulo_id)
            atos = bd.ler(
                "SELECT * FROM pt_atos WHERE titulo_id=%s ORDER BY id",
                (titulo_id,))
        for a in atos:
            a["detalhe"] = json.loads(a.get("detalhe_json") or "{}")
        # Que atos cabem AGORA. Quem decide é o domínio; a tela só não oferece
        # o que ele recusaria — mas se oferecer por engano, ele recusa.
        # O que a casa cobrou em cada um destes atos, medido em 24.849 selos.
        # NAO e orcamento fechado, e a tela diz isso.
        with db.connect() as con:
            receitas = _receitas_de(con, "pt_atos",
                                    ("APONTAMENTO", "INTIMACAO", "PROTESTO",
                                     "PAGAMENTO", "CANCELAMENTO",
                                     "DESISTENCIA"))
            caixa = _caixa_aberto(con)
            cobrancas = _cobrancas_de(con, "pt_atos", atos)
            protocolos = _protocolos_abertos(con)
            # OS AVISOS SAO LISTA, e nao um so: 255 dos 1.361 titulos do
            # acervo tem mais de um. Endereco que muda, entrega que nao deu
            # certo, aviso que se refaz.
            avisos = AV.do_titulo(con, titulo_id)
            for a in avisos:
                a["tentativas"] = AV.tentativas(con, a["id"])
            # A LISTA DE ATENCAO, sobre TODAS as partes do titulo — devedor
            # e credor. Conferir uma so deixaria a outra passar.
            fraudes = _fraudes_de(con, [
                {"nome": d.get("nome"), "documento": d.get("documento_numero"),
                 "papel_no_ato": "devedor"} for d in devedores
            ] + [
                {"nome": titulo["cedente_nome"],
                 "documento": titulo["cedente_documento"],
                 "papel_no_ato": "credor"},
            ])

        situacao = titulo["situacao"]
        # A ORDEM JUDICIAL DE SUSTACAO, se houver — Lei 9.492/1997, art. 17.
        # Ela decide o que a ficha oferece, e por isso vem antes da lista.
        with db.connect() as _c:
            sustacao = PT.sustacao_em_vigor(_c, titulo_id)
            suspensao = PT.efeito_suspensivo_em_vigor(_c, titulo_id)
            # QUEM PAGA CADA ATO, E POR QUAL TABELA (LG05) — o quadro do
            # emolumento a posteriori, e a frase de cada formulário.
            emolumento = POST.resumo_para_a_ficha(_c, titulo_id, hoje=hoje())
            # QUEM APRESENTOU, com o que os papéis dele vão dizer (LD08): o
            # documento e o endereço que faltam se veem aqui, antes do aviso.
            apresentante = PT.apresentante_do_titulo(_c, titulo)
            apresentante["documento_na_tela"] = PCE.formatar_documento(
                apresentante["documento"])
            # AS HIPÓTESES DE CANCELAMENTO QUE CABEM AGORA (LH13): o catálogo
            # inteiro no PROTESTADO, e só a anuência e a ordem judicial no
            # PAGO com protesto em pé — o legado do pagamento depois do
            # protesto, que a regra de 21/10/2026 não admite mais.
            catalogo = PT.hipoteses_que_cabem(_c, titulo)
            # O TRÍDUO (tarefa 56): só no intimado, que é quando o protesto cabe.
            triduo = (TRIDUO.para_a_lista(_c, [{"id": titulo_id}],
                                          hoje=hoje())[0]
                      if situacao == "INTIMADO" else None)
        pago_com_protesto = situacao == "PAGO" and bool(catalogo)
        cabem = []
        # O APONTAMENTO É O PRIMEIRO ATO DA VIDA DO TÍTULO — Lei 9.492/1997,
        # art. 3º. Ele faltava aqui, e por isso título cadastrado no balcão
        # nascia RECEBIDO e não tinha por onde andar: nenhuma tela chamava
        # `lancar_apontamento`. Nos títulos do acervo o buraco não aparecia,
        # porque todos os 1.366 já vieram apontados do E-Ofício.
        if situacao == "RECEBIDO":
            cabem.append("APONTAMENTO")
        if situacao in ("APONTADO", "INTIMADO"):
            cabem.append("INTIMACAO")
        if situacao == "INTIMADO":
            cabem.append("PROTESTO")
        if situacao in ("RECEBIDO", "APONTADO", "INTIMADO"):
            cabem.append("DESISTENCIA")
        # O PAGAMENTO SÓ ANTES DO PROTESTO (LH13, 21/10/2026): «protesto nao
        # pode ser pago na serventia depois de lavrar» — o oficial. Depois do
        # protesto o caminho é a carta de anuência e o cancelamento.
        if situacao not in PT.SITUACOES_SEM_PAGAMENTO:
            cabem.append("PAGAMENTO")
        if catalogo:
            cabem.append("CANCELAMENTO")

        # COM ORDEM EM VIGOR, TRES ATOS SAEM DA TELA — art. 17, § 1o: o titulo
        # sustado so pode ser pago, protestado ou retirado COM AUTORIZACAO
        # JUDICIAL. A tela tira por educacao; o dominio recusa por dever, e ha
        # teste que manda o ato direto para a rota so para ver isso.
        if sustacao:
            cabem = [x for x in cabem
                     if x not in PT.ATOS_QUE_A_SUSTACAO_BLOQUEIA]
            cabem.append("REVOGACAO_SUSTACAO")
        elif situacao not in PT.SITUACOES_FINAIS:
            # E a ordem pode chegar a qualquer momento, ate antes da
            # intimacao: por isso o registro dela nao depende da situacao.
            cabem.append("SUSTACAO")

        # O OUTRO INSTITUTO — a ordem que chega DEPOIS do protesto lavrado. Ele
        # nao bloqueia ato nenhum: o que ele para e a PUBLICIDADE, e quem le
        # isso e a certidao. Por isso ele nao entra em `ATOS_QUE_A_SUSTACAO
        # _BLOQUEIA` nem tira botao da tela.
        if suspensao:
            cabem.append("REVOGACAO_EFEITO_SUSPENSIVO")
        elif situacao == "PROTESTADO":
            cabem.append("EFEITO_SUSPENSIVO")
        return render_template("atrib_protesto_ficha.html", titulo=dict(titulo),
                               emolumento=emolumento, apresentante=apresentante,
                               imagens=imagens, sustacao=sustacao,
                               suspensao=suspensao,
                               devedores=devedores, atos=atos, cabem=cabem,
                               modos=PT.MODOS_INTIMACAO, receitas=receitas,
                               caixa=caixa, cobrancas=cobrancas,
                               protocolos=protocolos,
                               avisos=avisos, fraudes=fraudes,
                               cabe_aviso=(situacao in
                                           AV.SITUACOES_QUE_ACEITAM_AVISO),
                               motivos_aviso=AV.motivos_para_escolher(),
                               entregadores=AV.ENTREGADORES,
                               catalogo=catalogo,
                               pago_com_protesto=pago_com_protesto,
                               caracteres=PT.CARATER_DA_ORDEM,
                               triduo=(triduo or {}).get("triduo"),
                               triduo_situacao=(triduo or {}).get(
                                   "triduo_situacao"))

    @app.route("/protesto/<int:titulo_id>/ordem/<int:ato_id>/marcar",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_ordem_marcar(titulo_id: int, ato_id: int):
        """Marca a ordem que suspendeu os efeitos do protesto. ESCREVE.

        É A TELA DE EDITAR A ORDEM (LH13, 21/10/2026 — CNN art. 263-K): a
        ordem lançada antes da regra nova não tem o caráter da decisão, e o
        protesto dela fica fora da certidão até alguém ler o mandado e marcar.
        A mesma porta corrige a marca posta errada. Não sela e não cobra: não
        é ato da serventia, é a leitura de uma ordem de fora.
        """
        voltar = redirect(url_for("protesto_titulo", titulo_id=titulo_id))
        try:
            with db.transaction() as con:
                r = PT.marcar_ordem_judicial(
                    con, ato_id, carater=_campo("carater") or None,
                    manda_negativa=bool(request.form.get("manda_negativa")),
                    segredo_de_justica=bool(
                        request.form.get("segredo_de_justica")),
                    agora=agora(), usuario=usuario_nome())
                if r["titulo_id"] != titulo_id:
                    raise PT.ProtestoError(
                        "Esta ordem judicial é de outro título.")
        except PT.ProtestoError as erro:
            flash(str(erro), "danger")
            return voltar
        # `audit` abre transação própria: FORA do `with`, como no resto da casa.
        audit("PROTESTO_ORDEM_MARCADA", "pt_atos", ato_id,
              {k: v for k, v in r.items() if k != "ato_id"})
        quanto = PT.CARATER_DA_ORDEM[r["carater"]].split(" (")[0]
        flash(f"Ordem judicial marcada: decisão {quanto}. A certidão emitida "
              "daqui em diante segue a marca; a já emitida não muda.",
              "success")
        return voltar

    # ---------------------------------------------------------------- RCPN

    @app.route("/rcpn")
    @login_required
    def rcpn_assentos():
        """Os assentos de nascimento, casamento e óbito."""
        return render_template("atrib_lista.html", **_listar("rcpn"))

    @app.route("/rcpn/averbacoes")
    @login_required
    def rcpn_averbacoes():
        """Localiza o assento antes de abrir a tela própria de averbação."""
        return render_template("atrib_rcpn_averbacoes.html",
                               **_listar("rcpn"))

    @app.route("/rcpn/novo", methods=["GET", "POST"],
               defaults={"especie_url": None})
    @app.route("/rcpn/novo/<especie_url>", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_assento_novo(especie_url: str | None):
        """Escolhe e lavra uma espécie do RCPN em tela própria. ESCREVE.

        A ESPÉCIE MANDA NA SÉRIE, e a tela não pergunta o livro. Quem escolhe
        é `rc_assento.SERIE_DA_ESPECIE`: deixar o balcão escolher o livro é
        deixar lançar óbito em livro de nascimento.

        A MATRÍCULA DE 32 DÍGITOS É COMPOSTA AO LAVRAR — **mudou em
        30/08/2026**. Antes não era, e o motivo estava escrito aqui: «o
        algoritmo oficial não foi medido, e número de matrícula inventado é
        pior que campo em branco». O motivo era bom e deixou de valer — a regra
        está no Anexo IV do manual de carga da CRC, conferida contra 255 casos.

        Quem compõe é `rc_assento.lavrar_assento`, depois de o assento receber
        livro, folha e número: antes disso não há o que compor. Matrícula
        digitada pelo escrevente manda, e não é sobrescrita.
        """
        # O QUE VEIO DE ARQUIVO, se veio — relato #31, segunda metade.
        #
        #   **SÓ NO GET, e consumido de uma vez** (`pop`): se ficasse na
        #   sessão, o formulário do próximo cliente abriria com os dados do
        #   anterior, e alguém lavraria assento com o nome de outra pessoa.
        #
        #   E no POST manda o que o escrevente digitou, e não o arquivo: a
        #   correção dele na tela é que vale.
        def escolher():
            # do_acervo: veio de «Digitar informações» no hub de assentos /
            # importar-acervo. A flag só orienta o texto da tela; nao inventa
            # campos de livro/folha.
            return render_template(
                "atrib_rcpn_escolher.html",
                grupos=RCPN_GRUPOS_DE_ESPECIES,
                nomes=RC.NOME_DA_ESPECIE,
                slugs=RCPN_SLUG_DA_ESPECIE,
                do_acervo=(request.args.get("do_acervo") or "").strip())

        do_arquivo = None
        guardado = (session.get(IMPP.NA_SESSAO)
                    if request.method == "GET" else None)
        if guardado and guardado.get("formulario") != "rcpn_assento_novo":
            guardado = None

        # O RASCUNHO DE UMA TELA JÁ SALVA, reaberto por `?rascunho_id=` —
        # relato do oficial em 09/09/2026: «salvei um rascunho, mas não
        # tenho como abrir ele no sistema». O mecanismo (`rascunho_de_tela`)
        # SALVAVA, LISTAVA e APAGAVA desde 31/08 — só faltava reabrir, em
        # nenhuma das telas que já salvam. **Só no GET**, pela mesma razão
        # do do_arquivo logo abaixo: reabrir não pode se misturar com o que
        # o escrevente está digitando agora.
        rascunho = None
        rascunho_id = request.args.get("rascunho_id", type=int)
        if request.method == "GET" and rascunho_id:
            with db.connect() as con:
                try:
                    rascunho = RASC.ler(con, rascunho_id)
                except RASC.RascunhoError as erro:
                    flash(str(erro), "danger")
            if rascunho and rascunho["tela"] != "rcpn_assento_novo":
                flash("Este rascunho não é de um assento do Registro Civil.",
                      "danger")
                rascunho = None
        # A LEITURA QUE PREENCHEU ESTE RASCUNHO (12/10/2026): a conferência
        # aparece aqui mesmo, e os anexos acompanham o ato ao lavrar.
        leitura_origem = None
        if rascunho:
            import rc_leitura_documentos as LEIT
            with db.connect() as con:
                leitura_origem = LEIT.leitura_do_rascunho(con, rascunho["id"])

        # A importação antiga desemboca em `/rcpn/novo`. Se ela já diz a
        # espécie, vai para a porta certa sem consumir os dados; a segunda
        # requisição os retira da sessão. Se não diz, o escrevente escolhe a
        # espécie e só então o conteúdo é consumido.
        if request.method == "GET" and especie_url is None:
            importada = str(((guardado or {}).get("valores") or {}).get(
                "especie") or "").strip().upper()
            if not importada and rascunho:
                importada = str(
                    (rascunho.get("dados") or {}).get("especie")
                    or "").strip().upper()
            if importada in RCPN_SLUG_DA_ESPECIE:
                return redirect(url_for(
                    "rcpn_assento_novo",
                    especie_url=RCPN_SLUG_DA_ESPECIE[importada],
                    do_acervo=request.args.get("do_acervo") or None,
                    rascunho_id=rascunho_id or None))
            if rascunho:
                flash(
                    "O rascunho não diz a espécie do assento — escolha "
                    "abaixo. O que estava digitado continua guardado, e "
                    "nada foi perdido.", "warning")
            return escolher()

        if especie_url is None:
            # Compatibilidade com integrações e testes anteriores que ainda
            # fazem POST diretamente na porta de escolha. A tela humana nunca
            # envia a espécie em campo editável.
            especie = _campo("especie").upper()
        else:
            especie = RCPN_ESPECIE_DO_SLUG.get(especie_url, "")

        if especie not in RC.ESPECIES:
            flash(
                f"Espécie de assento desconhecida: {especie or especie_url!r}. "
                f"As que existem são: {', '.join(RC.ESPECIES)}.", "danger")
            return escolher()

        if request.method == "GET" and guardado:
            do_arquivo = session.pop(IMPP.NA_SESSAO, None)

        def tela(habilitacao_origem=None):
            with db.connect() as con:
                contexto = _para_cobrar(con, "rc_atos", "REGISTRO")
            valores = dict(
                do_arquivo["valores"] if do_arquivo
                else rascunho["dados"] if rascunho
                else request.form)
            if (habilitacao_origem and not do_arquivo and not rascunho
                    and request.method == "GET"):
                pre = HAB.valores_para_lavrar_casamento(habilitacao_origem)
                valores = {**pre, **{k: v for k, v in valores.items() if v}}
            # Arquivos do formato anterior trazem só `nome`. Nas novas telas
            # o nome vive no bloco da pessoa; copiar para exibição preserva a
            # importação sem reintroduzir dois campos para a mesma coisa.
            if (especie in {"NASCIMENTO", "OBITO", "NATIMORTO"}
                    and not valores.get("pessoa_nome")
                    and valores.get("nome")):
                valores["pessoa_nome"] = valores["nome"]
            _dac = (request.args.get("do_acervo")
                    or request.form.get("do_acervo")
                    or "").strip()
            return render_template("atrib_rcpn_novo.html",
                                   do_arquivo=do_arquivo,
                                   do_acervo=_dac,
                                   rascunho=rascunho,
                                   rascunho_id=(rascunho["id"] if rascunho else None),
                                   leitura_origem=leitura_origem,
                                   habilitacao_origem=habilitacao_origem,
                                   especie=especie,
                                   especie_url=RCPN_SLUG_DA_ESPECIE[especie],
                                   nome_especie=RC.NOME_DA_ESPECIE[especie],
                                   # AS DUAS PARTES SEPARADAS — relato #37,
                                   # item 1: a frase baixa a caixa da espécie
                                   # sem alcançar a letra do livro.
                                   so_especie=RC.nome_e_livro(especie)[0],
                                   livro_da_especie=RC.nome_e_livro(especie)[1],
                                   nomes=RC.NOME_DA_ESPECIE,
                                   locais=IBGE.LOCAL_DO_NASCIMENTO,
                                   gemeos=IBGE.GEMEO,
                                   # A LISTA FECHADA DA COR OU RACA. Sai do
                                   # modulo, e nao do template: escrita na
                                   # tela, ela divergiria da que a CRC aceita
                                   # no primeiro conserto.
                                   cores=RC.CORES_E_RACAS,
                                   regimes=HC.REGIMES,
                                   naturezas=IBGE.NATUREZA_DO_OBITO,
                                   locais_obito=IBGE.LOCAL_DO_OBITO,
                                   marcas_do_obito=MARCA.MARCAS,
                                   titulos_livro_e=RC.TITULOS_DO_LIVRO_E.get(especie, ()),
                                   nomes_do_titulo=RC.NOME_DO_TITULO,
                                   # O município do local que a tela já traz
                                   # escrito (LD01) — o da serventia.
                                   municipio_padrao=RC.municipio_do_local_padrao(
                                       sv()),
                                   tardio_sugerido=_tardio_sugerido(especie),
                                   form=valores,
                                   **contexto)

        habilitacao_origem = None
        if request.method == "GET" and especie in RC.ESPECIES_DE_CASAMENTO:
            hc_id = request.args.get("habilitacao_id", type=int)
            if hc_id:
                with db.connect() as con:
                    linha = banco(con).um(
                        "SELECT * FROM hc_habilitacoes WHERE id=%s",
                        (int(hc_id),))
                if not linha:
                    flash(f"Habilitação #{hc_id} não encontrada.", "danger")
                elif linha["situacao"] != "HABILITADO":
                    flash(
                        "Esta habilitação não está expedida — só se lavra "
                        "casamento a partir de habilitação válida e em vigor.",
                        "warning")
                elif HAB.habilitacao_vencida(linha, hoje()):
                    flash(
                        f"A habilitação venceu em {linha['habilitacao_vale_ate']} "
                        f"(CC art. 1.532). Refaça o processo antes de registrar "
                        f"o casamento.", "danger")
                else:
                    habilitacao_origem = dict(linha)

        if request.method != "POST":
            return tela(habilitacao_origem)

        # ------------------------------------------------ conferencia
        # Pedido do oficial 09/09/2026: tela que SEPAR A livro e folha de
        # seguranca, imprime rascunho para o declarante e mostra dados do
        # CPF — SEM lavrar. Lavrar so sai dessa tela, com a folha escolhida.
        acao = (_campo("acao") or "").strip().lower()

        def _tela_conferencia(valores_form, recusa=None):
            """Monta a conferencia a partir do form. Nao grava.

            Mostra o PROXIMO assento (livro/folha/termo) separado da folha
            de seguranca, e permite incluir o CPF (copiar CRC + campo
            cpf_registrado que grava na lavratura).
            """
            with db.connect() as con:
                folhas = PP.listar(con, situacao="EM BRANCO", limite=None)
                sug = PP.proxima_folha(con)
                serie = RC.SERIE_DA_ESPECIE.get(especie) or ""
                livro = banco(con).um(
                    "SELECT * FROM nu_livros WHERE serie=%s AND ativo=1 "
                    "AND encerrado=0 ORDER BY id DESC LIMIT 1",
                    (serie,),
                )
                num_row = banco(con).um(
                    "SELECT proximo FROM nu_numeracao WHERE serie=%s",
                    (serie,),
                )
            livro_d = dict(livro) if livro else None
            termo_previsto = int(num_row["proximo"]) if num_row else None
            folha_prevista = (livro_d or {}).get("folha_atual") or ""
            livro_num = (livro_d or {}).get("numero") or ""
            data_iso = hoje()
            data_br = ""
            if data_iso and len(data_iso) >= 10:
                data_br = (f"{data_iso[8:10]}/{data_iso[5:7]}/{data_iso[:4]}")
            nat = (valores_form.get("naturalidade_declarada") or "").strip()
            nat_uf = "MA"
            if "/" in nat:
                partes = [p.strip() for p in nat.rsplit("/", 1)]
                if len(partes) == 2 and len(partes[1]) == 2:
                    nat, nat_uf = partes[0], partes[1].upper()
            assento_prev = {
                "nome": (valores_form.get("pessoa_nome")
                         or valores_form.get("nome") or "").strip(),
                "data_fato": (valores_form.get("data_fato") or "").strip(),
                "naturalidade_declarada": nat,
                "naturalidade_uf": nat_uf,
                "dnv": (valores_form.get("dnv") or "").strip(),
                "matricula": "",
                "numero": termo_previsto or "",
                "data_ato": data_iso or "",
            }
            pessoas_prev = []
            if (valores_form.get("pessoa_nome")
                    or valores_form.get("pessoa_sexo")):
                pessoas_prev.append({
                    "papel": "REGISTRADO",
                    "nome": valores_form.get("pessoa_nome") or "",
                    "sexo": valores_form.get("pessoa_sexo") or "",
                })
            if valores_form.get("filiacao1_nome"):
                pessoas_prev.append({
                    "papel": "MAE",
                    "nome": valores_form.get("filiacao1_nome") or "",
                })
            if valores_form.get("filiacao2_nome"):
                pessoas_prev.append({
                    "papel": "PAI",
                    "nome": valores_form.get("filiacao2_nome") or "",
                })
            proximo_assento = None
            if livro_d:
                proximo_assento = {
                    "serie": livro_d.get("serie") or serie,
                    "livro": livro_num,
                    "complemento": livro_d.get("complemento") or "",
                    "folha": folha_prevista,
                    "termo": termo_previsto or "",
                    "data_registro": data_br,
                }
            # A CONFERÊNCIA DOS DADOS (11/10/2026) — a mesma régua que a
            # lavratura aplica, mostrada antes, com o declarante na frente. O
            # termo vai com quem assina já posto, como a lavratura o grava: o
            # traço de quem assina não é erro aqui.
            try:
                import rc_conferencia_dados as CONF
                with db.connect() as con_conf:
                    teor_conf = _teor_com_quem_assina(
                        con_conf, valores_form.get("teor") or "", especie)
                dados_conf = CONF.dados_do_formulario(
                    {**valores_form, "teor": teor_conf or ""},
                    especie=especie, data_ato=data_iso)
                dados_conf["numero"] = termo_previsto
                conferencia_dos_dados = CONF.conferir(dados_conf)
            except Exception:                           # noqa: BLE001
                # Conferir não pode derrubar a tela de conferência: a
                # lavratura confere de novo, e lá ela recusa.
                conferencia_dos_dados = []
            # A RECUSA DA LAVRATURA soma o que só aparece depois de gravar (a
            # testemunha fantasma nascia em `registrar_pessoa`).
            for p in recusa or []:
                if p not in conferencia_dos_dados:
                    conferencia_dos_dados.append(p)
            import rc_conferencia_dados as CONF
            para_corrigir = CONF.campos_para_corrigir(conferencia_dos_dados)
            # O REGISTRO TARDIO (21/10/2026): a régua das testemunhas do
            # art. 249, II, para o requerimento que se imprime aqui.
            tardio_regra = None
            if especie == "NASCIMENTO" and RC.e_tardio(
                    valores_form.get("registro_tardio")):
                tardio_regra = RC.regra_das_testemunhas_do_tardio(
                    {"data_fato": valores_form.get("data_fato"),
                     "dnv": valores_form.get("dnv"), "data_ato": data_iso},
                    [{"papel": "REGISTRADO", "data_nascimento":
                      valores_form.get("pessoa_data_nascimento")}])
            return render_template(
                "rcpn_conferencia.html",
                tardio_regra=tardio_regra,
                hoje_br=data_br,
                conferencia_dos_dados=conferencia_dos_dados,
                para_corrigir=para_corrigir,
                pode_forcar=_papel_atual() in CONF.PAPEIS_QUE_FORCAM,
                motivo_minimo=CONF.MOTIVO_MINIMO_LETRAS,
                veio_da_recusa=bool(recusa),
                especie=especie,
                especie_url=RCPN_SLUG_DA_ESPECIE[especie],
                nome_especie=RC.NOME_DA_ESPECIE[especie],
                so_especie=RC.nome_e_livro(especie)[0],
                form=valores_form,
                folhas_disponiveis=folhas,
                folha_sugerida=(sug["codigo"] if sug else None),
                livro_corrente=livro_d,
                proximo_assento=proximo_assento,
                norma=CPFRC,
                cpf_copiar=CPFRC.dados_para_copiar(
                    assento_prev, pessoas_prev,
                    lugar={
                        "livro_numero": livro_num,
                        "folha": folha_prevista,
                    }),
                cpf_faltas=CPFRC.o_que_falta_para_pedir(
                    assento_prev, pessoas_prev),
            )

        if acao in ("conferir", "voltar_editar"):
            valores = {k: v for k, v in request.form.items()
                       if k not in ("csrf_token",)}
            if acao == "voltar_editar":
                with db.connect() as con:
                    contexto = _para_cobrar(con, "rc_atos", "REGISTRO")
                return render_template(
                    "atrib_rcpn_novo.html",
                    do_arquivo=None, especie=especie,
                    do_acervo=(request.form.get("do_acervo")
                               or request.args.get("do_acervo")
                               or "").strip(),
                    especie_url=RCPN_SLUG_DA_ESPECIE[especie],
                    nome_especie=RC.NOME_DA_ESPECIE[especie],
                    so_especie=RC.nome_e_livro(especie)[0],
                    livro_da_especie=RC.nome_e_livro(especie)[1],
                    nomes=RC.NOME_DA_ESPECIE,
                    locais=IBGE.LOCAL_DO_NASCIMENTO, gemeos=IBGE.GEMEO,
                    cores=RC.CORES_E_RACAS, regimes=HC.REGIMES,
                    naturezas=IBGE.NATUREZA_DO_OBITO,
                    locais_obito=IBGE.LOCAL_DO_OBITO,
                    marcas_do_obito=MARCA.MARCAS,
                    titulos_livro_e=RC.TITULOS_DO_LIVRO_E.get(especie, ()),
                    nomes_do_titulo=RC.NOME_DO_TITULO,
                    municipio_padrao=RC.municipio_do_local_padrao(sv()),
                    tardio_sugerido=_tardio_sugerido(especie),
                    form=valores, **contexto)
            return _tela_conferencia(valores)

        # Lavrar exige folha quando o caminho gasta papel.
        caminho_selo = AS.caminho_do_ato(
            "rc_atos", "REGISTRO", especie=especie)
        if AS.gasta_folha_de_seguranca(caminho_selo):
            if not _folha_seguranca_do_form():
                flash(
                    "Escolha a folha de seguranca na conferencia antes de "
                    "lavrar — ela nao se escolhe sozinha.",
                    "danger")
                valores = {k: v for k, v in request.form.items()
                           if k not in ("csrf_token",)}
                return _tela_conferencia(valores)

        # A SAÍDA DE EMERGÊNCIA (11/10/2026): «lavrar mesmo assim» é do oficial
        # e do substituto. O balcão que mandar o botão pelo endereço recebe a
        # recusa aqui, antes de qualquer gravação.
        forcar_motivo = None
        if acao == "lavrar_forcado":
            import rc_conferencia_dados as CONF_F
            if _papel_atual() not in CONF_F.PAPEIS_QUE_FORCAM:
                flash("Lavrar por cima da trava é do oficial ou do substituto. "
                      "Arrume o que está em vermelho, ou chame quem responde "
                      "pela serventia.", "danger")
                return _tela_conferencia(
                    {k: v for k, v in request.form.items() if k != "csrf_token"})
            forcar_motivo = _campo("forcar_motivo")

        nome = _campo("nome")
        if not nome and especie in {"NASCIMENTO", "OBITO", "NATIMORTO"}:
            nome = _campo("pessoa_nome")
        if not nome and especie in RC.ESPECIES_DE_CASAMENTO:
            nomes_do_casal = [x for x in (
                _campo("nubente1_nome"), _campo("nubente2_nome")) if x]
            nome = " e ".join(nomes_do_casal)
        try:
            with db.transaction() as con:
                # Digitar acervo (?do_acervo=1): origem ACERVO pula a régua
                # completa do ato novo (art. 54/80) — livro antigo veio com
                # poucos campos. Balcão novo continua MANUAL.
                _origem_lavra = (
                    "ACERVO"
                    if (request.form.get("do_acervo")
                        or request.args.get("do_acervo")
                        or "").strip()
                    else "MANUAL")
                r = RC.lavrar_assento(
                    con, especie=especie, nome=nome, sv=sv(),
                    agora=agora(), data_extenso=hoje_extenso(),
                    data_fato=_campo("data_fato") or None,
                    matricula=_campo("matricula") or None,
                    # A HABILITAÇÃO DESTA CASA JÁ NO ASSENTO QUANDO O TERMO SE
                    # ESCREVE (LD01): é dela que saem a data dos proclamas e
                    # a relação dos documentos. Antes ela entrava no
                    # `dados_json` só depois da lavratura (o bloco do fim, que
                    # continua), e o termo não a achava.
                    # (o número que não é id do banco é «sem habilitação»,
                    # que é o que o id que não existe já dava — LD13)
                    dados=({"habilitacao_id":
                            numero_digitado(_campo("habilitacao_id"))}
                           if especie in RC.ESPECIES_DE_CASAMENTO
                           and numero_digitado(_campo("habilitacao_id")) is not None
                           else None),
                    teor=_teor_do_nascimento(
                        _teor_com_quem_assina(con, _campo("teor"), especie),
                        especie, _origem_lavra, con),
                    usuario=usuario_nome(),
                    origem=_origem_lavra,
                    # O QUE A REMESSA DO IBGE PEDE, perguntado enquanto o
                    # declarante está na frente do escrevente com a DNV na
                    # mão. Depois vira telefonema para a família.
                    ibge={"local_nascimento": _campo("ibge_local") or None,
                          "gemeo": _campo("ibge_gemeo") or None,
                          "dnv": _campo("dnv") or None,
                          "numero_do": _campo("numero_do") or None,
                          "natureza_obito": _campo("natureza_obito") or None,
                          "local_obito": _campo("local_obito") or None},
                    # O QUE O TERMO PEDE E A CERTIDÃO IMPRIME. Perguntado no
                    # mesmo momento que o bloco do IBGE, e pelo mesmo motivo:
                    # o declarante está na frente. A diferença entre os dois é
                    # o destino — o do IBGE não sai no papel do cliente; este
                    # sai, está no teor do termo.
                    termo_dados={
                        "cor_raca": _campo("cor_raca") or None,
                        "hora_fato": _campo("hora_fato") or None,
                        "local_fato_nome": (
                            _campo("local_fato_nome")
                            or ("IGNORADO" if _campo("nao_tem_local_fato")
                                else None)),
                        "local_fato_endereco":
                            _campo("local_fato_endereco") or None,
                        # O MUNICÍPIO DO LOCAL (LD01): o que o balcão diz, ou o
                        # da serventia — o mesmo que a tela já traz escrito.
                        "local_fato_municipio": (
                            _campo("local_fato_municipio")
                            or (RC.municipio_do_local_padrao(sv())
                                if (_origem_lavra == "MANUAL" and especie
                                    in RC.ESPECIES_COM_MUNICIPIO_DO_LOCAL)
                                else None)),
                        "naturalidade_declarada":
                            _campo("naturalidade_declarada") or None,
                        # EXCLUSIVOS DO ÓBITO. `anotar_do_termo` mantém a
                        # lista fechada por espécie e recusa estes mesmos
                        # campos se uma integração tentar enviá-los em
                        # nascimento ou casamento.
                        "causa_morte": _campo("causa_morte") or None,
                        "atestante": _campo("atestante") or None,
                        "atestante_documento":
                            _campo("atestante_documento") or None,
                        "local_sepultamento":
                            _campo("local_sepultamento") or None,
                        "testamento": _campo("testamento") or None,
                        # O QUE A LEI PEDE E NÃO TINHA CAMPO (13/10/2026):
                        # só os da espécie, todos opcionais.
                        **{c: _campo(c) or None for c in
                           RC.CAMPOS_DA_LEI_POR_ESPECIE.get(especie, ())}},
                    # DE QUE SERVENTIA VEIO A HABILITAÇÃO — e isto decide se o
                    # assento COMPRA selo ou REAPROVEITA o da habilitação
                    # daqui. Ver `_selar_o_ato`.
                    habilitacao_serventia=_campo("habilitacao_serventia") or None,
                    habilitacao_selo=_campo("habilitacao_selo") or None,
                    # A PESSOA DE QUEM O ASSENTO É — o registrado, os nubentes,
                    # o falecido. Até 28/08/2026 o assento guardava só o NOME
                    # dela, e isso deixava a certidão de casamento e a de óbito
                    # incompletas e a remessa do IBGE impossível.
                    regime_bens=_campo("regime_bens") or None,
                    pessoas=_pessoas_do_formulario(especie),
                    forcar_motivo=forcar_motivo,
                    # AS PERGUNTAS DO ÓBITO ENTRAM DENTRO DA LAVRATURA (relato
                    # #130, 14/10/2026): a CRC recusa óbito sem «deixou bens»,
                    # e a conferência das centrais roda lá dentro, antes do
                    # commit — gravadas depois, ela as acharia sempre vazias.
                    marcas_do_obito=(
                        {k: _campo(k) for k in MARCA.CHAVES if _campo(k)}
                        if especie == "OBITO" else None),
                    # O TERMO DE PATERNIDADE DO NASCIMENTO SEM O PAI (23/10/2026):
                    # a lavratura recusa sem ele, e o gera junto.
                    paternidade=({c: _campo(c) for c in (
                        "paternidade_tipo", "suposto_pai_nome",
                        "suposto_pai_profissao", "suposto_pai_documento",
                        "suposto_pai_residencia",
                        # a terceira saída (27/10/2026): por que a mãe não está
                        "motivo_ausencia_mae")}
                        if especie == "NASCIMENTO" else None))
                # O TERMO VAZIO SE ESCREVE PELO MODELO DA CASA (11/10/2026). É
                # o caminho da importação sem robô: o arquivo traz os CAMPOS, e
                # o texto que vai ao livro sai deles, pelo mesmo `congelar` da
                # tela do termo — coerente com o cadastro por construção.
                # Falhar aqui não desfaz a lavratura: o termo se escreve depois
                # pela tela, e a fiscalização do RCPN acusa o que ficou sem.
                # O CPF DA CONFERÊNCIA ENTRA ANTES DO TERMO (13/10/2026). Ele era
                # gravado só depois do selo, e o termo pelo modelo — escrito
                # aqui — lia `cpf_registrado` ainda vazio: o nascimento do termo
                # 19582 saiu sem o CPF e foi consertado por script. Gravar aqui
                # é idempotente com a gravação de depois, que fica para o aviso.
                _cpf_antes = (_campo("cpf_registrado") or "").strip()
                if _cpf_antes and CPFRC.valido(_cpf_antes):
                    CPFRC.gravar(con, r["assento_id"], _cpf_antes)
                    CPFRC.gravar_no_registrado(con, r["assento_id"], _cpf_antes)
                # AS PERGUNTAS DO ÓBITO TAMBÉM ENTRAM ANTES DO TERMO (13/10/2026).
                # Elas só se respondiam numa tela à parte, depois de lavrar, e o
                # termo — escrito aqui — saía sem «era eleitor», «deixou bens»,
                # «deixou filhos» (art. 80; art. 255 do Código de Normas). O
                # branco continua «não perguntado» e vira a frase do § 1º.
                # Desde 14/10/2026 quem as grava é `lavrar_assento`
                # (`marcas_do_obito`, acima), antes da conferência das centrais.
                termo_pelo_modelo = ""
                if (_origem_lavra == "MANUAL" and not (_campo("teor") or "").strip()
                        and especie in RCT.especies_com_termo()):
                    _ponto_de_retorno(con, "SAVEPOINT termo_pelo_modelo")
                    try:
                        RCT.congelar(con, r["assento_id"], serventia=_servent(),
                                     agora=agora(),
                                     livro=str(r.get("livro_numero") or ""),
                                     folha=str(r.get("folha") or ""))
                        _ponto_de_retorno(con, "RELEASE termo_pelo_modelo")
                        termo_pelo_modelo = "ok"
                    except Exception as erro_termo:          # noqa: BLE001
                        _ponto_de_retorno(con, "ROLLBACK TO termo_pelo_modelo")
                        _ponto_de_retorno(con, "RELEASE termo_pelo_modelo")
                        termo_pelo_modelo = str(erro_termo)
                aviso = _selar_se_pedido(con, "rc_atos", r["ato_id"], "RCPN")
                cob_msg = _cobrar_se_pedido(con, "rc_atos", r["ato_id"],
                                           "REGISTRO")
        except RC.ConferenciaError as erro:
            # ARRUMAR SÓ O PROBLEMA (pedido do oficial, 11/10/2026): a recusa
            # volta à conferência com tudo o que foi digitado guardado, e abre
            # para edição SÓ os campos que travaram. Nada foi gravado.
            flash("O assento não foi lavrado: arrume só o que está em "
                  "vermelho e lavre de novo. O resto continua como estava.",
                  "danger")
            if forcar_motivo is not None:
                # Quem tentou forçar precisa saber por que o forçar não passou.
                flash(str(erro).split("Nada foi gravado.")[-1].strip()
                      or str(erro), "danger")
            return _tela_conferencia(
                {k: v for k, v in request.form.items() if k != "csrf_token"},
                recusa=erro.problemas)
        except (RC.RcError, AS.AtoError) as erro:
            flash(str(erro), "danger")
            return tela()
        if termo_pelo_modelo == "ok":
            flash("O termo foi escrito pelo modelo da casa, a partir dos campos "
                  "conferidos. Confira-o na ficha antes de colher as "
                  "assinaturas.", "info")
        elif termo_pelo_modelo:
            flash("O assento foi lavrado, mas o termo não pôde ser escrito pelo "
                  f"modelo: {termo_pelo_modelo} Escreva-o pela tela do termo.",
                  "warning")
        # O SELO SAI AGORA, com o assento já lavrado — e fora da transação.
        recado_do_selo = _selar_o_ato(
            "rc_atos", r["ato_id"], "REGISTRO", "RCPN", aviso,
            especie=especie,
            folha_escolhida=_folha_seguranca_do_form() or None)
        aviso = (recado_do_selo or "") + cob_msg
        motivo_selo = _motivo_da_falha_do_selo(recado_do_selo)
        if motivo_selo:
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE rc_assentos
                          SET situacao='CANCELADO'
                        WHERE id=%s""",
                    (r["assento_id"],))
            audit("RCPN_ASSENTO_NAO_LAVRADO_SELO_FALHOU", "rc_assentos",
                  r["assento_id"], {"especie": especie, "serie": r["serie"],
                                    "numero_ordem": r.get("numero_ordem"),
                                    "motivo": motivo_selo})
            flash("Assento NÃO lavrado: o selo não saiu. "
                  f"Motivo: {motivo_selo}. Corrija o problema do "
                  "selo e tente de novo.",
                  "danger")
            return tela()
        audit("RCPN_ASSENTO_NOVO", "rc_assentos", r["assento_id"],
              {"especie": especie, "serie": r["serie"],
               "numero_ordem": r.get("numero_ordem")})
        if r.get("lavratura_forcada"):
            audit("RCPN_LAVRATURA_FORCADA", "rc_assentos", r["assento_id"],
                  {"motivo": forcar_motivo,
                   "travas": [p["codigo"] for p in r["avisos_da_conferencia"]
                              if p["gravidade"] == "BLOQUEIA"]})
            flash("Lavrado POR CIMA DA TRAVA, com o seu motivo. O que travou "
                  "ficou gravado ao lado do assento e aparece todo dia na "
                  "fiscalização do RCPN até ser arrumado (retificação ou "
                  "averbação).", "warning")
        # CPF informado na conferencia: grava no assento ja lavrado.
        cpf_conf = (_campo("cpf_registrado") or "").strip()
        if cpf_conf:
            try:
                with db.transaction() as con:
                    formatado = CPFRC.gravar(con, r["assento_id"], cpf_conf)
                    CPFRC.gravar_no_registrado(con, r["assento_id"], cpf_conf)
                aviso += f" CPF {formatado} gravado."
                audit("RCPN_CPF", "rc_assentos", r["assento_id"], None)
            except (ValueError, CPFRC.CpfError) as erro_cpf:
                flash(f"Assento lavrado, mas o CPF nao gravou: {erro_cpf}",
                      "warning")
        # ÓBITO FORA DO PRAZO — **avisa, e não trava**.
        #
        #   Excedido o prazo, o assento de óbito só sai por determinação
        #   judicial (art. 258). O sistema diz isso, e deixa a decisão com quem
        #   responde por ela: a data do falecimento pode estar errada na
        #   declaração, o lugar pode ser dos distantes, e a determinação pode
        #   já estar em mãos. Travar aqui seria decidir no lugar do oficial com
        #   menos informação que ele.
        if especie.strip().upper() == "OBITO" and _campo("data_fato"):
            try:
                s = OBTARDIO.situacao(_campo("data_fato"), hoje())
                if s["fora_do_prazo"]:
                    flash(f"{s['aviso']} {s['o_que_o_pedido_leva']}", "warning")
            except ValueError:
                pass          # data ilegível já é recusada antes, na lavratura

        # A MATRICULA VAI NO AVISO porque e o numero que o balcao copia para a
        # certidao e para a remessa. Deixa-la so no banco obrigaria a abrir o
        # assento de novo para le-la.
        if r.get("matricula"):
            aviso += f" Matrícula {r['matricula']}."
        if r.get("matricula_porque_nao"):
            # NAO FICA CALADO. O assento existe e esta certo; o que faltou foi
            # o numero nacional, e quem esta no balcao precisa saber disso
            # agora — nao na hora de emitir a certidao.
            flash(r["matricula_porque_nao"], "warning")
        # O QUE A CONFERÊNCIA DOS DADOS SÓ AVISOU (11/10/2026): não impediu,
        # mas quem lavrou precisa ver agora, com o declarante ainda no balcão.
        for p in r.get("avisos_da_conferencia") or []:
            flash(f"Confira: {p['mensagem']}", "warning")
        # O ASSENTO JÁ ESTÁ LAVRADO AQUI: o «²» e os 5.000 dígitos que passavam
        # pelo `isdigit()` davam a tela de erro, e quem lavrou achava que nada
        # tinha saído (LD13). Número que não é id do banco é «sem habilitação»
        # e «sem leitura», que é o que o id que não existe já dava.
        hc_form = numero_digitado(_campo("habilitacao_id"))
        if hc_form is not None:
            with db.transaction() as con:
                ass = banco(con).um(
                    "SELECT dados_json FROM rc_assentos WHERE id=%s",
                    (int(r["assento_id"]),))
                dados_hc = json.loads(ass["dados_json"] or "{}")
                dados_hc["habilitacao_id"] = hc_form
                banco(con).escrever(
                    "UPDATE rc_assentos SET dados_json=%s WHERE id=%s",
                    (json.dumps(dados_hc, ensure_ascii=False),
                     int(r["assento_id"])))
        # OS ANEXOS DA LEITURA ACOMPANHAM O ATO (12/10/2026). Até aqui ficavam
        # só na leitura, e a ficha do assento não os mostrava.
        leitura_form = numero_digitado(request.form.get("leitura_id"))
        if leitura_form is not None:
            import rc_leitura_documentos as LEIT
            with db.transaction() as con:
                ligados = LEIT.ligar_documentos(con, leitura_form, "rc_assento", int(r["assento_id"]),
                                                agora=db.now(), por_id=usuario_id_do_sistema())
            if ligados:
                aviso += f" Os {ligados} anexo(s) da leitura passaram a acompanhar o assento."
        flash(f"Assento lavrado no Livro {r.get('livro_numero')}, "
              f"fl. {r.get('rotulo')}, nº {r.get('numero_ordem')}.{aviso}",
              "success")
        # O JUIZ DE PAZ É OPCIONAL, COM AVISO — decisão de 15/10/2026 (relato
        # #124). Recusar a lavratura sem ele travaria o balcão por um nome que
        # se completa depois na ficha; calar faria a linha da folha sair sem
        # nome sem ninguém notar.
        if especie == "CASAMENTO" and not _campo("juiz_de_paz"):
            flash("O nome do(a) Juiz(a) de Paz que presidiu o ato não foi "
                  "informado: a linha de assinatura da folha sai só com o "
                  "rótulo. Complete pelo botão «Alterar livro / termo / "
                  "folha» da ficha do assento.", "warning")
        return redirect(url_for("rcpn_assento", assento_id=r["assento_id"]))

    @app.route("/rcpn/ato/<int:ato_id>/selar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_ato_selar(ato_id: int):
        """Sela o REGISTRO do civil que ficou pendente de selo. FALA COM A REDE.

        FOLHA_DA_1A_VIA_20261009. Ato lavrado por conta de robo fica
        "Pendente de selo" (regra do oficial de 05/10/2026) e nao havia por
        onde o escrevente selar depois. Aqui ele sela escolhendo a folha que
        esta na mao dele - sem pre-selecao -, e e essa que vai ao TJMA e
        que a 1a via vai mostrar travada. Robo: 403.
        """
        import selo_robo as SR
        if SR.exige_humano_para_selar():
            abort(403)
        with db.connect() as con:
            ato = banco(con).um(
                "SELECT id, assento_id, tipo, COALESCE(selo,'') selo "
                "FROM rc_atos WHERE id=%s", (int(ato_id),))
        if not ato:
            abort(404)
        volta = redirect(url_for("rcpn_assento", assento_id=ato["assento_id"]))
        if str(ato["selo"]).strip():
            flash(f"Este ato já tem selo ({ato['selo']}).", "info")
            return volta
        especie = _especie_do_assento(ato["assento_id"])
        folha = _folha_seguranca_do_form() or None
        if AS.gasta_folha_de_seguranca(AS.caminho_do_ato(
                "rc_atos", ato["tipo"], especie=especie)) and not folha:
            flash("Escolha a folha de segurança que está na sua mão "
                  "antes de selar - ela vai ao TJMA e é nela que a 1ª via "
                  "será impressa.", "danger")
            return volta
        recado = _selar_o_ato("rc_atos", int(ato_id), ato["tipo"], "RCPN", "",
                              especie=especie, folha_escolhida=folha)
        motivo = _motivo_da_falha_do_selo(recado)
        if motivo:
            flash(f"O selo não saiu: {motivo}. O ato continua pendente "
                  "de selo.", "danger")
            return volta
        audit("RCPN_ATO_SELADO", "rc_atos", int(ato_id),
              {"folha": folha, "recado": (recado or "").strip()})
        flash(f"Registro selado.{recado or ''}", "success")
        return volta

    @app.route("/rcpn/<int:assento_id>/lancar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_lancar(assento_id: int):
        """Averba, anota ou retifica o assento. ESCREVE.

        Os três blocos da divisão tripartite. NÃO ocupam folha nova — lançam-se
        no espaço do próprio assento, como no livro físico; quem garante isso é
        `rc_assento`, e não esta rota.
        """
        tipo = _campo("tipo")
        voltar = redirect(url_for("rcpn_assento", assento_id=assento_id))
        funcoes = {"AVERBACAO": RC.averbar, "ANOTACAO": RC.anotar,
                   "RETIFICACAO": RC.retificar}
        if tipo not in funcoes:
            flash(f"Tipo de lançamento desconhecido: {tipo!r}.", "danger")
            return voltar
        try:
            with db.transaction() as con:
                extra = ({"fundamento": _campo("fundamento")}
                         if tipo == "RETIFICACAO"
                         else {"fundamento": _campo("fundamento") or None})
                r = funcoes[tipo](con, assento_id, teor=_campo("teor"),
                                  agora=agora(), usuario=usuario_nome(), **extra)
                aviso = _selar_se_pedido(con, "rc_atos", r["ato_id"], "RCPN")
                cob_msg = _cobrar_se_pedido(con, "rc_atos", r["ato_id"], tipo)
        except (RC.RcError, AS.AtoError) as erro:
            flash(str(erro), "danger")
            return voltar
        # O SELO SAI AGORA, com o ato já lavrado — e fora da transação dele.
        recado_do_selo = _selar_o_ato(
            "rc_atos", r["ato_id"], tipo, "RCPN", aviso,
            especie=_especie_do_assento(assento_id))
        aviso = (recado_do_selo or "") + cob_msg
        motivo_selo = _motivo_da_falha_do_selo(recado_do_selo)
        if motivo_selo:
            with db.transaction() as con:
                banco(con).escrever("DELETE FROM rc_atos WHERE id=%s", (r["ato_id"],))
            audit("RCPN_ATO_NAO_LAVRADO_SELO_FALHOU", "rc_atos",
                  r["ato_id"], {"tipo": tipo, "assento_id": assento_id,
                                "motivo": motivo_selo})
            flash("Ato NÃO lançado: o selo não saiu. "
                  f"Motivo: {motivo_selo} "
                  "Corrija o problema do selo e lance de novo.",
                  "danger")
            return voltar
        with db.transaction() as con:
            RCETQ.sincronizar_teor_do_ato(con, r["ato_id"])
        audit("RCPN_ATO", "rc_atos", r["ato_id"], {"tipo": tipo})
        flash(f"{tipo.capitalize()} lançada no assento.{aviso}", "success")
        return voltar

    def _rcpn_tela_lancamento(assento_id: int, tipo: str):
        """A tela de um único tipo de lançamento. Só LÊ até o envio."""
        with db.connect() as con:
            assento = banco(con).um(
                "SELECT * FROM rc_assentos WHERE id=%s", (assento_id,)
            )
            if not assento:
                flash("Assento não encontrado.", "danger")
                return redirect(url_for("rcpn_assentos"))
            receita = _receitas_de(con, "rc_atos", (tipo,)).get(tipo)
            caixa = _caixa_aberto(con)
            protocolos = _protocolos_abertos(con)
        if assento["situacao"] != "ATIVO":
            flash("Só é possível lançar ato em assento ativo.", "danger")
            return redirect(url_for("rcpn_assento", assento_id=assento_id))
        import custas as CU
        return render_template(
            "atrib_rcpn_lancamento_novo.html", assento=dict(assento),
            tipo=tipo,
            rotulos={"AVERBACAO": "Averbação", "ANOTACAO": "Anotação",
                     "RETIFICACAO": "Retificação"},
            receita=receita, caixa=caixa, protocolos=protocolos,
            gratuidades=CU.GRATUIDADES_POR_PESSOA,
            naturezas_averbacao=AS.NATUREZAS_AVERBACAO_CIVIL)

    @app.route("/rcpn/<int:assento_id>/averbar")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_averbar(assento_id: int):
        return _rcpn_tela_lancamento(assento_id, "AVERBACAO")

    @app.route("/rcpn/<int:assento_id>/averbar-cpf", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_averbar_cpf(assento_id: int):
        """Averba o CPF no assento (art. 347) — sempre gratuito. ESCREVE.

        Um POST só: valida o dígito, lança a averbação em `rc_atos`, grava o
        documento da pessoa certa, cobra zero com `ART_347_CPF` e sela com
        `isentoGratuito`.

        NO CASAMENTO SÃO DOIS CLIQUES, UM PARA CADA NUBENTE — pedido do
        oficial em 09/09/2026: *"o sistema só tem a opção de averbar 1 CPF
        (...) o texto precisa dizer qual cpf se refere a cada cônjuge"*.
        `papel` (`NUBENTE1`/`NUBENTE2`) diz de quem é esta averbação; sem ele
        — nascimento, óbito, um principal só — o CPF vai para
        `cpf_registrado`, como sempre foi. Com ele, vai só para a pessoa: a
        coluna do assento não tem onde pôr um segundo número.
        """
        voltar = redirect(url_for("rcpn_assento", assento_id=assento_id))
        cpf = _campo("cpf")
        papel = _campo("papel").strip().upper() or None
        try:
            especie = _especie_do_assento(assento_id)
            principais = dict(CPFRC.PRINCIPAIS_DA_ESPECIE.get(
                str(especie or "").strip().upper(), ()))
            nome = rotulo = None
            if papel:
                rotulo = principais.get(papel)
                if rotulo is None:
                    raise CPFRC.CpfError(
                        f"«{papel}» não é um dos principais deste assento "
                        f"({especie or 'espécie desconhecida'}).")
                with db.connect() as con:
                    linha = banco(con).um(
                        """SELECT nome FROM rc_pessoas
                            WHERE assento_id=%s AND UPPER(COALESCE(papel,''))=%s
                            ORDER BY id LIMIT 1""",
                        (assento_id, papel))
                nome = (linha["nome"] if linha else "") or None
            teor = CPFRC.texto_averbacao(cpf, nome=nome, papel_rotulo=rotulo)
            g.rcpn_gratuidade_override = {
                "codigo": "ART_347_CPF",
                "motivo": (_campo("motivo_gratuidade")
                           or "ART. 347 DO CODIGO DE NORMAS DO TJMA "
                              "— AVERBACAO DE CPF"),
            }
            with db.transaction() as con:
                cpf_formatado = CPFRC.formatar(cpf)
                ja = banco(con).um(
                    """SELECT id, COALESCE(selo,'') selo
                         FROM rc_atos
                        WHERE assento_id=%s AND tipo='AVERBACAO'
                          AND teor ILIKE %s
                        ORDER BY id DESC LIMIT 1""",
                    (assento_id, f"%CPF n. {cpf_formatado}%"))
                if ja:
                    aviso_selo = (f", selo {ja['selo']}" if ja["selo"] else
                                  ", ainda sem selo")
                    raise CPFRC.CpfError(
                        f"Este CPF já foi averbado neste assento "
                        f"(averbação {ja['id']}{aviso_selo}).")
                r = RC.averbar(con, assento_id, teor=teor, agora=agora(),
                               fundamento="art. 347 do Código de Normas do TJMA",
                               usuario=usuario_nome())
                if papel:
                    formatado = CPFRC.gravar_na_pessoa(con, assento_id, cpf,
                                                       papel=papel)
                else:
                    formatado = CPFRC.gravar(con, assento_id, cpf)
                    CPFRC.gravar_no_registrado(con, assento_id, cpf)
                aviso = _selar_se_pedido(con, "rc_atos", r["ato_id"], "RCPN")
                # ATO GRATUITO LANCA COM ZERO: se ha caixa e o item 14.4.1
                # resolve, lanca - mesmo sem o operador marcar cobranca.
                # cob_msg fica FORA de ja_dito: _selar_o_ato trata ja_dito
                # nao-vazio como "selo ja dito" e nao compra AVERBA.
                cob_msg = ""
                caixa = _caixa_aberto(con)
                servico_cpf = AS.servico_do_codigo_tj(con, "14.4.1")
                if caixa and servico_cpf:
                    cob = AS.cobrar(
                        con, tabela="rc_atos", ato_id=r["ato_id"],
                        servico=int(servico_cpf["codigo"]), agora=agora(),
                        hoje=hoje(), hora=agora()[11:16],
                        caixa_id=int(caixa["id"]),
                        descricao="AVERBACAO CPF - art. 347",
                        gratuidade_codigo="ART_347_CPF",
                        motivo_gratuidade=g.rcpn_gratuidade_override["motivo"],
                        usuario_id=None)
                    from caixa_schema import reais
                    cob_msg = (f" Lancado no caixa (gratuito): "
                               f"R$ {reais(cob['total_centavos'])}.")
                else:
                    cob_msg = _cobrar_se_pedido(con, "rc_atos", r["ato_id"],
                                               "AVERBACAO")
        except (RC.RcError, CPFRC.CpfError, AS.AtoError) as erro:
            flash(str(erro), "danger")
            return voltar
        aviso_selo = _selar_o_ato("rc_atos", r["ato_id"], "AVERBACAO", "RCPN", aviso,
                             especie=_especie_do_assento(assento_id))
        aviso = (aviso_selo or "") + cob_msg
        motivo_selo = _motivo_da_falha_do_selo(aviso_selo)
        if motivo_selo:
            with db.transaction() as con:
                bd = banco(con)
                bd.escrever("DELETE FROM rc_atos WHERE id=%s", (r["ato_id"],))
                if papel:
                    bd.escrever(
                        """UPDATE rc_pessoas
                              SET documento_tipo=NULL, documento_numero=NULL
                            WHERE assento_id=%s
                              AND UPPER(COALESCE(papel,''))=%s
                              AND documento_tipo='CPF'
                              AND documento_numero=%s""",
                        (assento_id, papel, "".join(
                            c for c in str(cpf or "") if c.isdigit())))
                else:
                    bd.escrever(
                        """UPDATE rc_assentos
                              SET cpf_registrado=NULL
                            WHERE id=%s AND cpf_registrado=%s""",
                        (assento_id, "".join(
                            c for c in str(cpf or "") if c.isdigit())))
                    bd.escrever(
                        """UPDATE rc_pessoas
                              SET documento_tipo=NULL, documento_numero=NULL
                            WHERE assento_id=%s
                              AND UPPER(COALESCE(papel,''))='REGISTRADO'
                              AND documento_tipo='CPF'
                              AND documento_numero=%s""",
                        (assento_id, "".join(
                            c for c in str(cpf or "") if c.isdigit())))
            audit("RCPN_AVERBAR_CPF_NAO_LAVRADA_SELO_FALHOU", "rc_atos",
                  r["ato_id"], {"cpf": formatado, "papel": papel,
                                "gratuito": True, "motivo": motivo_selo})
            flash("Averbação de CPF NÃO lançada: o selo não saiu. "
                  f"Motivo: {motivo_selo}. Corrija o problema do "
                  "selo e tente de novo.",
                  "danger")
            return voltar
        with db.transaction() as con:
            RCETQ.sincronizar_teor_do_ato(con, r["ato_id"])
        audit("RCPN_AVERBAR_CPF", "rc_atos", r["ato_id"],
              {"cpf": formatado, "papel": papel, "gratuito": True})
        de_quem = f" ({rotulo}{f', {nome}' if nome else ''})" if papel else ""
        flash(f"CPF {formatado} averbado gratuitamente (art. 347){de_quem}."
              f"{aviso}", "success")
        return voltar



    # HOTFIX-2026-10-09-05 - SELAR NOVAMENTE a averbacao cujo selo foi
    # cancelado no Portal do Selo (pedido da Debora, 09/10/2026). Reusa o
    # MESMO `_selar_o_ato` do lancamento; a unica diferenca e `reselagem`, que
    # muda o SID (referencia `...:R<n>`): com o SID antigo o selador devolveria
    # o selo CANCELADO em vez de vender um novo. Nao cobra de novo.
    @app.context_processor
    def _gratuidades_para_selar_novamente():
        import custas as CU
        return {"gratuidades_selar_novamente": tuple(
            g_ for g_ in CU.GRATUIDADES_POR_PESSOA
            if g_.get("codigo") != "ART_347_CPF"),
            "naturezas_selar_novamente": AS.NATUREZAS_AVERBACAO_CIVIL}

    @app.route("/rcpn/averbacao/<int:ato_id>/selar-novamente", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_averbacao_selar_novamente(ato_id: int):
        """Sela de novo uma averbacao SEM selo cujo selo anterior foi cancelado. ESCREVE."""
        with db.connect() as con:
            bd = banco(con)
            ato = bd.um("SELECT * FROM rc_atos WHERE id=%s", (ato_id,))
            if not ato:
                abort(404)
            assento_id = int(ato["assento_id"])
            voltar = redirect(url_for("rcpn_assento", assento_id=assento_id))
            situacao = bd.um("SELECT situacao FROM rc_assentos WHERE id=%s",
                             (assento_id,))
            vivos = [r["numero"] for r in bd.ler(
                """SELECT numero FROM sd_selos WHERE tabela='rc_atos' AND ato_id=%s
                      AND cancelado_em IS NULL ORDER BY id""", (ato_id,))]
            cancelados = int(bd.valor(
                """SELECT COUNT(*) AS n FROM sd_selos WHERE tabela='rc_atos' AND ato_id=%s
                      AND cancelado_em IS NOT NULL""", (ato_id,)))
        if str(ato["tipo"] or "").upper() != "AVERBACAO":
            flash("«Selar novamente» é só para averbação.", "danger")
            return voltar
        if str(ato["selo"] or "").strip():
            flash(f"Esta averbação já tem selo ({ato['selo']}).", "danger")
            return voltar
        if situacao and str(situacao["situacao"] or "").upper() == "CANCELADO":
            flash("Assento cancelado: não se sela averbação nele.", "danger")
            return voltar
        if vivos:
            flash("Há selo NÃO cancelado ligado a esta averbação "
                  f"({', '.join(vivos)}). Registre o cancelamento antes.", "danger")
            return voltar
        teor = str(ato["teor"] or "")
        eh_cpf = (" ".join(teor.split()).lower().startswith("averbo neste assento o cpf")
                  or "347" in str(ato["fundamento"] or ""))
        if eh_cpf:
            # A MESMA ISENCAO do botao de CPF (rcpn_averbar_cpf).
            g.rcpn_gratuidade_override = {
                "codigo": "ART_347_CPF",
                "motivo": (_campo("motivo_gratuidade")
                           or "ART. 347 DO CODIGO DE NORMAS DO TJMA "
                              "- AVERBACAO DE CPF"),
            }
        recado = _selar_o_ato("rc_atos", ato_id, "AVERBACAO", "RCPN", "",
                              especie=_especie_do_assento(assento_id),
                              reselagem=cancelados)
        motivo_selo = _motivo_da_falha_do_selo(recado)
        if motivo_selo:
            audit("RCPN_AVERBACAO_SELAR_NOVAMENTE_FALHOU", "rc_atos", ato_id,
                  {"motivo": motivo_selo, "reselagem": cancelados})
            flash(f"O selo não saiu: {motivo_selo} A averbação continua sem selo; "
                  "corrija e clique de novo.", "danger")
            return voltar
        with db.transaction() as con:
            RCETQ.sincronizar_teor_do_ato(con, ato_id)
            novo = banco(con).um("SELECT selo FROM rc_atos WHERE id=%s", (ato_id,))
        audit("RCPN_AVERBACAO_SELAR_NOVAMENTE", "rc_atos", ato_id,
              {"selo": novo["selo"] if novo else None, "reselagem": cancelados,
               "cpf_art_347": eh_cpf})
        flash(f"Averbação selada novamente.{recado or ''}", "success")
        return voltar

    @app.route("/rcpn/ato/<int:ato_id>/etiqueta", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_ato_etiqueta(ato_id: int):
        """ODT da etiqueta de averbação — para colar na margem do livro.

        Baixa o arquivo editável (LibreOffice). Medidas em
        etiqueta.AVERBACAO_RCPN / tela de ajuste.

        POST COM O TOKEN (M8 do LS01, lote LX11). Era GET, e GET que grava
        não passa pelo CSRF da casa: o `SameSite=Lax` manda o cookie em link
        vindo de fora, e bastava um link ou `<img>` com o id para gravar em
        nome de quem estivesse logado. O botão da tela manda o formulário. Aqui a gravação
        é o teor da averbação, sincronizado com o próprio ato.
        """
        with db.transaction() as con:
            try:
                RCETQ.sincronizar_teor_do_ato(con, ato_id)
                dados = RCETQ.dados_da_etiqueta(con, ato_id, sv=sv())
            except LookupError:
                abort(404)
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_assentos"))
        medidas = ETQ.medidas(db.get_settings, ETQ.AVERBACAO_RCPN)
        odt = RCETQ.arquivo_odt(dados, medidas)
        nome = RCETQ.nome_arquivo(dados)
        audit("RCPN_ETIQUETA_ODT", "rc_atos", ato_id,
              {"selo": dados.get("selo"), "lavrou": dados.get("lavrou")})
        return send_file(
            io.BytesIO(odt),
            mimetype="application/vnd.oasis.opendocument.text",
            as_attachment=True,
            download_name=nome)

    @app.route("/rcpn/etiqueta-averbacao/ajuste", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_etiqueta_averbacao_ajuste():
        """Acertar largura/altura/margem da etiqueta de averbação do livro.

        Independente da firma e do RTD: a faixa do livro é mais justa.
        """
        configuracao = ETQ.AVERBACAO_RCPN
        padrao = ETQ.padrao_gravado(configuracao)
        if request.method == "POST":
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
                    return redirect(url_for("rcpn_etiqueta_averbacao_ajuste"))
                novo[chave] = bruto
            if not novo:
                flash("Nenhuma medida foi enviada.", "warning")
                return redirect(url_for("rcpn_etiqueta_averbacao_ajuste"))
            db.set_settings(novo)
            audit("RCPN_ETIQUETA_AJUSTADA", None, None, novo)
            flash("Medidas da etiqueta de averbação guardadas.", "success")
            return redirect(url_for("rcpn_etiqueta_averbacao_ajuste"))
        return render_template(
            "rcpn_etiqueta_averbacao_ajuste.html",
            m=ETQ.medidas(db.get_settings, configuracao),
            padrao=ETQ.PADROES[configuracao],
            chave=lambda medida: ETQ.chave_gravada(configuracao, medida),
            nome=ETQ.NOME_DA_CONFIGURACAO[configuracao])

    @app.route("/rcpn/<int:assento_id>/anotar")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_anotar(assento_id: int):
        return _rcpn_tela_lancamento(assento_id, "ANOTACAO")

    @app.route("/rcpn/<int:assento_id>/retificar")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_retificar(assento_id: int):
        return _rcpn_tela_lancamento(assento_id, "RETIFICACAO")

    # ------------------------- o termo de paternidade (23/10/2026)

    @app.route("/rcpn/<int:assento_id>/paternidade/termo")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def rcpn_paternidade_termo(assento_id: int):
        """O termo de alegação (ou negativo) em .odt, para a mãe e o oficial
        assinarem e a serventia arquivar. O texto é o que foi gravado na
        lavratura — não se remonta."""
        import rc_paternidade as RP
        from ri_odt import gerar_odt, html_para_odf
        with db.connect() as con:
            termo = RP.do_assento(con, assento_id)
        if not termo:
            flash("Este assento não tem termo de paternidade.", "warning")
            return redirect(url_for("rcpn_assento", assento_id=assento_id))
        if not termo["tem_termo"]:
            # A MÃE NÃO COMPARECEU (27/10/2026): não há termo para ninguém
            # assinar — só a anotação, que já está na ficha.
            flash("Neste assento a mãe não compareceu: não há termo de "
                  "paternidade para imprimir. A anotação está na ficha.",
                  "warning")
            return redirect(url_for("rcpn_assento", assento_id=assento_id))
        from markupsafe import escape as esc
        s = sv()
        html = (f'<p align="center"><b>{esc(s.get("unit_name", ""))}</b></p>'
                f'<p align="center">CNS {esc(s.get("ri_cns", ""))}</p><p></p>'
                f'<p>{esc(termo["teor"])}</p><p></p><p></p>'
                f'<p align="center">_________________________________</p>'
                f'<p align="center">{esc(termo.get("mae_nome") or "a declarante")}</p>'
                f'<p></p><p align="center">_________________________________</p>'
                f'<p align="center">{esc(s.get("serventia_titular", ""))}</p>'
                f'<p align="center">{esc(s.get("serventia_titulo", ""))}</p>')
        arquivo = gerar_odt(html_para_odf(html), titulo=termo["nome_do_tipo"])
        audit("RCPN_TERMO_PATERNIDADE_IMPRESSO", "rc_termos_paternidade",
              termo["id"], {"assento_id": assento_id, "tipo": termo["tipo"]})
        return Response(arquivo,
                        mimetype="application/vnd.oasis.opendocument.text",
                        headers={"Content-Disposition":
                                 f'attachment; filename="termo-paternidade-{assento_id}.odt"'})

    @app.route("/rcpn/<int:assento_id>/paternidade/remessa", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_paternidade_remessa(assento_id: int):
        """Grava a remessa do termo de alegação ao juiz (PJe). ESCREVE."""
        import rc_paternidade as RP
        try:
            with db.transaction() as con:
                r = RP.registrar_remessa(
                    con, assento_id, processo=_campo("remessa_processo"),
                    data=_campo("remessa_data"), agora=agora(),
                    usuario=usuario_nome())
        except RP.PaternidadeError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_assento", assento_id=assento_id))
        audit("RCPN_TERMO_PATERNIDADE_REMETIDO", "rc_termos_paternidade", None,
              {"assento_id": assento_id, "processo": r["processo"],
               "remetido_em": r["remetido_em"]})
        flash(f"Remessa ao juiz registrada: processo {r['processo']}, em "
              f"{r['remetido_em']}.", "success")
        return redirect(url_for("rcpn_assento", assento_id=assento_id))

    @app.route("/rcpn/<int:assento_id>")
    @login_required
    def rcpn_assento(assento_id: int):
        """A ficha do assento, com a divisão tripartite em blocos próprios."""
        with db.connect() as con:
            assento = banco(con).um("SELECT * FROM rc_assentos WHERE id=%s",
                                    (assento_id,))
            if not assento:
                flash("Assento não encontrado.", "danger")
                return redirect(url_for("rcpn_assentos"))
            atos = banco(con).ler(
                "SELECT * FROM rc_atos WHERE assento_id=%s ORDER BY id",
                (assento_id,))
            for a in atos:
                a["lavrou"] = RCETQ.nome_de_quem_lavrou(con, a.get("criado_por"))
                # FICHA_FOLHA_SEGURANCA_20261009: a folha de seguranca baixada
                # no REGISTRO (a que foi ao TJMA no `papelMoeda`). A linha «Folha»
                # do quadro do assento e a folha do LIVRO - outra coisa.
                a["folhas_seguranca"] = (
                    PP.do_ato(con, "rc_atos", a["id"])
                    if a.get("tipo") == "REGISTRO" else [])
            receitas = _receitas_de(con, "rc_atos",
                                    ("AVERBACAO", "ANOTACAO", "RETIFICACAO"))
            caixa = _caixa_aberto(con)
            cobrancas = _cobrancas_de(con, "rc_atos", atos)
            protocolos = _protocolos_abertos(con)
            pessoas = RCE.pessoas(con, assento_id)
            # QUEM AINDA PRECISA DA AVERBAÇÃO DO CPF (art. 347) — pedido do
            # oficial em 09/09/2026: no casamento são OS DOIS nubentes, cada
            # um com o seu botão; no nascimento e no óbito continua sendo um
            # só, exatamente como sempre foi.
            cpf_pendentes = CPFRC.quem_falta_cpf(
                pessoas, assento["especie"],
                cpf_registrado=assento["cpf_registrado"])
            certidoes = RCE.do_assento(con, assento_id)
            anexos_termo = [dict(r) for r in db.get_attachments(
                RCT.ANEXO_DO_TERMO, assento_id)]
            # OS DOCUMENTOS DO REGISTRO (12/10/2026): os da leitura e os que já
            # estavam guardados como `rc_assento` — 5 na produção, e nenhuma
            # tela os mostrava.
            anexos_registro = [dict(r) for r in db.get_attachments("rc_assento", assento_id)]
            # OS PAIS E OS AVOS ENTRAM NA CONFERENCIA DE FRAUDE, e isso e novo
            # desde 26/08/2026. Antes eu escrevi aqui que os demais nomes
            # moravam em `dados_json` e entrariam "quando a tela pedisse" —
            # eles nunca estiveram la: estavam no acervo, em `tbFiliacao` e
            # `tbProgenitor`, e a carga nao os abria.
            #
            # E nome de MAE e exatamente o tipo de nome que aparece numa
            # comunicacao de fraude: registro de nascimento falso se faz com a
            # filiacao de outra pessoa.
            fraudes = _fraudes_de(con, [
                {"nome": assento["nome"], "papel_no_ato": "registrado"},
                *({"nome": x["nome"],
                   "papel_no_ato": x["papel"].replace("_", " ").lower()}
                  for x in pessoas),
            ])
            # A FOLHA DE SEGURANÇA PASSOU A SER ESCOLHIDA NA TELA — pedido do
            # oficial em 08/09/2026: a sugerida automaticamente (a menor em
            # branco) às vezes não é a que está fisicamente na gaveta, e a
            # certidão saía com o papel errado. `proxima_folha` continua
            # sendo a sugestão (pré-selecionada, para o caso comum), mas quem
            # emite pode trocar por qualquer outra em branco do estoque.
            #
            # `limite=None`: SEM ISSO O TETO PADRÃO DE 200 ESCONDIA FOLHA —
            # achado em 09/09/2026, com a folha 7225441 (em branco de
            # verdade) na posição 285 de 344, fora da lista que o escrevente
            # via. Escolha livre não pode ter teto: a folha que falta é
            # exatamente a que a pessoa tem na mão.
            folhas_disponiveis = PP.listar(con, situacao="EM BRANCO", limite=None)
            folha_sugerida_pp = PP.proxima_folha(con)
            # FOLHA_DA_1A_VIA_20261009: na 1a via a folha nao se escolhe - e a
            # do registro, que ja foi ao TJMA no `papelMoeda`. A ficha a mostra
            # travada em vez de pedir uma EM BRANCO.
            folha_da_1a_via = _folha_da_1a_via(con, assento_id,
                                               assento["especie"])
            habilitacao_vinculo = HAB.habilitacao_relacionada_ao_assento(
                con, assento_id)
            import rc_paternidade as RP
            termo_paternidade = RP.do_assento(con, assento_id)
        # Os tres blocos que a inspecao cobra, cada um no seu lugar.
        blocos = {t: [a for a in atos if a["tipo"] == t]
                  for t in ("REGISTRO", "AVERBACAO", "ANOTACAO", "RETIFICACAO")}
        dados = json.loads(assento["dados_json"] or "{}")
        # **COMO A CERTIDAO VAI SER SELADA, ANTES DE EMITIR** — correcao de
        # 10/09/2026, do relato do oficial: «na ultima o selo que era pra ser
        # gratuito foi pago». A tela ia para segunda via calada.
        with db.connect() as _con_sel:
            selagem = RCE.como_vai_selar(_con_sel, int(assento["id"]),
                                         especie=assento["especie"])
        return render_template("atrib_rcpn_ficha.html", assento=dict(assento),
                               habilitacao_vinculo=habilitacao_vinculo,
                               termo_paternidade=termo_paternidade,
                               SITUACOES=HC.SITUACOES,
                               selagem=selagem,
                               blocos=blocos, dados=dados, receitas=receitas,
                               caixa=caixa, cobrancas=cobrancas,
                               protocolos=protocolos, fraudes=fraudes,
                               pessoas=pessoas, certidoes=certidoes,
                               cpf_pendentes=cpf_pendentes,
                               anexos_termo=anexos_termo,
                               anexos_registro=anexos_registro,
                               papeis_da_filiacao=RCE.PAPEIS_DA_FILIACAO,
                               # O ROTULO DE CADA PAPEL, para a ficha não
                               # mostrar a chave do banco. `AVO_PATERNO` virava
                               # «Avo paterno» — sem acento e com o vocabulário
                               # que o E-Ofício não usa.
                               rotulo_do_papel=RC.ROTULO_DO_PAPEL,
                               papeis_dos_avos=RCE.PAPEIS_DOS_AVOS,
                               folhas_disponiveis=folhas_disponiveis,
                               folha_sugerida=(folha_sugerida_pp["codigo"]
                                              if folha_sugerida_pp else None),
                               folha_da_1a_via=folha_da_1a_via,
            gratuidades=_gratuidades_da_certidao())

    def _tardio_sugerido(especie) -> str:
        """O próximo número de requerimento de registro tardio do ano. SÓ LÊ.

        É SUGESTÃO, e não reserva: o requerimento é autuado em papel (art. 249,
        I), e a tela só preenche o campo com o número seguinte ao maior que a
        casa já gravou neste ano — quem autua confere e corrige.
        """
        if especie != "NASCIMENTO":
            return ""
        ano = hoje()[:4]
        maior = 0
        try:
            with db.connect() as con:
                for linha in banco(con).ler(
                        "SELECT tardio_requerimento FROM rc_assentos "
                        "WHERE tardio_requerimento IS NOT NULL ORDER BY id"):
                    texto = str(linha["tardio_requerimento"] or "").strip()
                    numero, _, de = texto.partition("/")
                    if de.strip() == ano and numero.strip().isdigit():
                        maior = max(maior, int(numero))
        except sqlite3.OperationalError:
            return ""
        return f"{maior + 1}/{ano}"

    def _rcpn_form_da_ficha(assento, pessoas, folha=None) -> dict:
        """Monta o dict do formulario de edicao a partir do assento e das pessoas."""
        form = {
            "nome": assento["nome"] or "",
            "data_ato": (assento["data_ato"] or "")[:10],
            "data_fato": (assento["data_fato"] or "")[:10],
            "matricula": assento["matricula"] or "",
            "livro_volume": assento["livro_volume"] or "",
            "numero": "" if assento["numero"] is None else str(assento["numero"]),
            "folha": "" if folha is None else str(folha),
            "teor": assento["teor"] or "",
            "cor_raca": assento["cor_raca"] or "",
            "hora_fato": assento["hora_fato"] or "",
            "local_fato_nome": assento["local_fato_nome"] or "",
            "local_fato_endereco": assento["local_fato_endereco"] or "",
            # O MUNICÍPIO DO LOCAL (LD01): sem ele aqui, a correção da ficha
            # mandaria o campo vazio e apagaria o que a lavratura gravou.
            "local_fato_municipio": assento.get("local_fato_municipio") or "",
            "naturalidade_declarada": assento["naturalidade_declarada"] or "",
            "causa_morte": assento["causa_morte"] or "",
            "atestante": assento["atestante"] or "",
            "atestante_documento": assento["atestante_documento"] or "",
            "local_sepultamento": assento["local_sepultamento"] or "",
            "testamento": assento["testamento"] or "",
            "ibge_local": ("" if assento.get("ibge_local_nascimento") is None
                           else str(assento.get("ibge_local_nascimento"))),
            "regime_bens": assento.get("regime_bens") or "",
            # O QUE A LEI PEDE (13/10/2026) e o LIVRO E — sem isto a tela de
            # corrigir abriria vazia e, ao salvar, apagaria o que foi lavrado.
            **{c: assento.get(c) or "" for c in RC.CAMPOS_DA_LEI},
            # AS QUATRO MARCAS DO ÓBITO (relato #131, 14/10/2026): a tela de
            # corrigir não as tinha, e a carga da CRC recusa o óbito sem
            # «deixou bens». Elas vêm do assento para a caixa já marcada.
            **{c: MARCA.normalizar(assento.get(c)) for c in MARCA.CHAVES},
        }
        try:
            dados = json.loads(assento["dados_json"] or "{}")
        except (TypeError, ValueError):
            dados = {}
        if isinstance(dados, dict) and dados.get("sexo"):
            form["sexo"] = dados["sexo"]
        # O PAPEL QUE TEM DUAS GAVETAS (as testemunhas) — termo 1214,
        # 23/10/2026: as duas caíam na gaveta `testemunha`, a segunda por cima
        # da primeira, e a gaveta `testemunha2` abria vazia. A n-ésima pessoa
        # do papel vai para a n-ésima gaveta, na ordem em que foram gravadas
        # — a mesma que `RC.corrigir_informacoes` usa para gravar de volta.
        vistas: dict[str, int] = {}
        for p in pessoas or []:
            papel = (p.get("papel") or "").strip().upper()
            if papel not in RC.PREFIXO_DO_PAPEL:
                continue
            gavetas = RC.prefixos_do_papel(papel, assento["especie"])
            n = vistas.get(papel, 0)
            vistas[papel] = n + 1
            if n >= len(gavetas):
                continue
            prefixo = gavetas[n]
            for c in RC.CAMPOS_DA_PESSOA:
                valor = p.get(c)
                if valor not in (None, ""):
                    form[f"{prefixo}_{c}"] = valor
        return form

    @app.route("/rcpn/<int:assento_id>/editar", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_assento_editar(assento_id: int):
        """Corrige campos da ficha do assento (acervo / EOFICIO e demais).

        NAO e a retificacao do art. 109 (`/rcpn/<id>/retificar`). Grava
        direto em `rc_assentos` / `rc_pessoas` / folha do ato REGISTRO, com
        motivo e auditoria. `criado_por` do assento nao muda.
        """
        volta = url_for("rcpn_assento", assento_id=assento_id)

        def carregar():
            with db.connect() as con:
                assento = banco(con).um(
                    "SELECT * FROM rc_assentos WHERE id=%s", (assento_id,)
                )
                if not assento:
                    return None, None, None
                pessoas = [dict(x) for x in RC.pessoas_do_assento(con, assento_id)]
                ato = banco(con).um(
                    "SELECT folha, rotulo FROM rc_atos WHERE assento_id=%s AND "
                    "tipo='REGISTRO' ORDER BY id LIMIT 1",
                    (assento_id,))
                folha = ato["folha"] if ato else None
                if folha is None:
                    # Acervo sem ato REGISTRO: folha mora em dados_json ou na matrícula.
                    try:
                        dj = json.loads(assento["dados_json"] or "{}")
                    except (TypeError, ValueError):
                        dj = {}
                    if isinstance(dj, dict) and str(dj.get("folha") or "").strip():
                        folha = dj.get("folha")
                    elif assento["matricula"]:
                        try:
                            p = MAT.partes(assento["matricula"])
                            if str(p.get("folha") or "").strip():
                                folha = int(p["folha"])
                        except MAT.MatriculaError:
                            pass
                if ato and ato["rotulo"] and folha is not None:
                    # Preferir rótulo (ex.: 102V) no formulário quando existir.
                    try:
                        if str(ato["rotulo"]).strip().upper() != str(int(folha)):
                            folha = ato["rotulo"]
                    except (TypeError, ValueError):
                        folha = ato["rotulo"]
            return dict(assento), pessoas, folha

        assento, pessoas, folha = carregar()
        if not assento:
            flash("Assento não encontrado.", "danger")
            return redirect(url_for("rcpn_assentos"))
        if assento["situacao"] != "ATIVO":
            flash("Só é possível editar informações em assento ativo.", "danger")
            return redirect(volta)

        especie = assento["especie"]
        campos_termo = RC.CAMPOS_DO_TERMO_POR_ESPECIE.get(especie, ())

        def tela(form=None):
            # O QUE AINDA FALTA PARA A CRC E O SIRC (relato #130, 14/10/2026):
            # só AVISO — a correção não trava por isso —, com as mesmas réguas
            # da carga, para o balcão completar os assentos antigos.
            import rc_centrais_na_lavratura as CENT
            with db.connect() as con_c:
                faltas_centrais = CENT.o_que_falta(con_c, assento_id)
            return render_template(
                "atrib_rcpn_editar.html",
                assento=assento,
                faltas_centrais=faltas_centrais,
                nome_da_central=CENT.NOME_DA_CENTRAL,
                form=form or _rcpn_form_da_ficha(assento, pessoas, folha),
                cores=RC.CORES_E_RACAS,
                campos_termo=campos_termo,
                locais=(IBGE.LOCAL_DO_NASCIMENTO
                        if especie == "NASCIMENTO" else {}),
                regimes=HC.REGIMES,
                titulos_livro_e=RC.TITULOS_DO_LIVRO_E.get(especie, ()),
                nomes_do_titulo=RC.NOME_DO_TITULO,
                marcas_do_obito=(MARCA.MARCAS if especie == MARCA.ESPECIE
                                 else ()),
            )

        if request.method != "POST":
            return tela()

        form_post = {k: (request.form.get(k) or "") for k in request.form}
        # «ONDE NASCEU» (06/10/2026): o SIRC recusa o nascimento sem o local,
        # e a ficha não tinha onde informá-lo depois de lavrado. Mora em
        # `anotar_para_o_ibge`, que confere o código contra o catálogo; vazio
        # não apaga o que já está gravado.
        local_novo = _campo("ibge_local") if especie == "NASCIMENTO" else ""
        mudou_local = bool(local_novo) and str(local_novo) != str(
            assento.get("ibge_local_nascimento") or "")
        # AS MARCAS DO ÓBITO (relato #131) gravam pela MESMA função da tela
        # «óbitos por perguntar» — vazio não apaga resposta já dada.
        marcas_novas = ({c: request.form.get(c, "") for c in MARCA.CHAVES
                         if c in request.form}
                        if especie == MARCA.ESPECIE else {})
        mudou_marcas = any(
            MARCA.normalizar(v)
            and MARCA.normalizar(v) != MARCA.normalizar(assento.get(c))
            for c, v in marcas_novas.items())
        try:
            with db.transaction() as con:
              try:
                r = RC.corrigir_informacoes(
                    con, assento_id,
                    motivo=_campo("motivo"),
                    agora=agora(),
                    usuario=usuario_nome(),
                    nome=_campo("nome"),
                    data_ato=_campo("data_ato") or "",
                    data_fato=_campo("data_fato") or "",
                    matricula=_campo("matricula") or "",
                    teor=request.form.get("teor"),
                    livro_volume=_campo("livro_volume") or "",
                    numero=_campo("numero") or "",
                    folha=_campo("folha") or "",
                    sexo=_campo("sexo") or "",
                    # O REGIME só existe no casamento e na união estável; nas
                    # demais espécies o campo não vem, e None é «não mexer».
                    regime_bens=(_campo("regime_bens") or ""
                                 if "regime_bens" in request.form else None),
                    termo={
                        k: (_campo(k) or "")
                        for k in campos_termo
                    },
                    pessoas=_pessoas_do_formulario(especie),
                )
              except RC.RcError as erro:
                # Só o local ou as marcas mudaram: «Nada foi alterado» é dos
                # outros campos.
                if not ((mudou_local or mudou_marcas)
                        and str(erro).startswith("Nada foi alterado")):
                    raise
                if not _campo("motivo").strip():
                    raise
                r = {"motivo": _campo("motivo").strip(),
                     "origem": assento.get("origem"), "campos": [],
                     "usuario": usuario_nome()}
              if mudou_local:
                RC.anotar_para_o_ibge(con, assento_id, especie=especie,
                                      local_nascimento=local_novo)
                r["campos"] = [*r["campos"], "local do nascimento"]
              if marcas_novas:
                rm = MARCA.responder(con, assento_id, marcas_novas)
                r["campos"] = [*r["campos"],
                               *(MARCA.marca(c)["rotulo"] for c in rm["mudou"])]
        except RC.RcError as erro:
            flash(str(erro), "danger")
            form_post["motivo"] = _campo("motivo")
            return tela(form_post)

        audit("RCPN_ASSENTO_CORRIGIDO", "rc_assentos", assento_id, {
            "motivo": r["motivo"],
            "origem": r["origem"],
            "campos": r["campos"],
            "usuario": r["usuario"],
        })
        flash(
            f"Informações corrigidas ({', '.join(r['campos'])}). "
            f"Motivo: {r['motivo']}",
            "success")
        return redirect(volta)

    # ------------------------------------------ o TERMO do livro
    #
    # O QUE ESTE BLOCO FECHA
    #     Este sistema construiu a CERTIDAO do RCPN e nunca o TERMO — o texto
    #     que vai escrito no livro. A explicacao registrada era que «os 244
    #     assentos do acervo nao tem teor nenhum»; em 29/08/2026 se descobriu
    #     que o E-Oficio **montava o teor do modelo na hora de imprimir**, e os
    #     treze modelos dele estao no acervo.
    #
    #     A tela vem junto do modulo, e nao depois: seis vezes neste projeto uma
    #     funcao de dominio ficou pronta e testada sem tela, e o buraco so
    #     apareceu meses depois no balcao.

    def _servent() -> dict:
        """A serventia como o termo precisa dela.

        Quem assina no termo e quem esta logado (nome completo + funcao).
        Pedido do oficial 09/09/2026: antes saia a substituta (ri_substituta)
        em vez de quem lavrou. escrevente/funcao ficam na frente em
        rc_termo._quem_assina. registrador/titulo continuam a regra viva
        da casa (substituta ou titular) para os demais papeis.
        """
        s = dados_serventia(db.get_settings)
        substituta = (db.get_setting("ri_substituta", "") or "").strip()
        return {
            "nome": s["serventia_titular"],
            "cidade": s["ri_cidade"], "uf": s["ri_uf"],
            "estado": s.get("ri_estado") or "Maranhão",
            "registrador": substituta or s["serventia_titular"],
            "titulo": ("Tabeliã Registradora Substituta" if substituta
                       else s["serventia_titulo"]),
            # Nome completo de quem esta na tela (users.full_name).
            "escrevente": usuario_nome(),
            "funcao": usuario_funcao(),
        }

    def _teor_do_nascimento(teor, especie: str, origem: str, con=None):
        """CPF e «primeiro registro» DENTRO do teor do nascimento novo. So calcula.

        Pedido do oficial 09/10/2026 («adicionar o CPF sem averbacao e o
        primeiro registro»). So o nascimento lavrado no balcao (origem MANUAL),
        so na lavratura: teor ja gravado nao muda. CPF invalido nao entra (o
        passo do CPF, depois, continua avisando). As duas frases sao pecas do
        termo (LF06C): com `con`, saem da busca unica.
        """
        if not teor or str(especie or "").upper() != "NASCIMENTO" \
                or origem != "MANUAL":
            return teor
        cpf = (_campo("cpf_registrado") or "").strip()
        if cpf and not CPFRC.valido(cpf):
            cpf = ""
        return MODLIVRO.completar_teor_nascimento(
            teor, cpf=CPFRC.formatar(cpf) if cpf else "",
            sexo=_campo("pessoa_sexo") or "", con=con)

    def _teor_com_quem_assina(con, teor: str, especie: str) -> str | None:
        """O teor digitado, com quem assina no lugar do traço. SÓ CALCULA.

        **RELATO #63 DO OFICIAL, 15/09/2026.** A lavratura grava o teor que o
        escrevente **digita**, e o texto do modelo nunca passa por `montar` — o
        balcão abre a tela com a frase do livro já escrita e o traço onde não
        sabe o que pôr. Os dois claros da assinatura saíam da máquina como
        traço, e o Livro ficava sem o nome de quem assinou:

            «...o(a) declarante assina. Eu, ____________, Oficial, dou fé e
             assino.»

        Medido em 15/09/2026, e a primeira leitura era enganosa: **625 dos
        1.181 assentos com teor** têm doze underscores seguidos — mas **624
        deles são texto do acervo**, e ali o traço é a linha de assinatura de
        **vinte e dois** underscores («Em testemunho da verdade.
        ______________________»), onde quem assina é a mão. Os doze da casa
        **cabem dentro** daqueles vinte e dois, e por isso o `LIKE` primeiro
        devolveu os 1.181.

        **O caso desta casa é UM**: o assento **8.266**, nascimento lavrado em
        15/09/2026 às 13h00, com «Eu, ____________, Oficial, dou fé e assino.»
        É o defeito exato do relato — e a medida certa é essa, e não «o estrago
        do tamanho do livro», que foi o que eu quase escrevi aqui.

        **E É MELHOR CONSERTAR DO QUE EXIGIR.** Quem assina não é campo de
        decisão do balcão: é a **regra viva de quem responde pela serventia**,
        a mesma do cartão de assinatura e da certidão do RI. O relato #65 diz o
        mesmo pelo outro lado — «não faz sentido escolher quem assinou».

        Quem faz a troca é `rc_termo.completar_quem_assina`, que acha o lugar
        pelo **corpo do modelo** e não no palpite: procurar só o traço trocaria
        o primeiro do papel, que pode ser de outro campo.
        """
        texto = (teor or "").strip()
        if not texto:
            return None
        r = RCT.completar_quem_assina(con, texto, especie=especie,
                                      serventia=_servent())
        if r.get("nao_achei") or (
                not r["mudou"]
                and "não sei quem assina" in str(r.get("motivo") or "")):
            # **NÃO É ERRO, E SAI NA TELA ASSIM MESMO.** O balcão pode colar um
            #   texto próprio, e aí não há traço a trocar — mas quando o motivo
            #   é não saber quem assina, ou o traço estar onde o modelo não
            #   manda, isso é alguém indo para o Livro sem o nome de quem
            #   assinou: o #63 outra vez. Avisar é o que impede a troca que não
            #   achou o lugar de passar calada — `str.replace` sem achar não
            #   estoura.
            #
            # **E O AVISO NÃO PODE EXIGIR QUE NADA TENHA SIDO TROCADO.** A
            #   primeira versão só avisava com `nao_achei` **e** `mudou` falso —
            #   e o caso pior é o meio: dois claros, um trocado e o outro não.
            #   Metade da assinatura no Livro, e a tela calada. Quem sabe que o
            #   traço ficou é o `nao_achei`, e é ele que manda avisar.
            flash("O termo vai ser gravado SEM o nome de quem assina — "
                  "informe quem responde pela serventia.", "warning")
        return r["texto"]

    # ============== a conferencia dos tres termos, para a tela do catalogo
    #
    # **OS TERMOS DO CIVIL NAO SAO JINJA, e a tela geral confere em Jinja.**
    # Sem este conferidor ela reprovaria os tres — e o oficial perderia a edicao
    # justamente dos papeis mais importantes do Registro Civil, que e o relato
    # #28 desfeito pela metade.
    #
    # `""` quer dizer «conferi, esta bom»; a frase quer dizer «esta errado, e e
    # isto». Nunca devolve `None`: aqui sempre ha com que conferir, porque a
    # lista de campos do termo vem do proprio modulo e nao do banco.
    def _conferir_termo_do_civil(corpo: str, _chave: str = ""):
        import rc_modelos_do_livro as LIVRO
        return LIVRO.conferir_corpo(_chave.replace("RC_TERMO_", ""), corpo)

    app.extensions.setdefault("conferidores_de_modelo", {})
    for _ch in ("RC_TERMO_NASCIMENTO", "RC_TERMO_CASAMENTO", "RC_TERMO_OBITO"):
        app.extensions["conferidores_de_modelo"][_ch] = (
            lambda corpo, _c=_ch: _conferir_termo_do_civil(corpo, _c))

    # **OS PAPÉIS DO CIVIL QUE SAÍRAM DO CÓDIGO NO LF06C** (edital, certidões,
    # comunicações, ofício à FUNAI…) também são de chave simples, e a régua é a
    # mesma ideia: o ajuste só usa os claros que o padrão daquele papel usa.
    # Sem isto um `{nome_do_pai}` inventado passaria na tela e estouraria na
    # hora de emitir — ver `rc_textos.conferir_claros`.
    for _ch in TEXTOS.CLAROS_FECHADOS:
        app.extensions["conferidores_de_modelo"][_ch] = (
            lambda corpo, _c=_ch: TEXTOS.conferir_claros(_c, corpo))

    @app.route("/rcpn/assentos/<int:assento_id>/termo")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_termo(assento_id: int):
        """Mostra o termo — o que já está escrito, ou como ele ficaria.

        SÓ LÊ. Ver como fica é barato e se pode fazer quantas vezes quiser;
        escrever acontece uma vez, e depois o texto não muda mais.

        **PÁGINA EM BRANCO É DEFEITO** — relato #38, 31/08/2026. O E-Ofício
        não guardava o teor; a carga deixou a coluna vazia; a tela que só lia
        o gravado saía sem o ato. A prévia monta dos campos pelo catálogo da
        casa, nas três espécies.

        **MOSTRAR NÃO É GRAVAR.** O importado não congela só porque a prévia
        abriu; gravar é POST em `escrever`, com confirmação. Ato novo continua
        `congelar` uma vez.
        """
        with db.connect() as con:
            a = banco(con).um("SELECT * FROM rc_assentos WHERE id=%s",
                              (assento_id,))
            if not a:
                flash("Assento não encontrado.", "danger")
                return redirect(url_for("rcpn_assentos"))
            a = dict(a)
            visto = RCT.texto_para_mostrar(con, assento_id, serventia=_servent())
            escrito = visto["texto"] if visto["congelado"] else ""
            previa = visto["texto"] if not visto["congelado"] else ""
            erro = visto["erro"]
            do_acervo = visto["do_acervo"]
            anexos = [dict(x) for x in
                      db.get_attachments(RCT.ANEXO_DO_TERMO, assento_id)]
        return render_template("rcpn_termo.html", a=a, escrito=escrito,
                               previa=previa, erro=erro, do_acervo=do_acervo,
                               pediu_gerar=True, anexos=anexos, norma=RCT)

    @app.route("/rcpn/assentos/<int:assento_id>/termo/escrever",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_termo_escrever(assento_id: int):
        """Escreve o termo no assento. UMA VEZ SÓ.

        O termo é o papel que o declarante lê e assina; reescrevê-lo faria o
        livro de hoje discordar do papel assinado ontem. Corrigir é **averbar ao
        lado**, que é o que a lei manda e o que a ficha já oferece.
        """
        try:
            with db.transaction() as con:
                RCT.congelar(con, assento_id, serventia=_servent(),
                             agora=db.now(),
                             livro=(request.form.get("livro") or "").strip(),
                             folha=(request.form.get("folha") or "").strip())
        except RCT.TermoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_termo", assento_id=assento_id))
        audit("RCPN_TERMO_ESCRITO", "rc_assentos", assento_id, None)
        flash("Termo escrito no assento. Ele não se reescreve — para corrigir, "
              "averbe ao lado.", "success")
        return redirect(url_for("rcpn_termo", assento_id=assento_id))

    def _etiqueta_do_registro_rcpn(con, assento_id: int) -> str:
        """Etiqueta inteira (sd_selos.texto) do selo VIGENTE do REGISTRO. SO LE.

        HOTFIX-2026-10-08 (carimbo RCPN). A fonte e o NUMERO gravado em
        `rc_atos.selo` — o selo vigente do ato. `etiqueta_do_ato` por
        tabela+ato_id devolve TODOS os selos ja obtidos para o ato (medido no
        assento 8298: re-selagem, dois REGNAS), e o carimbo sairia duplo.
        Casamento com habilitacao daqui: o selo e o HABCAS da habilitacao
        (item 14.1.1, um selo so), achado aqui pelo numero.
        Sem etiqueta no razao, devolve o numero sozinho (carimbo sem valores).
        """
        import re as _re
        r = banco(con).um(
            """SELECT id, selo FROM rc_atos WHERE assento_id=%s
                 AND tipo='REGISTRO' AND coalesce(selo,'')<>''
               ORDER BY id DESC LIMIT 1""", (assento_id,))
        if not r:
            return ""
        codigos = list(dict.fromkeys(
            _re.findall(r"[A-Z]{6}[0-9A-Z]{22}", str(r["selo"] or "").upper())))
        if not codigos:
            codigos = [str(r["selo"]).strip()]
        fora = []
        for cod in codigos:
            linha = banco(con).um(
                """SELECT texto FROM sd_selos WHERE numero=%s
                     AND cancelado_em IS NULL
                   ORDER BY id DESC LIMIT 1""", (cod,))
            fora.append(str((linha["texto"] if linha else "") or "").strip()
                        or cod)
        return "\n".join(x for x in fora if x)

    def _sem_selo_corrido(texto: str, etiqueta: str) -> str:
        """Tira «Selo: XXXXXX.» do texto corrido (so na IMPRESSAO). SO CALCULA.

        O teor congelado nao muda; o selo passa a sair no carimbo.
        """
        import re as _re
        if not texto:
            return texto
        numeros = set(_re.findall(r"[A-Z]{6}[0-9A-Z]{22}", etiqueta or ""))
        def _tira(m):
            return "" if (not numeros or m.group(1) in numeros) else m.group(0)
        return _re.sub(r"\s*Selo:\s*([A-Z]{6}[0-9A-Z]{22})\.?", _tira,
                       texto).rstrip()

    @app.route("/rcpn/assentos/<int:assento_id>/termo.odt")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_termo_odt(assento_id: int):
        """O termo em `.odt`, para colar no livro de papel.

        TERMO QUE SO EXISTE NO BANCO NAO SERVE — e a mesma razao pela qual os
        termos de abertura e encerramento do nucleo saem em arquivo.
        """
        with db.connect() as con:
            a = banco(con).um("SELECT * FROM rc_assentos WHERE id=%s",
                              (assento_id,))
            if not a:
                abort(404)
            html = (a["teor"] or "").strip()
            if not html:
                try:
                    html = RCT.montar(con, assento_id, serventia=_servent())
                except RCT.TermoError as erro:
                    flash(str(erro), "danger")
                    return redirect(url_for("rcpn_termo",
                                            assento_id=assento_id))
            # SELO EM CARIMBO (QR + numero + emolumentos), como RI/Notas/RTD.
            # O texto do termo NAO leva o selo; o carimbo e desenhado no papel.
            etiqueta = _etiqueta_do_registro_rcpn(con, assento_id)
        imagens: dict = {}
        corpo_odf = html_para_odf(_sem_selo_corrido(html, etiqueta))
        if etiqueta:
            corpo_odf += RODT.carimbo_compacto_odf(
                etiqueta, rotulo="SELO DIGITAL DO TJMA", imagens=imagens,
                prefixo_qr=f"qr-rcpn-{assento_id}")
        arquivo = gerar_odt(corpo_odf, titulo=f"Termo {a['numero']}",
                            imagens=imagens or None)
        audit("RCPN_TERMO_ODT", "rc_assentos", assento_id, None)
        return Response(
            arquivo,
            mimetype="application/vnd.oasis.opendocument.text",
            headers={"Content-Disposition":
                     f'attachment; filename="termo-{a["numero"]}.odt"'})

    @app.route("/rcpn/informacoes-importadas")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def rcpn_informacoes_importadas():
        """Os 244 assentos que vieram do E-Ofício. **NÃO é lista de trabalho.**

        ESTA TELA FALTAVA, E A FALTA ERA MINHA. Em 30/08/2026 o oficial mandou
        corrigir os termos importados, eu tirei os 244 da lista «Termos a
        escrever» — certíssimo — e lhe disse que eles passavam a ter «lista
        própria». Escrevi a função e não construí a tela: os 244 sumiram da
        vista em vez de mudar de lugar.

        **Tirar de uma lista não é o mesmo que dar um lugar.** O assento
        importado continua existindo, continua servindo à certidão, e alguém
        precisa poder olhar para ele.
        """
        with db.connect() as con:
            linhas = RCT.informacoes_importadas(con)
            quadro = RCT.quantos_termos_faltam(con)
        return render_template("rcpn_informacoes_importadas.html",
                               linhas=linhas, quadro=quadro)


    @app.route("/rcpn/importar-acervo", methods=["GET", "POST"])
    # ABERTA AO USER POR ORDEM DELE (11/10/2026, «manter abertas»). A revisão
    # de segurança de 22/10/2026 (M12) quis fechá-la a quem gere — o
    # acervo-fonte trocado por um USER não tem volta —, e voltou atrás no mesmo
    # dia ao achar a ordem: fica declarado no relatório, e não consertado.
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_importar_acervo():
        """Submódulo RCPN: carregar o acervo (arquivo) e importar assentos.

        Duas metades, na ordem do balcão:

          (A) arquivo → monta/atualiza `acervo_eoficio.sqlite3`
              (ZIP da exportação JSONL, SQLite pronto, ou pasta no disco);
          (B) prévia + confirmação → `carregar_rcpn` / `carregar_tudo(quais=['rcpn'])`,
              com origem=EOFICIO e origem_chave idempotente.

        Conferir e importar são botões distintos — o mesmo molde de
        `importar_padrao` e da carga Admin: aqui não há como desfazer, porque
        acervo importado vira o livro.
        """
        from storage import save_upload

        previa = None
        resultado = None
        carga_acervo = None
        caminho = acervo_no_disco()
        tem_acervo = caminho.exists()
        erro_acervo = None

        if request.method == "POST":
            o_que = (request.form.get("o_que") or "").strip()
            try:
                if o_que == "carregar_arquivo":
                    # (A) arquivo → acervo no disco
                    enviado = request.files.get("arquivo")
                    pasta = (request.form.get("pasta") or "").strip()
                    trabalho = Path(app.config["DATA_DIR"]) / "tmp_acervo_rcpn"
                    if enviado and enviado.filename:
                        info = save_upload(
                            enviado,
                            Path(app.config["DATA_DIR"]) / "uploads_acervo")
                        nome = (info.get("original_name") or "").lower()
                        guardado = Path(info["stored_path"])
                        if nome.endswith(".zip"):
                            carga_acervo = AC.instalar_acervo_de_zip(
                                guardado, caminho, trabalho)
                        elif nome.endswith((".sqlite3", ".db", ".sqlite")):
                            carga_acervo = AC.instalar_acervo_de_sqlite(
                                guardado, caminho)
                        else:
                            raise AC.CargaError(
                                "Envie um .zip da exportação do E-Ofício "
                                "(os .jsonl) ou um acervo .sqlite3. "
                                "Outro formato não entra por aqui — para "
                                "JSON de outro sistema use «Importar de "
                                "outro sistema».")
                        audit("RCPN_ACERVO_ARQUIVO", "ACERVO", None, {
                            "arquivo": info.get("original_name"),
                            "sha256": info.get("sha256"),
                            "tabelas": carga_acervo.get("tabelas"),
                            "linhas": carga_acervo.get("linhas"),
                        })
                        flash(
                            "Acervo carregado a partir do arquivo. Confira a "
                            "prévia abaixo antes de importar os assentos.",
                            "success")
                    elif pasta:
                        # SÓ PASTA DA CASA (LS02 A3; LX12, 19/10/2026): o que
                        # entra aqui SUBSTITUI o acervo de onde saem as cargas
                        # do RCPN, e `\\maquina\x` levava o servidor à rede.
                        try:
                            p = app.extensions["pasta_da_casa"](pasta)
                        except PDC.ForaDaCasa as recusa:
                            raise AC.CargaError(str(recusa)) from recusa
                        if p.is_file() and p.suffix.lower() in (
                                ".sqlite3", ".db", ".sqlite"):
                            carga_acervo = AC.instalar_acervo_de_sqlite(
                                p, caminho)
                        elif p.is_dir():
                            carga_acervo = AC.instalar_acervo_de_pasta(
                                p, caminho)
                        else:
                            raise AC.CargaError(
                                f"Não achei pasta de exportação nem SQLite "
                                f"em {pasta}.")
                        audit("RCPN_ACERVO_PASTA", "ACERVO", None, {
                            "pasta": pasta,
                            "tabelas": carga_acervo.get("tabelas"),
                            "linhas": carga_acervo.get("linhas"),
                        })
                        flash(
                            "Acervo carregado. Confira a prévia abaixo antes "
                            "de importar os assentos.", "success")
                    else:
                        raise AC.CargaError(
                            "Escolha um arquivo (.zip ou .sqlite3) ou informe "
                            "o caminho da pasta da exportação.")
                    tem_acervo = caminho.exists()

                elif o_que == "conferir":
                    # (B) prévia — não grava
                    if not caminho.exists():
                        raise AC.CargaError(
                            "O acervo ainda não está no lugar. Carregue o "
                            "arquivo da exportação primeiro.")
                    acervo = AC.abrir_acervo(caminho)
                    try:
                        with db.connect() as con:
                            previa = AC.previa_rcpn(con, acervo)
                    finally:
                        acervo.close()

                elif o_que == "importar":
                    # (B) grava — idempotente por origem_chave
                    if not caminho.exists():
                        raise AC.CargaError(
                            "O acervo ainda não está no lugar. Carregue o "
                            "arquivo da exportação primeiro.")
                    acervo = AC.abrir_acervo(caminho)
                    try:
                        with db.transaction() as con:
                            resultado = AC.carregar_tudo(
                                con, acervo, agora=agora(),
                                quais=["rcpn"])
                    finally:
                        acervo.close()
                    audit("RCPN_ACERVO_CARGA", "ACERVO", None, resultado)
                    entraram = (resultado.get("rcpn") or {}).get(
                        "inseridos", 0)
                    flash(
                        f"Importação do RCPN concluída: {entraram} "
                        f"assento(s) novo(s). O que já estava (mesma "
                        f"origem_chave) não entrou de novo.", "success")
                else:
                    flash("Não reconheci a ação pedida.", "danger")
            except AC.CargaError as erro:
                flash(str(erro), "danger")
                erro_acervo = str(erro)
            except FileNotFoundError as erro:
                flash(str(erro), "danger")
                erro_acervo = str(erro)
            except OSError as erro:
                flash(f"Não consegui ler o arquivo: {erro}", "danger")
                erro_acervo = str(erro)

        # Prévia automática no GET (e após carregar arquivo), se o acervo
        # existir — human in the loop: ver antes de gravar.
        if previa is None and tem_acervo and resultado is None:
            try:
                acervo = AC.abrir_acervo(caminho)
                try:
                    with db.connect() as con:
                        previa = AC.previa_rcpn(con, acervo)
                finally:
                    acervo.close()
            except AC.CargaError as erro:
                erro_acervo = str(erro)

        return render_template(
            "rcpn_importar_acervo.html",
            tem_acervo=tem_acervo,
            caminho_acervo=str(caminho),
            previa=previa,
            resultado=resultado,
            carga_acervo=carga_acervo,
            erro_acervo=erro_acervo,
            especies_padrao="RCPN_ASSENTO",
        )


    # ------------------- O RASCUNHO DE QUALQUER TELA — relato #36
    #
    #   «em todos os atos do cartório, durante o preenchimento, é preciso ter
    #    um campo para salvar o progresso e continuar depois»
    #
    #   AS ROTAS SÃO GENÉRICAS, e é isso que faz o mecanismo servir aos seis
    #   formulários da casa em vez de um: elas não sabem o que é assento,
    #   escritura ou protocolo — guardam o que foi digitado e devolvem.

    @app.route("/rascunhos")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rascunhos():
        """O que ficou salvo pela metade, de qualquer tela. SÓ LÊ.

        **FALTAVA "ABRIR" — relato do oficial em 09/09/2026**, achado ao
        salvar um rascunho e não conseguir voltar a ele. A rota continua
        genérica (não sabe o que é assento ou escritura); o que ela faz é
        perguntar ao Flask se `tela` vira endereço, sem inventar parâmetro
        nenhum — é por isso que só `rascunho_id` vai na URL, e cada tela de
        destino decide o resto (a de assento novo, por exemplo, ainda
        escolhe a espécie a partir do que o rascunho guardou).
        """
        tela = (request.args.get("tela") or "").strip()
        with db.connect() as con:
            linhas = RASC.listar(con, tela=tela)
            velhos = {v["id"]: v["dias_parado"]
                      for v in RASC.expirados(con, hoje())}
        for r in linhas:
            r["dias_parado"] = velhos.get(r["id"])
            try:
                r["abrir_url"] = url_for(r["tela"], rascunho_id=r["id"])
            except Exception:
                # Tela que não existe mais, ou que não aceita reabertura por
                # aqui — a linha continua na lista (e apagável), só sem link.
                r["abrir_url"] = None
        return render_template("rascunhos.html", linhas=linhas, tela=tela,
                               dias=RASC.DIAS_ATE_ENVELHECER)

    @app.route("/rascunhos/salvar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rascunho_salvar():
        """Guarda o preenchimento de uma tela. ESCREVE.

        **NÃO EXIGE O FORMULÁRIO VÁLIDO**, e é a razão de existir: o cliente
        foi buscar um documento, e o escrevente precisa parar no meio.
        """
        tela = (request.form.get("_tela") or "").strip()
        volta = destino_interno((request.form.get("_volta") or "").strip(), "")
        rid = request.form.get("_rascunho_id")
        dados = {k: v for k, v in request.form.items()
                 if not k.startswith("_")}
        try:
            with db.transaction() as con:
                r = RASC.salvar(
                    con, tela=tela, dados=dados,
                    titulo=(request.form.get("_titulo") or "").strip()
                    or (dados.get("nome") or tela),
                    chave=(request.form.get("_chave") or "").strip(),
                    agora=agora(), por=usuario_nome(),
                    rascunho_id=int(rid) if rid else None)
        except ValueError as erro:
            flash(str(erro), "danger")
            return redirect(volta or url_for("rascunhos"))
        flash("Rascunho guardado. Ele **não é ato**: não tomou número nem "
              "reservou nada — está em Rascunhos, para você continuar quando "
              "puder.", "success")
        # A conferência dos dados do RCPN (11/10/2026): o que a lavratura vai
        # recusar, dito agora, enquanto ainda é rascunho.
        travas = [p for p in r.get("conferencia") or [] if p["gravidade"] == "BLOQUEIA"]
        if travas:
            flash("A lavratura vai recusar este rascunho como está: "
                  + " ".join(p["mensagem"] for p in travas), "danger")
        return redirect(url_for("rascunhos"))

    @app.route("/rascunhos/<int:rascunho_id>/apagar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rascunho_apagar(rascunho_id: int):
        """Joga o rascunho fora. ESCREVE. **Não pede motivo** — ele nunca foi
        ato, não tomou número e não está em corrente nenhuma."""
        with db.transaction() as con:
            RASC.apagar(con, rascunho_id)
        flash("Rascunho apagado.", "info")
        return redirect(url_for("rascunhos"))

    @app.route("/rcpn/cpf", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_cpf():
        """O CPF no registro de nascimento. **A inscrição é obrigatória.**

        IN RFB nº 1.548/2015, art. 3º, V: quem é registrado em ofício de
        registro civil está obrigado a inscrever-se no CPF **no momento da
        lavratura do assento**. O manual da ARPEN é explícito: «não é um ato
        discricionário dos usuários e sim obrigatório».

        O SISTEMA AINDA NÃO PEDE O CPF À RECEITA, e a tela diz por quê — falta
        o **Termo de Adesão da RFB**, que o oficial assina na CRC Nacional com
        certificado digital, e sem o qual **nenhum** dos três caminhos
        funciona, nem o formulário manual deles.

        O que a tela faz hoje: mostra quem está sem CPF, diz o que falta em
        cada assento para o pedido, e **grava o número conferido** quando ele
        vier — pelo formulário da CRC, por um posto da Receita, por onde for.
        """
        if request.method == "POST":
            # o que não é número é o assento 0, o de ninguém: a recusa de
            # `gravar` (LD13 — «abc» era a tela de erro)
            assento_id = numero_digitado(request.form.get("assento_id")) or 0
            try:
                with db.transaction() as con:
                    formatado = CPFRC.gravar(con, assento_id,
                                             request.form.get("cpf"))
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_cpf"))
            audit("RCPN_CPF", "rc_assentos", assento_id, None)
            flash(f"CPF {formatado} gravado no assento.", "success")
            return redirect(url_for("rcpn_cpf"))

        with db.connect() as con:
            linhas = CPFRC.assentos_sem_cpf(con)
            for a in linhas:
                pessoas = banco(con).ler(
                    "SELECT * FROM rc_pessoas WHERE assento_id=%s ORDER BY id",
                    (a["id"],))
                a["falta"] = CPFRC.o_que_falta_para_pedir(a, pessoas)
                # OS DADOS PRONTOS PARA COPIAR no formulário da CRC — para que
                # o escrevente não precise voltar ao assento campo a campo, e
                # para que nada disto viaje pela URL.
                # O LIVRO E A FOLHA SAO DO ATO, e a tela da CRC os pede.
                a["copiar"] = CPFRC.dados_para_copiar(
                    a, pessoas, lugar=RCE.lugar_do_assento(con, a["id"]))
        return render_template("rcpn_cpf.html", linhas=linhas, norma=CPFRC)

    @app.route("/rcpn/filiacao")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def rcpn_filiacao():
        """Conferência da filiação dos assentos. **SÓ LÊ.**

        DESCOBERTA EM 30/08/2026 POR ACIDENTE: montando o termo de referência
        de um assento real, o texto saiu «filho de VITÓRIA … e BRUNO …» — e o
        declarante era BRUNO. O assento tem `PAI` = VITÓRIA, sexo F, e `MAE` =
        BRUNO, sexo M. Não foi o termo que errou; foi o dado que veio trocado
        da carga do acervo.

        A TELA MOSTRA E NÃO CORRIGE, e é decisão: certidão desses assentos
        pode já ter saído com a filiação invertida, e os dados foram para a
        CRC. A correção de assento lavrado é **retificação** (art. 352), e
        quem a decide é o oficial.
        """
        with db.connect() as con:
            trocadas = FILI.filiacao_trocada(con)
            mesmo_sexo = FILI.duas_filiacoes_do_mesmo_sexo(con)
            faltando = FILI.sem_sexo(con)
            resumo = FILI.resumo(con)
        return render_template("rcpn_filiacao.html", trocadas=trocadas,
                               mesmo_sexo=mesmo_sexo, faltando=faltando,
                               resumo=resumo, motivo=FILI.MOTIVO,
                               o_que_fazer=FILI.O_QUE_FAZER)

    @app.route("/rcpn/obitos-por-perguntar", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_marcas_do_obito():
        """As quatro perguntas do óbito que ainda não foram feitas.

        ELAS SÃO GATILHOS, E NÃO ESTATÍSTICA. Marcar «era eleitor» é o que faz
        a comunicação à Justiça Eleitoral existir; nenhuma delas se deduz do
        assento. São coisas que o declarante diz no balcão, com a família na
        frente — depois disso viram telefonema, ou não viram nada.

        A TELA SEPARA «NÃO» DE «NÃO PERGUNTEI», que é a razão de tudo isto
        existir: um assento em que ninguém perguntou nada parece, num booleano,
        um assento em que tudo foi respondido com «não».
        """
        if request.method == "POST":
            # o que não é número é o assento 0, o de ninguém (LD13)
            assento_id = numero_digitado(request.form.get("assento_id")) or 0
            # DESFAZER É AÇÃO DECLARADA, e não o silêncio de um campo que não
            # veio — é o que dá saída a quem marcou por engano sem abrir a
            # porta para um POST incompleto apagar resposta.
            desfazer = (request.form.get("desfazer") or "").strip()
            try:
                with db.transaction() as con:
                    if desfazer:
                        MARCA.apagar_resposta(con, assento_id, desfazer)
                        r = {"quantas": 0, "mudou": {desfazer: "desfeita"}}
                    else:
                        r = MARCA.responder(
                            con, assento_id,
                            {c: request.form.get(c, "") for c in MARCA.CHAVES})
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_marcas_do_obito"))
            audit("RCPN_MARCAS_OBITO", "rc_assentos", assento_id,
                  {"mudou": sorted(r["mudou"])})
            if desfazer:
                flash(f"A resposta de «{MARCA.marca(desfazer)['rotulo']}» "
                      f"voltou a ficar por perguntar.", "info")
            else:
                flash(f"Gravado: {r['quantas']} "
                      f"{'resposta' if r['quantas'] == 1 else 'respostas'}."
                      if r["quantas"] else "Nada mudou.",
                      "success" if r["quantas"] else "info")
            return redirect(url_for("rcpn_marcas_do_obito"))

        with db.connect() as con:
            linhas = MARCA.assentos_com_marca_por_perguntar(con)
            # O QUE CADA ASSENTO JÁ PASSOU A DEVER. A tela mostra isso ao lado
            # das perguntas em aberto: quem responde «sim» precisa ver, na
            # mesma tela, que acabou de criar uma obrigação com prazo.
            for a in linhas:
                a["abertas"] = MARCA.obrigacoes_abertas(a)
            eleitores = MARCA.eleitores_a_comunicar(con)
        return render_template("rcpn_marcas_do_obito.html", linhas=linhas,
                               eleitores=eleitores, marcas=MARCA.MARCAS,
                               estados=MARCA.ESTADOS)

    @app.route("/rcpn/checklist-pendente")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def rcpn_checklist_pendente():
        """Os atos que ainda não passaram pelo checklist obrigatório.

        ESTA TELA TAMBÉM FALTAVA. O checklist funcionava um a um, pela ficha do
        assento; o que não havia era o lugar que responde **«quais faltam»** —
        e sem essa pergunta a exigência não se cumpre, só se atende por acaso.

        É a exigência de **prazo zero** e prioridade **crítica** da pág. 50 do
        Relatório de Inspeção Ordinária de 12/08/2026.

        O ACERVO NÃO ENTRA: a exigência é dos atos futuros, e quem garante isso
        é a própria consulta, não esta tela.
        """
        with db.connect() as con:
            linhas = CHECK.atos_sem_checklist(con)
        return render_template("rcpn_checklist_pendente.html", linhas=linhas,
                               norma=CHECK)

    @app.route("/rcpn/matriculas", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_matriculas():
        """A matrícula de 32 dígitos: conferir o acervo, e conferir uma à mão.

        **SÓ LÊ.** Nem o varredor nem esta tela consertam matrícula: o número
        pode já ter saído em certidão e ido para a CRC e o SIRC, e trocá-lo no
        banco calaria o problema sem resolver nenhuma dessas pontas. A decisão
        é do oficial.

        A conferência à mão existe porque **32 dígitos seguidos não se conferem
        a olho** — chega matrícula de fora em requisição de segunda via, e o
        balcão precisa poder desconfiar.
        """
        conferido: dict = {}
        linhas: list[str] = []
        digitado = (request.values.get("matricula") or "").strip()
        if digitado:
            conferido = MAT.confere(digitado)
            if conferido.get("partes"):
                linhas = MAT.explicar(digitado)
        with db.connect() as con:
            erradas = MAT.matriculas_com_digito_errado(con)
            sem = MAT.quantas_sem_matricula(con)
        return render_template("rcpn_matriculas.html", erradas=erradas,
                               sem=sem, conferido=conferido, linhas=linhas,
                               digitado=digitado, campos=MAT.CAMPOS,
                               livros=MAT.TIPOS_DE_LIVRO, fonte=MAT.FONTE,
                               cns=sv().get("ri_cns"))

    @app.route("/rcpn/termos-a-escrever")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_termos_a_escrever():
        """Os assentos que ainda não têm o texto do livro.

        OS 244 DO ACERVO VAO APARECER AQUI, e a tela diz por que isso é certo:
        eles não têm o teor porque o E-Ofício não o guardava, e montá-lo agora
        seria escrever hoje um termo que foi lido e assinado há anos.
        """
        with db.connect() as con:
            faltando = RCT.assentos_sem_termo(con)
            # A CONTA SEPARA O QUE E TRABALHO DO QUE FICA SEM TERMO DE
            # PROPOSITO. Medido na producao em 30/08/2026: 244 sem termo, e os
            # 244 sao do acervo — **zero de trabalho**. A tela ja explicava isso
            # em palavras; faltava a conta dizer o mesmo.
            quadro = RCT.quantos_termos_faltam(con)
        return render_template("rcpn_termos.html", faltando=faltando,
                               quadro=quadro)

    # ------------------------------------------ as ANOTACOES devidas

    @app.route("/rcpn/anotacoes")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_anotacoes():
        """O que a casa deve anotar ou comunicar — art. 367, cinco dias.

        A LISTA VEM DO MAIS ANTIGO PARA O MAIS NOVO, ao contrário das outras
        deste sistema: aqui o que importa é o prazo, e quem está há mais tempo
        esperando é quem está mais perto de estourá-lo.
        """
        with db.connect() as con:
            devendo = ANOT.pendentes(con)
            vencidas = ANOT.fora_do_prazo(con, hoje=db.now()[:10])
        ids_vencidas = {x["id"] for x in vencidas}
        return render_template("rcpn_anotacoes.html", devendo=devendo,
                               vencidas=vencidas, ids_vencidas=ids_vencidas,
                               norma=ANOT)

    @app.route("/rcpn/anotacoes/<int:pendencia_id>/resolver", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_anotacao_resolver(pendencia_id: int):
        """Marca a anotação como feita, comunicada ou dispensada.

        A TELA NÃO REPETE A REGRA DO DOMÍNIO: ela oferece os três caminhos, e
        quem recusa é `rc_anotacao` — o protocolo obrigatório na comunicação, o
        motivo escrito na dispensa, o assento que tem de existir.
        """
        acao = (request.form.get("acao") or "").strip().upper()
        try:
            with db.transaction() as con:
                if acao == "ANOTAR":
                    ANOT.anotar_aqui(
                        con, pendencia_id,
                        assento_alvo_id=int(request.form.get("assento_alvo_id")
                                            or 0),
                        agora=db.now(), usuario=usuario_nome())
                elif acao == "COMUNICAR":
                    ANOT.comunicar(
                        con, pendencia_id,
                        canal=(request.form.get("canal") or "").strip(),
                        serventia=(request.form.get("serventia") or "").strip(),
                        protocolo=(request.form.get("protocolo") or "").strip(),
                        agora=db.now(), usuario=usuario_nome())
                elif acao == "DISPENSAR":
                    ANOT.dispensar(
                        con, pendencia_id,
                        motivo=(request.form.get("motivo") or "").strip(),
                        agora=db.now(), usuario=usuario_nome())
                else:
                    raise ANOT.AnotacaoError(
                        "Diga o que foi feito: anotada aqui, comunicada à outra "
                        "serventia, ou dispensada com motivo.")
        except (ANOT.AnotacaoError, ValueError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_anotacoes"))
        audit("RCPN_ANOTACAO", "rc_anotacoes", pendencia_id, {"acao": acao})
        flash("Anotação registrada.", "success")
        return redirect(url_for("rcpn_anotacoes"))

    @app.route("/rcpn/anotacoes/<int:pendencia_id>/oficio")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_anotacao_oficio(pendencia_id: int):
        """O texto da comunicação, com o resumo do assento que o art. 367 pede.

        O ARTIGO PEDE RESUMO, E NAO O TEOR INTEIRO — mandar o teor a outra
        serventia é espalhar a qualificação de todo mundo, que ela não precisa
        para anotar à margem.
        """
        with db.connect() as con:
            p = banco(con).um(
                """SELECT n.*, a.especie, a.numero, a.nome
                     FROM rc_anotacoes n JOIN rc_assentos a ON a.id=n.assento_id
                    WHERE n.id=%s""", (pendencia_id,))
            if not p:
                flash("Não achei essa pendência.", "warning")
                return redirect(url_for("rcpn_anotacoes"))
            resumo = ANOT.resumo_do_assento(con, int(p["assento_id"]))
        return render_template("rcpn_anotacao_oficio.html", p=dict(p),
                               resumo=resumo, sv=_servent(), norma=ANOT)

    # ----------------------- anotação a partir da CRC (entrada / prévia)
    #
    # INVERSO das anotações devidas: lá a casa LAVROU e comunica; aqui a CRC
    # JÁ MANDOU a comunicação de outra serventia, e a casa precisa do texto
    # para anotar à margem. Só prévia + copiar — art. 370 manda conferir.

    @app.route("/rcpn/anotacoes/crc", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_anotacao_crc():
        """Prévia do texto de anotação a partir do HTML da CRC. SÓ LÊ.

        NÃO GRAVA no banco e NÃO escreve na margem do assento. O art. 370 manda
        conferir a compatibilidade dos atos antes — o sistema monta o texto;
        quem cola na margem é o escrevente, depois de conferir.
        """
        sv = _servent()
        previa = None
        modelo = (request.form.get("modelo") or request.args.get("modelo")
                  or "compacto").strip().lower()
        especie = (request.form.get("especie") or request.args.get("especie")
                   or "").strip().upper()
        assinatura = (request.form.get("assinatura") or "").strip() or (
            f"{sv.get('registrador') or ''}, {sv.get('titulo') or ''}".strip(", ")
        )
        cidade = (request.form.get("cidade_destino") or "").strip() or (
            sv.get("cidade") or "")

        if request.method == "POST":
            enviado = request.files.get("arquivo")
            if not enviado or not (enviado.filename or "").strip():
                flash("Escolha o arquivo HTML das comunicações da CRC.",
                      "warning")
            else:
                nome = (enviado.filename or "").lower()
                if not nome.endswith((".html", ".htm")):
                    flash("Envie um arquivo .html ou .htm exportado da CRC.",
                          "danger")
                else:
                    bruto = enviado.read(5 * 1024 * 1024 + 1)
                    if len(bruto) > 5 * 1024 * 1024:
                        flash("O arquivo passa de 5 MB — confira se é mesmo "
                              "o HTML das comunicações.", "danger")
                    else:
                        html = None
                        for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
                            try:
                                html = bruto.decode(enc)
                                break
                            except UnicodeDecodeError:
                                continue
                        if html is None:
                            flash("Não consegui ler o texto do arquivo.",
                                  "danger")
                        else:
                            try:
                                comuns = ANOTCRC.ler_arquivo(html)
                                # O TEXTO DO MODELO E O DA CASA (LF06C): o
                                # papel e as peças dele saem da busca única, e
                                # `gerar` só monta. Ler não é gravar — a prévia
                                # continua sem escrita nenhuma.
                                with db.connect() as con:
                                    textos = {k: TEXTOS.texto(k, con) for k in
                                              ANOTCRC.CHAVES_DO_MODELO.get(modelo, ())}
                                previa = ANOTCRC.gerar(
                                    comuns, modelo,
                                    hoje=db.now()[:10],
                                    assinatura=assinatura or None,
                                    cidade_destino=cidade or None,
                                    especie=especie or None,
                                    textos=textos)
                                audit("RCPN_ANOTACAO_CRC_PREVIA",
                                      "rc_anotacoes", None,
                                      {"quantas": len(previa["itens"]),
                                       "modelo": previa["modelo"],
                                       "especie": especie or "TODAS"})
                            except ANOTCRC.AnotacaoCrcError as erro:
                                flash(str(erro), "danger")

        return render_template(
            "rcpn_anotacao_crc.html",
            previa=previa, modelos=ANOTCRC.MODELOS, modelo=modelo,
            especie=especie, assinatura=assinatura, cidade_destino=cidade,
            sv=sv, norma=ANOTCRC)

    # ------------------------------------ as COMUNICACOES MENSAIS de obito

    @app.route("/rcpn/comunicacoes")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_comunicacoes():
        """O que a casa deve comunicar — art. 226, cinco destinos, cinco dias
        úteis.

        A LISTA VEM DA COMPETENCIA MAIS ANTIGA, como as anotações: aqui o que
        importa é o prazo, e quem está há mais tempo esperando é quem está mais
        perto de estourá-lo.
        """
        with db.connect() as con:
            devendo = COM.pendentes(con)
            atrasadas = COM.meses_sem_comunicacao(con)
        return render_template("rcpn_comunicacoes.html", devendo=devendo,
                               atrasadas=atrasadas, norma=COM,
                               nomes={d["chave"]: d["nome"]
                                      for d in COM.DESTINOS})

    @app.route("/rcpn/comunicacoes/abrir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_comunicacoes_abrir():
        """Abre as cinco comunicações de um mês.

        O PRAZO VEM CALCULADO DAQUI, e não de dentro do módulo: quem conta dia
        útil é `ri_schema.soma_dias_uteis`, que conhece os feriados desta
        comarca e já serve a prenotação, o edital do usucapião e a retificação.
        """
        comp = (request.form.get("competencia") or "").strip()
        try:
            from datetime import date as _d

            from ri_schema import soma_dias_uteis
            ano, mes = int(comp[:4]), int(comp[5:7])
            primeiro = _d(ano + (mes // 12), (mes % 12) + 1, 1)
            prazo = soma_dias_uteis(primeiro, COM.PRAZO_DIAS_UTEIS).isoformat()
        except Exception:                                      # noqa: BLE001
            prazo = ""
        try:
            with db.transaction() as con:
                novas = COM.declarar_mes(con, comp, agora=db.now(),
                                         prazo_ate=prazo,
                                         usuario=usuario_nome())
        except COM.ComunicacaoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_comunicacoes"))
        audit("RCPN_COMUNICACOES_ABERTAS", "rc_comunicacoes", None,
              {"competencia": comp, "quantas": len(novas)})
        flash(f"{len(novas)} comunicação(ões) aberta(s) para {comp}."
              if novas else f"As comunicações de {comp} já estavam abertas.",
              "success" if novas else "info")
        return redirect(url_for("rcpn_comunicacoes"))

    @app.route("/rcpn/comunicacoes/<int:comunicacao_id>")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_comunicacao(comunicacao_id: int):
        """O texto da comunicação — o que já saiu, ou como ela ficaria."""
        with db.connect() as con:
            c = banco(con).um("SELECT * FROM rc_comunicacoes WHERE id=%s",
                              (comunicacao_id,))
            if not c:
                flash("Não achei essa comunicação.", "warning")
                return redirect(url_for("rcpn_comunicacoes"))
            c = dict(c)
            previa, erro = None, ""
            if not (c.get("teor") or "").strip():
                try:
                    previa = COM.montar(con, comunicacao_id,
                                        serventia=_servent())
                except COM.ComunicacaoError as e:
                    erro = str(e)
        return render_template("rcpn_comunicacao.html", c=c, previa=previa,
                               erro=erro, norma=COM,
                               d=COM.destino(c["destino"]))

    @app.route("/rcpn/comunicacoes/<int:comunicacao_id>/resolver",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_comunicacao_resolver(comunicacao_id: int):
        acao = (request.form.get("acao") or "").strip().upper()
        try:
            with db.transaction() as con:
                if acao == "ENVIADA":
                    COM.registrar_envio(
                        con, comunicacao_id,
                        canal=(request.form.get("canal") or "").strip(),
                        protocolo=(request.form.get("protocolo") or "").strip(),
                        quando=(request.form.get("quando") or db.now()[:10]),
                        agora=db.now(), serventia=_servent(),
                        usuario=usuario_nome())
                elif acao == "DISPENSAR":
                    COM.dispensar(
                        con, comunicacao_id,
                        motivo=(request.form.get("motivo") or "").strip(),
                        agora=db.now(), usuario=usuario_nome())
                else:
                    raise COM.ComunicacaoError(
                        "Diga o que foi feito: enviada com protocolo, ou "
                        "dispensada com motivo.")
        except COM.ComunicacaoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_comunicacao",
                                    comunicacao_id=comunicacao_id))
        audit("RCPN_COMUNICACAO", "rc_comunicacoes", comunicacao_id,
              {"acao": acao})
        flash("Comunicação registrada.", "success")
        return redirect(url_for("rcpn_comunicacoes"))

    # ------------------------------------------ a carga da CRC Nacional

    def _cns_rcpn() -> str:
        """O CNS desta serventia, para a CRC e o SIRC.

        A PRODUÇÃO NUNCA TEVE LINHA `serventia_cns` EM `settings` — quem
        existe é `ri_cns` (`DEFAULT_SETTINGS`, `database.py`), que já entra
        semeada com "000000". Ler só `serventia_cns` manda `<CNS></CNS>`
        vazio pro XML real, e a CRC recusa: ela exige seis dígitos
        (`xs:length value="6"`). É a mesma armadilha do CNPJ do relato #42 —
        a mesma palavra em dois lugares —, e o mesmo conserto que
        `proclamas_web.py` e `rc_pedidos_web.py` já usam.
        """
        return str(db.get_setting("serventia_cns", "") or "").strip() \
            or str(db.get_setting("ri_cns", "") or "").strip()

    @app.route("/rcpn/crc", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_crc():
        """A carga da CRC — monta o XML, diz o que ficou retido, e OFERECE
        o envio pelo web service (`/rcpn/crc/enviar`, ao lado).

        ESTA ROTA SÓ LÊ, mesmo no POST: montar o arquivo não muda nada no
        banco. Quem assina e manda é a outra — e o PIN nunca passa por aqui,
        nem por nenhuma rota que precise ser vista de novo depois.
        """
        # **`ver_enviados` — relato do oficial em 11/09/2026: "os assentos
        # não ficaram lá nas cargas, sem opção de dizer que já foram
        # enviados".** Por padrão a lista some o que já tem lote
        # registrado (`rc_crc_lotes`); o link "ver os já enviados" traz de
        # volta, para quem quiser reenviar de propósito.
        ver_enviados = request.values.get("ver_enviados") == "1"
        escolhidos, resultado = [], None
        with db.connect() as con:
            todos_ativos = CRC.pendentes_de_carga(con, incluir_ja_enviados=True)
            nao_enviados = CRC.pendentes_de_carga(con, incluir_ja_enviados=False)
            candidatos = todos_ativos if ver_enviados else nao_enviados
            quantos_ja_enviados = len(todos_ativos) - len(nao_enviados)
            # **A QUARENTENA APARECE, senão ela some do mundo.** O assento
            # retido saiu da lista de cima; sem esta segunda lista ninguém
            # saberia que ele existe nem o que falta nele — e «não está na
            # carga» seria lido como «já foi».
            retidos = CRC.em_quarentena(con)
            token_escolhidos = ""
            if request.method == "POST":
                # o que não é número não foi marcado; o id que passa do
                # `integer` não é de assento nenhum, e voltaria pelo token
                # para estourar a marca de enviado (LD13)
                escolhidos = [n for n in (numero_digitado(x, maximo=MAIOR_INTEGER)
                                          for x in request.form.getlist("assento"))
                              if n is not None]
                if escolhidos:
                    resultado = CRC.montar(
                        con, escolhidos, cns=_cns_rcpn())
                    # **O TOKEN SUBSTITUI OS MILHARES DE `<input hidden>` —
                    # relato do oficial em 13/09/2026, "monto o arquivo com
                    # todos, mas não acontece nada depois".** Repetir a
                    # lista inteira em quatro formulários (este + os três de
                    # baixo) inflava a página a ~15 MB com 6700+ assentos;
                    # o navegador parecia travado nela, e não travava por
                    # limite do Flask (medido: o POST com todos os IDs
                    # SOBE certo — o problema era a página que descia).
                    token_escolhidos = _guardar_crc_selecao(escolhidos)
                else:
                    flash("Escolha ao menos um assento.", "warning")
        # OS DRIVERS SO SE OLHAM — nunca se carregam aqui. `driver_disponivel`
        # so confere o arquivo no disco; abrir a DLL e o passo que da segfault,
        # e isso so acontece dentro do processo isolado de `crc_a3_assinador`.
        drivers = [{"nome": n, "achado": CRCA3.driver_disponivel(n) is not None}
                  for n in CRCA3.DRIVERS_CONHECIDOS]
        return render_template("rcpn_crc.html", candidatos=candidatos,
                               resultado=resultado, escolhidos=escolhidos,
                               token_escolhidos=token_escolhidos,
                               norma=CRC, drivers=drivers,
                               ambientes=(CRCSOAP.HOMOLOGACAO, CRCSOAP.PRODUCAO),
                               ver_enviados=ver_enviados,
                               quantos_ja_enviados=quantos_ja_enviados,
                               retidos=retidos)

    @app.route("/rcpn/crc/arquivo", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_crc_arquivo():
        """Baixa o XML da carga.

        O ARQUIVO SAI EM UTF-8, que e o que o manual manda. Nomeia-se com a
        data para o oficial saber, na pasta, o que ja mandou.
        """
        escolhidos = _escolhidos_do_token_crc()
        if not escolhidos:
            flash("Escolha ao menos um assento.", "warning")
            return redirect(url_for("rcpn_crc"))
        with db.connect() as con:
            r = CRC.montar(con, escolhidos, cns=_cns_rcpn())
        audit("RCPN_CRC_ARQUIVO", "rc_assentos", None,
              {"quantos": r["quantos"], "retidos": len(r["retidos"])})
        nome = f"crc-carga-{db.now()[:10]}.xml"
        return Response(
            r["xml"].encode("utf-8"), mimetype="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    @app.route("/rcpn/crc/enviar", methods=["POST"])
    # A GUARDA AGORA DIZ O QUE A DOCSTRING SEMPRE DISSE (LS02; LX12,
    # 19/10/2026): a rota aceitava USER, e o C1 do LS02 — a DLL do driver
    # carregada como SYSTEM — era alcançável pelo escrevente por isso.
    @roles_required("ADMIN", "MANAGER")
    def rcpn_crc_enviar():
        """Assina com o A3 e MANDA a carga pelo web service — de verdade.

        **O TRANSPORTE É MEDIDO POR ANALOGIA, NÃO CONFIRMADO NESTE ENDPOINT
        ESPECÍFICO** — ver o cabeçalho de `crc_soap.py`. O PIN não fica em
        lugar nenhum: passa pelo formulário, vai ao processo isolado do A3, e
        se perde com a resposta, dando certo ou não.

        **SÓ ADMIN E GERENTE**, e não USER como o resto da tela — enviar à
        Central é irreversível do lado de lá (mesmo em homologação, que só
        não valida a ASSINATURA; ela recebe o arquivo do mesmo jeito).
        """
        escolhidos = _escolhidos_do_token_crc()
        driver = str(request.form.get("driver") or "").strip()
        pin = str(request.form.get("pin") or "")
        ambiente = str(request.form.get("ambiente")
                       or CRCSOAP.HOMOLOGACAO).strip().upper()
        if not escolhidos:
            flash("Escolha ao menos um assento antes de enviar.", "warning")
            return redirect(url_for("rcpn_crc"))
        if not driver:
            flash("Escolha o driver do certificado A3.", "warning")
            return redirect(url_for("rcpn_crc"))
        # O DRIVER É UM DOS DA LISTA DA TELA, e só (LS02, 19/10/2026).
        #
        #   O nome vai para o processo do assinador, que faz `WinDLL(driver)`
        #   como o serviço — SYSTEM. Sem esta conferência, o formulário montado
        #   à mão com `\\outra-maquina\pasta\x.dll` (ou o caminho de um anexo
        #   enviado) fazia o servidor CARREGAR E RODAR a DLL de quem pediu,
        #   antes de qualquer PIN. A tela só oferece `DRIVERS_CONHECIDOS`.
        if driver not in CRCA3.DRIVERS_CONHECIDOS:
            flash("Escolha o driver do certificado A3 na lista da tela.",
                  "warning")
            return redirect(url_for("rcpn_crc"))
        try:
            with db.transaction() as con:
                resultado = CRCSOAP.enviar_carga(
                    con, escolhidos, cns=_cns_rcpn(),
                    driver=driver, pin=pin, ambiente=ambiente)
                # **REGISTRA O LOTE — relato do oficial em 11/09/2026: "os
                # assentos não ficaram lá nas cargas [...] já foram
                # enviados".** Só os que ENTRARAM de verdade — os retidos
                # não subiram, e marcá-los como enviados os esconderia da
                # lista sem eles nunca terem chegado à Central.
                retidos_ids = {r["assento_id"] for r in resultado["retidos"]}
                enviados_ids = [a for a in escolhidos if a not in retidos_ids]
                if enviados_ids:
                    CRCENVIOS.registrar_envio(
                        con, enviados_ids, agora=db.now(), por=usuario_nome(),
                        canal="WEBSERVICE", ambiente=ambiente,
                        resposta=resultado["resposta"])
        except (CRCSOAP.CrcSoapError, CRCA3.AssinaturaA3Error) as erro:
            flash(f"Não enviei: {erro}", "danger")
            return redirect(url_for("rcpn_crc"))
        audit("RCPN_CRC_ENVIO", "rc_assentos", None,
              {"enviado": resultado["enviado"], "ambiente": ambiente,
               "retidos": len(resultado["retidos"])})
        flash(f"Enviado à CRC ({ambiente.lower()}): {resultado['enviado']} "
              f"registro(s) — não vão mais aparecer na lista de pendentes. "
              f"Resposta: {resultado['resposta'][:300]}",
              "success")
        return redirect(url_for("rcpn_crc"))

    @app.route("/rcpn/crc/marcar-enviado", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_crc_marcar_enviado():
        """Marca assentos como já enviados — pelo MODELO POR UPLOAD, no
        próprio site da CRC.

        **O SISTEMA NÃO SABE SE O UPLOAD MANUAL ACONTECEU** — quem manda
        pelo modelo de upload no site da CRC sai daqui com o XML e volta
        só para dizer que deu certo. Sem este clique, a próxima vez que a
        tela abrisse mostraria os mesmos assentos de novo, porque nada
        neste sistema tinha onde guardar «isto já foi». É o "Confirmei no
        livro de papel" do núcleo, aplicado à carga da CRC.
        """
        escolhidos = _escolhidos_do_token_crc()
        nota = str(request.form.get("nota") or "").strip()
        if not escolhidos:
            flash("Escolha ao menos um assento antes de marcar.", "warning")
            return redirect(url_for("rcpn_crc"))
        with db.transaction() as con:
            CRCENVIOS.registrar_envio(con, escolhidos, agora=db.now(),
                                por=usuario_nome(), canal="MANUAL", nota=nota)
        audit("RCPN_CRC_MARCADO_ENVIADO", "rc_assentos", None,
              {"quantos": len(escolhidos)})
        flash(f"{len(escolhidos)} assento(s) marcado(s) como já enviados — "
              "não vão mais aparecer na lista de pendentes.", "success")
        return redirect(url_for("rcpn_crc"))

    @app.route("/rcpn/crc/historico")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_crc_historico():
        """O que já foi enviado à CRC, lote por lote — a resposta da
        Central inclusa, para quando alguém perguntar meses depois."""
        with db.connect() as con:
            lotes = CRCENVIOS.historico_de_envios(con)
            for lote in lotes:
                lote["assentos"] = CRCENVIOS.assentos_do_lote(con, lote["id"])
        return render_template("rcpn_crc_historico.html", lotes=lotes)

    # ------------------------------------------ o que comecou e nao terminou

    def _contexto_dos_inacabados(con, *, fonte_chave="", atribuicao="",
                                 so_parados=False):
        """O que as tres telas dos inacabados precisam. SÓ LÊ."""
        hoje = db.now()[:10]
        return {
            "resumo": INAC.resumo(con, hoje=hoje),
            "config": INAC.configuracao(con),
            "itens": INAC.lista(con, hoje=hoje, chave=fonte_chave,
                                atribuicao=atribuicao, so_parados=so_parados),
            "fonte_escolhida": INAC.fonte(fonte_chave) if fonte_chave else None,
            "atribuicao": atribuicao, "so_parados": so_parados,
            "atribuicoes": sorted({f["atribuicao"] for f in INAC.FONTES}),
        }

    @app.route("/inacabados")
    @roles_required("ADMIN", "MANAGER", "USER")
    def inacabados_lista():
        """O que comecou e nao terminou — MEDIDO NA HORA. So le.

        ATO CONCLUIDO SAI DAQUI SOZINHO, porque a lista e a pergunta e nao a
        resposta guardada. E o que impede o defeito do relato #24: a tarefa
        concluida e o expediente ainda aberto.
        """
        fonte_chave = request.args.get("fonte", "")
        if fonte_chave:
            try:
                INAC.fonte(fonte_chave)
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("inacabados_lista"))
        with db.connect() as con:
            ctx = _contexto_dos_inacabados(
                con, fonte_chave=fonte_chave,
                atribuicao=request.args.get("atribuicao", ""),
                so_parados=bool(request.args.get("so_parados")))
        return render_template("inacabados.html", **ctx)

    @app.route("/inacabados/ajustar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def inacabados_ajustar():
        """Liga, desliga e muda os dias — «moldar o que fica, o que sai».

        SO O OFICIAL E O GERENTE: e configuracao, e quem muda a regra nao pode
        ser o balcao inteiro. A tela de VER continua aberta a todos, porque quem
        precisa da lista e quem trabalha.
        """
        try:
            with db.transaction() as con:
                for f in INAC.FONTES:
                    chave = f["chave"]
                    INAC.ajustar(
                        con, chave,
                        ligada=bool(request.form.get(f"ligada_{chave}")),
                        dias=int(request.form.get(f"dias_{chave}") or f["dias"]),
                        agora=db.now(), por=usuario_nome())
        except ValueError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("inacabados_lista"))
        audit("INACABADOS_AJUSTE", "ex_fontes", None, {})
        flash("Ajuste guardado.", "success")
        return redirect(url_for("inacabados_lista"))

    @app.route("/inacabados/anotar/<tabela>/<int:item_id>",
               methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def inacabados_anotar(tabela: str, item_id: int):
        """A anotacao sobre um item — quem cuida, ate quando, o que falta.

        **NAO CONCLUI NADA.** Anotar nao e resolver: concluir e na tela do ato,
        com as regras de la.
        """
        if request.method == "POST":
            try:
                with db.transaction() as con:
                    if request.form.get("acao") == "apagar":
                        INAC.apagar_anotacao(con, tabela=tabela,
                                             item_id=item_id)
                    else:
                        INAC.anotar(con, tabela=tabela, item_id=item_id,
                                    texto=request.form.get("texto", ""),
                                    responsavel=request.form.get(
                                        "responsavel", ""),
                                    ate=request.form.get("ate", ""),
                                    agora=db.now(), por=usuario_nome())
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("inacabados_anotar", tabela=tabela,
                                        item_id=item_id))
            audit("INACABADOS_ANOTACAO", "ex_anotacoes", item_id,
                  {"tabela": tabela})
            # O PAINEL DOS PEDIDOS DO RI ANOTA POR AQUI (12/10/2026) — a mesma
            # anotação, e não uma segunda — e quem veio de lá volta para lá.
            if request.form.get("voltar") == "ri_pedidos":
                return redirect(url_for("ri_pedidos"))
            return redirect(url_for("inacabados_lista"))

        with db.connect() as con:
            atual = banco(con).um(
                "SELECT * FROM ex_anotacoes WHERE tabela=%s AND item_id=%s "
                "ORDER BY id",
                (tabela, item_id))
            item = next((x for x in INAC.lista(con, hoje=db.now()[:10],
                                               limite=100000)
                         if x["tabela"] == tabela and x["id"] == item_id), None)
        return render_template("inacabados_anotar.html", tabela=tabela,
                               item_id=item_id,
                               atual=dict(atual) if atual else None, item=item)

    # ------------------- o formulario que se monta do modelo

    @app.route("/rcpn/formulario/<chave>", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_formulario(chave: str):
        """O formulário de preenchimento de cada ato — **montado do modelo**.

        OS CAMPOS SAEM DO PROPRIO MODELO, e nao de uma lista escrita ao lado:
        duas listas divergem no primeiro conserto, e a tela passaria a perguntar
        uma coisa e o texto a esperar outra. E a licao da `normalizar_nome`,
        aplicada ao formulario.

        SO LE — «ver como fica» nao grava nada. Quem congela o termo e
        `rc_termo.congelar`, e ele o faz uma vez so.
        """
        try:
            m = MODLIVRO.modelo(chave.upper())
        except ValueError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_assentos"))
        valores = {c["nome"]: request.values.get(c["nome"], "")
                   for c in m["campos"]}
        montado, em_branco = "", []

        # QUEM ASSINA NA PRÉVIA É QUEM ASSINA NA LAVRATURA — relato #123,
        # 15/10/2026: «não puxa quem está assinando o ato, ficando lacuna para
        # preencher». O comentário do POST abaixo já dizia «quem assina sai de
        # `_servent`», e o código passava `sv()` — que não tem `escrevente`,
        # `registrador` nem `funcao`: o nome saía no traço e a função caía no
        # piso «Oficial». Agora os dois claros chegam PREENCHIDOS desde o GET,
        # com a mesma regra da lavratura (quem está na tela, nome e função do
        # cadastro), e a tela os mostra só para leitura — o relato #65 continua
        # valendo: quem assina não se escolhe no balcão.
        servent = _servent()
        quem_assina = RCT.quem_assina_da_serventia(servent)
        for nome_do_claro in MODLIVRO.QUEM_ASSINA_VEM_DE_FORA:
            valores[nome_do_claro] = quem_assina.get(nome_do_claro, "")

        # O CORPO DA PRÉVIA É O DA CASA, e não o padrão do código — o mesmo que
        # `rc_termo.montar` congela. O oficial edita o termo pelo catálogo
        # (relato #28); sem isto a prévia mostraria o texto de fábrica enquanto
        # o livro recebe o editado. Corpo que não passa na conferência não se
        # usa: a tela avisa e mostra o padrão.
        import modelos_motor_versao as VERSAO
        with db.connect() as con:
            corpo_da_casa, _origem_do_corpo = VERSAO.corpo_do_termo(
                con, "RC_TERMO_" + m["chave"])
        aviso_corpo = (MODLIVRO.conferir_corpo(m["chave"], corpo_da_casa)
                       if corpo_da_casa else "")
        if aviso_corpo:
            corpo_da_casa = None

        # CONFERIR O MODELO CONTRA UM ASSENTO REAL.
        #
        #   **AGORA É ISTO QUE VAI AO LIVRO — correção de 31/08/2026.** Até
        #   essa data este comentário dizia o contrário, e estava certo: o termo
        #   oficial saía dos treze modelos do E-Ofício. O oficial os recusou em
        #   30/08, e em 31/08 escolheu a «opção B» — `rc_termo.montar` passou a
        #   montar deste mesmo texto, e o que ele editar pelo catálogo é o que
        #   se congela no assento.
        #
        #   **Carimbo que mente é pior que carimbo nenhum**: quem lesse a frase
        #   antiga concluiria que ensaiar aqui não diz nada sobre o papel
        #   assinado — e diz tudo, porque é o mesmo texto.
        #
        #   Existe porque conferir modelo com dado inventado não confere nada:
        #   o campo que falta só aparece quando se usa um assento que a casa
        #   lavrou.
        #
        #   **NAS QUATRO ESPÉCIES, E PELA MESMA RÉGUA DA LAVRATURA** — relato
        #   #123, 15/10/2026. Até aqui só o nascimento tinha o botão, e ele
        #   chamava a ponte à mão com `data_extenso`, que ela não aceita:
        #   «Preencher com este» devolvia HTTP 500. Agora quem monta é
        #   `rc_termo.montar_para_conferir` — a mesma de `montar` —, com o
        #   corpo da casa, quem assina e, no casamento, os documentos da
        #   habilitação. As espécies saem de `MODELO_DA_ESPECIE`, e não de uma
        #   lista daqui: o natimorto confere no termo de nascimento, e as sete
        #   do Livro E no termo do Livro E.
        conferindo, aviso_conf = None, ""
        numero = (request.values.get("assento") or "").strip()
        especies_do_modelo = tuple(
            e for e, c in RCT.MODELO_DA_ESPECIE.items()
            if c == "RC_TERMO_" + m["chave"])
        if numero and especies_do_modelo:
            marcas = ", ".join("%s" for _ in especies_do_modelo)
            with db.connect() as con:
                # O NÚMERO NÃO É ÚNICO: no casamento ele reinicia a cada livro.
                # Vale o mais recente, e a tela diz quantos havia.
                achados = banco(con).ler(
                    "SELECT * FROM rc_assentos WHERE numero=%s "
                    f"AND UPPER(COALESCE(especie,'')) IN ({marcas}) "
                    "ORDER BY id DESC",
                    (numero_digitado(numero),   # LD13: 5.000 dígitos
                     *especies_do_modelo))
                if not achados:
                    aviso_conf = (f"Não achei {m['nome'].lower()} com o "
                                  f"número {numero}.")
                else:
                    a = achados[0]
                    lugar = RCE.lugar_do_assento(con, a["id"])
                    livro_conf = str(lugar.get("livro")
                                     or lugar.get("livro_numero")
                                     or a.get("livro_volume") or "")
                    try:
                        conferindo = RCT.montar_para_conferir(
                            con, a["id"], serventia=servent,
                            livro=livro_conf,
                            folha=str(lugar.get("folha") or ""))
                        conferindo["assento"] = a
                        conferindo["livro"] = livro_conf
                    except RCT.TermoError as erro:
                        aviso_conf = str(erro)
                    if len(achados) > 1:
                        aviso_conf = (
                            f"Há {len(achados)} assentos com o número "
                            f"{numero}; esta conferência usou o mais recente"
                            + (f" (livro {livro_conf})" if livro_conf else "")
                            + ". " + aviso_conf).strip()

        if request.method == "POST":
            # **A ASSINATURA DA PRÉVIA VEM DA REGRA VIVA, E NÃO DO FORMULÁRIO.**
            #   Aqui — e só aqui — os claros de quem assina são campos de texto.
            #   Deixá-los valer faria a prévia mostrar o traço na assinatura, e
            #   **foi de uma prévia assim que o traço foi copiado para o teor**
            #   do assento 8.266 — o do relato #63.
            #
            #   **E O NÚMERO MAIOR QUE ESTE COMENTÁRIO TROUXE ESTAVA ERRADO.**
            #   Procurando o traço em qualquer lugar davam 625 assentos, mas
            #   **624 deles são do acervo**, onde o traço é a linha de assinatura
            #   de vinte e dois underscores («Em testemunho da verdade.
            #   ______________________») e os doze da casa **cabem dentro** dela.
            #   Carimbo que mente com um número de verdade dentro é o que este
            #   comentário era, e quem o lesse mandaria consertar 624 livros de
            #   papel que não têm defeito. Não é escolha do balcão (relato #65):
            #   quem assina sai de `_servent` — e desde 15/10/2026 é de lá
            #   mesmo (relato #123; antes vinha de `sv()`, que não o tem).
            r = MODLIVRO.montar_do_formulario(
                m["chave"], valores, texto=corpo_da_casa,
                quem_assina=quem_assina)
            montado, em_branco = r["texto"], r["em_branco"]
        # OS OUTROS TEORES DO MESMO ATO. A tela mostra os que faltam junto com
        # o que há: uma lista só com os prontos diria que o nascimento tem um
        # teor, quando ele tem quatro e nós temos um.
        especie = m["chave"]
        try:
            tipos = MODLIVRO.tipos_do_ato(especie)
        except ValueError:
            tipos = ()
        return render_template("rcpn_formulario.html", modelo=m,
                               campos=m["campos"], valores=valores,
                               montado=montado, em_branco=em_branco,
                               tipos=tipos, tem_texto=MODLIVRO.tem_texto,
                               conta=MODLIVRO.quantos_teores_faltam(),
                               conferindo=conferindo, aviso_conf=aviso_conf,
                               numero_conf=numero,
                               faltas=MODLIVRO.conferir(m["chave"]),
                               # Relato #123: a tela ganhou saída — lavrar o
                               # ato desta espécie, ou editar o texto dele.
                               vem_de_fora=MODLIVRO.QUEM_ASSINA_VEM_DE_FORA,
                               conferivel=bool(especies_do_modelo),
                               aviso_corpo=aviso_corpo,
                               slug_novo=RCPN_SLUG_DA_ESPECIE.get(m["chave"]),
                               chave_do_catalogo="RC_TERMO_" + m["chave"])

    # ------------------- o PDF do termo de papel, para o assento importado

    @app.route("/rcpn/<int:assento_id>/termo-pdf", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_termo_pdf(assento_id: int):
        """Anexa o PDF do termo de papel ao assento.

        **ORDEM DO OFICIAL, EM 30/08/2026:** «Permitir, caso conveniente, que se
        importe o pdf do termo». Para o assento vindo do E-Oficio o termo existe
        **em papel, assinado** — e o que o sistema tem dele sao as informacoes.
        O PDF e a unica coisa que ainda pode vir do papel, e ele **nao se
        monta**: digitaliza-se.

        A TABELA E A `attachments`, que ja serve expediente, tarefa e protocolo.
        **Nao se cria a quarta** — `entity_type` e o que distingue, e uma tabela
        nova seria o mesmo dado em dois lugares.
        """
        from storage import safe_component, save_upload
        with db.connect() as con:
            assento = banco(con).um("SELECT * FROM rc_assentos WHERE id=%s",
                                    (assento_id,))
        if not assento:
            flash("Esse assento não existe.", "danger")
            return redirect(url_for("rcpn_assentos"))
        arquivo = request.files.get("arquivo")
        if not arquivo or not arquivo.filename:
            flash("Escolha o arquivo do termo digitalizado.", "danger")
            return redirect(url_for("rcpn_termo", assento_id=assento_id))
        destino = (pasta_dos_arquivos() / "RegistroCivil" / "Termos"
                   / safe_component(str(assento["serie"] or "RC")))
        info = save_upload(arquivo, destino)
        anexo = db.add_attachment(
            RCT.ANEXO_DO_TERMO, assento_id, info,
            usuario_id_do_sistema(),
            request.form.get("descricao") or "Termo digitalizado do livro")
        audit("RCPN_TERMO_PDF", "rc_assentos", assento_id,
              {"anexo": anexo, "sha256": info["sha256"]})
        flash("Termo digitalizado anexado ao assento.", "success")
        return redirect(url_for("rcpn_termo", assento_id=assento_id))

    def _assinaturas_da_folha(con, assento: dict) -> list:
        """Linhas de assinatura da folha do termo. So LE.

        Pedido do balcão, 09/10/2026 (termo 19579): depois do teor, linhas com nome e
        qualidade embaixo. Nascimento: declarante + quem lavrou. Obito:
        declarante + escrevente. Casamento: 1o/2o nubente + escrevente.
        Nomes de rc_pessoas; quem lavrou de rc_atos REGISTRO criado_por.
        Dado que falta sai em branco, sem quebrar a folha.

        Relato #124, 15/10/2026: TODA espécie que tem termo ganha as linhas
        — o natimorto e as sete do Livro E saíam sem nenhuma. Quem assina,
        além de quem lavrou, sai de `rc_folha.ASSINAM_ALEM_DE_QUEM_LAVROU`,
        que copia o que o texto de cada termo diz.
        """
        especie = str((assento or {}).get("especie") or "").upper()
        if especie not in FOLHA.ASSINAM_ALEM_DE_QUEM_LAVROU:
            return []

        def _nome_pessoa(papel: str) -> str:
            try:
                row = banco(con).um(
                    """SELECT nome FROM rc_pessoas
                        WHERE assento_id=%s AND papel=%s
                     ORDER BY ordem, id LIMIT 1""",
                    (assento["id"], papel))
                return str((row["nome"] if row else "") or "").strip()
            except Exception:  # noqa: BLE001
                return ""

        def _quem_lavrou() -> tuple[str, str]:
            lavrou = funcao = ""
            try:
                reg = banco(con).um(
                    """SELECT criado_por FROM rc_atos
                        WHERE assento_id=%s AND tipo='REGISTRO'
                     ORDER BY id DESC LIMIT 1""", (assento["id"],))
                quem = (reg["criado_por"] if reg and str(reg["criado_por"] or "").strip()
                        else assento.get("criado_por"))
                lavrou = RCETQ.nome_de_quem_lavrou(con, quem)
                funcao = RCETQ.funcao_de_quem_lavrou(con, quem)
            except Exception:  # noqa: BLE001
                pass
            return lavrou, funcao

        def _nomes_das_testemunhas() -> list[str]:
            try:
                return [str(r["nome"] or "").strip() for r in banco(con).ler(
                    """SELECT nome FROM rc_pessoas
                        WHERE assento_id=%s AND papel='TESTEMUNHA'
                     ORDER BY ordem, id""", (assento["id"],))]
            except Exception:  # noqa: BLE001
                return []

        def _nome_do_juiz_de_paz() -> str:
            # O campo da lavratura vem primeiro (`rc_assentos.juiz_de_paz`,
            # decisão do oficial de 15/10/2026); o acervo, que não o tem,
            # continua lido de `strNomeCelebrante` no blob. Sem nome, a linha
            # sai só com o rótulo.
            proprio = str(assento.get("juiz_de_paz") or "").strip()
            if proprio:
                return proprio
            try:
                dados = json.loads(assento.get("dados_json") or "{}")
                return str(dados.get("strNomeCelebrante") or "").strip()
            except Exception:  # noqa: BLE001
                return ""

        try:
            linhas = []
            for papel, rotulo in FOLHA.ASSINAM_ALEM_DE_QUEM_LAVROU[especie]:
                qualidade = rotulo or RC.ROTULO_DO_PAPEL.get(papel, papel)
                if papel == "TESTEMUNHA":
                    # Relato #124, resposta do oficial em 15/10/2026: todas as
                    # testemunhas do assento, e ao menos duas linhas (CC, art.
                    # 1.534) — a que falta sai com o rótulo, para assinar.
                    nomes = _nomes_das_testemunhas()
                    nomes += [""] * max(
                        0, FOLHA.TESTEMUNHAS_DO_CASAMENTO_NO_MINIMO - len(nomes))
                    linhas += [{"nome": n, "qualidade": qualidade}
                               for n in nomes]
                elif papel == FOLHA.JUIZ_DE_PAZ:
                    linhas.append({"nome": _nome_do_juiz_de_paz(),
                                   "qualidade": qualidade})
                else:
                    linhas.append({"nome": _nome_pessoa(papel),
                                   "qualidade": qualidade})
            lavrou, funcao = _quem_lavrou()
            return linhas + [{"nome": lavrou, "qualidade": funcao}]
        except Exception:  # noqa: BLE001 - imprimir nao pode cair por isto
            return []

    # ------------------- a folha do livro: tres colunas, frente e verso

    @app.route("/rcpn/<int:assento_id>/folha")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_folha(assento_id: int):
        """A folha do livro para imprimir — tres colunas, frente e verso.

        SÓ LÊ. Imprimir nao muda nada no banco. Se o teor esta vazio, monta
        dos campos (relato #38) e **nao grava**. A geometria das tres colunas
        mora no papel; a tela de uso nao da aula sobre ela.
        """
        with db.connect() as con:
            assento = banco(con).um("SELECT * FROM rc_assentos WHERE id=%s",
                                    (assento_id,))
            if not assento:
                flash("Esse assento não existe.", "danger")
                return redirect(url_for("rcpn_assentos"))
            assento = dict(assento)
            # ONDE O ASSENTO ESTA — livro e folha vao no cabecalho da folha,
            # e sao do ATO, nao do assento: quem sabe e `lugar_do_assento`.
            lugar_da_folha = RCE.lugar_do_assento(con, assento_id)
            notas = banco(con).ler(
                """SELECT tipo, teor, data_ato FROM rc_atos
                    WHERE assento_id=%s AND tipo IN ('AVERBACAO','ANOTACAO',
                                                    'RETIFICACAO')
                 ORDER BY id""", (assento_id,))
            # **PÁGINA EM BRANCO É DEFEITO** — relato #38, 31/08/2026.
            # O E-Ofício não guardava o teor: montava na hora de imprimir. A
            # carga deixou a coluna vazia, e esta rota só lia o gravado. Montar
            # dos campos (catálogo da casa) mostra o ato; **não grava**.
            # lugar_do_assento devolve `livro` (nao livro_numero): sem isso
            # o numero do livro some do cabecalho.
            livro_cab = str(lugar_da_folha.get("livro")
                            or lugar_da_folha.get("livro_numero")
                            or assento.get("livro_volume") or "")
            folha_cab = str(lugar_da_folha.get("folha") or "")
            visto = RCT.texto_para_mostrar(
                con, assento_id, serventia=_servent(),
                livro=livro_cab, folha=folha_cab)
            # HOTFIX-2026-10-08: selo do REGISTRO em CARIMBO (QR), igual PDF/ODT.
            etiqueta = _etiqueta_do_registro_rcpn(con, assento_id)
            assinaturas = _assinaturas_da_folha(con, assento)

        # A geometria da folha nao precisa da conexao.
        teor = _sem_selo_corrido(visto["texto"], etiqueta)
        carimbo_html = (RODT.carimbo_compacto_html(
            etiqueta, rotulo="SELO DIGITAL DO TJMA") if etiqueta else "")

        # 1a coluna: so o numero de ordem. O nome NAO vai ali.
        # 3a coluna: um so campo — imprimir concatena anotacao, averbacao e
        # retificacao (oficial 01/09/2026, 10:25).
        notas_coluna = [
            f"{n['tipo'].capitalize()} de "
            f"{(n['data_ato'] or '')[:10]}: {n['teor'] or ''}"
            for n in notas
        ]
        faces = [{
            "numero": assento.get("numero"),
            "termo": teor,
            "carimbo": carimbo_html,
            "notas_coluna": notas_coluna,
            "rotulo": "Frente",
            "assinaturas": assinaturas,
        }]
        # **O VERSO SAI SEMPRE**, mesmo em branco: a exigencia manda a coluna de
        # notas «inclusive no verso das folhas», e folha cujo verso nao tem a
        # margem e folha em que a averbacao nao cabe — e a averbacao vem depois.
        faces.append({"numero": "", "termo": "",
                      "notas_coluna": [],
                      "rotulo": "Verso"})
        return render_template(
            "rcpn_folha_impressa.html", folha=FOLHA, faces=faces, margem=12,
            congelado=visto["congelado"], do_acervo=visto["do_acervo"],
            erro_termo=visto["erro"], especie=visto["especie"],
            # O CABEÇALHO DA FOLHA: termo, LIVRO e folha no topo compacto.
            cabecalho=CAB.montar(sv(), especie=assento.get("especie"),
                                 termo=assento.get("numero")
                                 or lugar_da_folha.get("termo"),
                                 livro=livro_cab,
                                 folha=folha_cab or lugar_da_folha.get("folha")),
            falta_no_cabecalho=CAB.o_que_falta(
                CAB.montar(sv(), especie=assento.get("especie"))),
            titulo=f"Folha do livro — assento {assento.get('numero') or ''}")




    def _contexto_folha_do_assento(assento_id: int):
        """Dados da folha do livro (mesmo da rota HTML). So LE.

        Devolve (ctx dict, erro) — ctx pronto para rcpn_folha_impressa.html.
        """
        with db.connect() as con:
            assento = banco(con).um(
                "SELECT * FROM rc_assentos WHERE id=%s", (assento_id,)
            )
            if not assento:
                return None, "Esse assento nao existe."
            assento = dict(assento)
            lugar_da_folha = RCE.lugar_do_assento(con, assento_id)
            notas = banco(con).ler(
                """SELECT tipo, teor, data_ato FROM rc_atos
                    WHERE assento_id=%s AND tipo IN (
                        'AVERBACAO','ANOTACAO','RETIFICACAO')
                 ORDER BY id""", (assento_id,))
            livro_cab = str(
                lugar_da_folha.get("livro")
                or lugar_da_folha.get("livro_numero")
                or assento.get("livro_volume") or "")
            folha_cab = str(lugar_da_folha.get("folha") or "")
            ato_reg = banco(con).um(
                """SELECT selo FROM rc_atos
                    WHERE assento_id=%s AND tipo='REGISTRO'
                      AND coalesce(selo,'') != ''
                 ORDER BY id DESC LIMIT 1""",
                (assento_id,),
            )
            selo_reg = (ato_reg["selo"] if ato_reg else "") or ""
            visto = RCT.texto_para_mostrar(
                con, assento_id, serventia=_servent(),
                livro=livro_cab, folha=folha_cab, selo=selo_reg)
            etiqueta = (_etiqueta_do_registro_rcpn(con, assento_id)
                        if selo_reg else "")
            assinaturas = _assinaturas_da_folha(con, assento)
        teor = _sem_selo_corrido(visto["texto"] or "", etiqueta)
        # Folha do livro: o selo do REGISTRO sai em CARIMBO (QR + numero +
        # emolumentos) logo abaixo do termo — nunca no texto corrido.
        carimbo_html = (RODT.carimbo_compacto_html(
            etiqueta, rotulo="SELO DIGITAL DO TJMA") if etiqueta else "")
        notas_coluna = [
            f"{n['tipo'].capitalize()} de "
            f"{(n['data_ato'] or '')[:10]}: {n['teor'] or ''}"
            for n in notas
        ]
        faces = [{
            "numero": assento.get("numero"),
            "termo": teor,
            "carimbo": carimbo_html,
            "notas_coluna": notas_coluna,
            "rotulo": "Frente",
            "assinaturas": assinaturas,
        }, {"numero": "", "termo": "", "carimbo": "", "notas_coluna": [],
            "rotulo": "Verso"}]
        cab = CAB.montar(
            sv(), especie=assento.get("especie"),
            termo=assento.get("numero") or lugar_da_folha.get("termo"),
            livro=livro_cab,
            folha=folha_cab or lugar_da_folha.get("folha"))
        return {
            "folha": FOLHA,
            "faces": faces,
            "margem": 12,
            "congelado": visto["congelado"],
            "do_acervo": visto["do_acervo"],
            "erro_termo": visto["erro"],
            "especie": visto["especie"],
            "cabecalho": cab,
            "falta_no_cabecalho": CAB.o_que_falta(
                CAB.montar(sv(), especie=assento.get("especie"))),
            "titulo": f"Folha do livro - assento {assento.get('numero') or ''}",
            "assento": assento,
            "etiqueta": etiqueta,
        }, None

    def _html_folha_para_arquivo(ctx: dict) -> str:
        """O mesmo HTML da tela, autocontido para o LibreOffice. So calcula."""
        import re as _re
        import impressao_pdf as PDFIMP
        html = render_template("rcpn_folha_impressa.html", **{
            k: v for k, v in ctx.items() if k != "assento"
        })
        # Tira avisos de tela (.naoimprime) — no arquivo nao entram.
        html = _re.sub(
            r'<div class="aviso naoimprime">.*?</div>',
            "", html, flags=_re.S)
        html = _re.sub(
            r'<p class="naoimprime"[^>]*>.*?</p>',
            "", html, flags=_re.S)
        # Brasao: data-URI nas DUAS faces (Chrome nao resolve /static/ quando
        # abre o HTML temporario por file://).
        brasao = Path(app.root_path) / "static" / "brasao.jpg"
        return PDFIMP.incorporar_imagem_local(html, brasao, mime="image/jpeg")

    def _odt_bytes_da_folha(assento_id: int):
        """Compat: devolve (bytes, nome, erro) do ODT gerado do HTML da folha."""
        ctx, erro = _contexto_folha_do_assento(assento_id)
        if erro:
            return None, None, erro
        html = _html_folha_para_arquivo(ctx)
        numero = (ctx.get("assento") or {}).get("numero") or assento_id
        nome = f"folha-livro-termo-{numero}"
        import impressao_pdf as PDFIMP
        try:
            conteudo, _tipo, _arq, _ent = PDFIMP.arquivo_de_html(
                html, nome=nome, formato="odt", get_setting=db.get_setting)
        except PDFIMP.PdfError as e:
            return None, None, str(e)
        return conteudo, nome, None

    @app.route("/rcpn/<int:assento_id>/folha/papel")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_folha_papel(assento_id: int):
        """Folha do livro em PDF/ODT a partir do MESMO HTML da impressao. So LE.

        Pedido 09/09/2026: PDF e ODT iguais a folha HTML (3 colunas, CSS).
        Manda o HTML ao Chrome (PDF fiel) / ODT visual das paginas.
        """
        import impressao_pdf as PDFIMP
        ctx, erro = _contexto_folha_do_assento(assento_id)
        if erro:
            flash(erro, "danger")
            return redirect(url_for("rcpn_assento", assento_id=assento_id))
        html = _html_folha_para_arquivo(ctx)
        numero = (ctx.get("assento") or {}).get("numero") or assento_id
        nome = f"folha-livro-termo-{numero}"
        pedido = request.args.get("formato")
        if (pedido or "").lower() == "odt":
            # ODT EDITAVEL: texto do termo + carimbo do selo (QR) + notas,
            # pelo mesmo gerar_odt do RI/Notas. O ODT antigo era as paginas
            # do PDF do Chrome viradas PNG (`odt_de_pdf_visual`) — nada se
            # editava. A fidelidade visual das 3 colunas continua no PDF.
            from html import escape
            imagens: dict = {}
            cab = ctx.get("cabecalho") or {}
            corpo = html_para_odf(
                f'<p align="center"><b>{escape(str(cab.get("titulo_do_ato") or ""))}</b></p>'
                f'<p><b>Termo:</b> {escape(str(cab.get("termo") or ""))} &nbsp; '
                f'<b>Livro:</b> {escape(str(cab.get("livro") or ""))} &nbsp; '
                f'<b>Folha:</b> {escape(str(cab.get("folha") or ""))}</p>')
            corpo += html_para_odf(ctx["faces"][0]["termo"])
            if ctx.get("etiqueta"):
                corpo += RODT.carimbo_compacto_odf(
                    ctx["etiqueta"], rotulo="SELO DIGITAL DO TJMA",
                    imagens=imagens, prefixo_qr=f"qr-rcpn-{assento_id}")
            for ass in ctx["faces"][0].get("assinaturas") or []:
                corpo += html_para_odf(
                    '<p>&#160;</p><p>&#160;</p>'
                    '<p align="center">' + '_' * 45 + '</p>'
                    f'<p align="center">{escape(ass["nome"])}'
                    f'{", " if ass["nome"] and ass["qualidade"] else ""}'
                    f'{escape(ass["qualidade"])}</p>')
            for nota in ctx["faces"][0]["notas_coluna"]:
                corpo += html_para_odf(f"<p>{escape(nota)}</p>")
            conteudo = gerar_odt(corpo, titulo=nome, imagens=imagens or None)
            audit("RCPN_FOLHA_PAPEL", "rc_assentos", assento_id,
                  {"formato": "odt", "via": "gerar_odt editavel"})
            return Response(
                conteudo, mimetype="application/vnd.oasis.opendocument.text",
                headers={"Content-Disposition":
                         f'attachment; filename="{nome}.odt"'})
        try:
            conteudo, tipo, arquivo, entrega = PDFIMP.arquivo_de_html(
                html, nome=nome, formato=pedido, get_setting=db.get_setting)
        except PDFIMP.PdfError as e:
            flash(
                f"{e} Use Folha (HTML) e imprima no navegador, ou Baixe ODT "
                "se o PDF falhar.",
                "warning")
            return redirect(url_for("rcpn_assento", assento_id=assento_id))
        audit("RCPN_FOLHA_PAPEL", "rc_assentos", assento_id,
              {"formato": pedido or "pdf", "via": "html+libreoffice"})
        return Response(
            conteudo, mimetype=tipo,
            headers={"Content-Disposition": f'{entrega}; filename="{arquivo}"'})

    # ------------------- o checklist obrigatorio da inspecao (pag. 50)

    @app.route("/rcpn/<int:assento_id>/checklist", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_checklist(assento_id: int):
        """O checklist que a inspecao manda aplicar antes de concluir o ato.

        **ELE AVISA, E NAO TRAVA.** Registro de nascimento e imperativo legal
        (art. 250), e o balcao nao pode parar — mas o que ficou por conferir
        **fica gravado**, porque numa correicao a pergunta e «o sistema avisou?».
        """
        with db.connect() as con:
            assento = banco(con).um("SELECT * FROM rc_assentos WHERE id=%s",
                                    (assento_id,))
            if not assento:
                flash("Esse assento não existe.", "danger")
                return redirect(url_for("rcpn_assentos"))
            assento = dict(assento)
            ja = CHECK.do_ato(con, tabela="rc_assentos", ato_id=assento_id)

        if request.method == "POST":
            marcados = request.form.getlist("item")
            try:
                with db.transaction() as con:
                    CHECK.registrar(con, tabela="rc_assentos",
                                    ato_id=assento_id,
                                    especie=assento.get("especie") or "",
                                    marcados=marcados, agora=db.now(),
                                    por=usuario_nome())
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_checklist",
                                        assento_id=assento_id))
            audit("RCPN_CHECKLIST", "rc_assentos", assento_id,
                  {"conferidos": len(marcados)})
            flash(CHECK.resumo_para_gravar(assento.get("especie") or "",
                                           marcados),
                  "success" if len(marcados) >= len(
                      CHECK.itens_da_especie(assento.get("especie") or ""))
                  else "warning")
            return redirect(url_for("rcpn_assento", assento_id=assento_id))

        return render_template("rcpn_checklist.html", assento=assento,
                               itens=CHECK.itens_da_especie(
                                   assento.get("especie") or ""),
                               ja=ja, norma=CHECK)

    # ------------------------------------------ os gemeos, art. 234

    @app.route("/rcpn/gemeos", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_gemeos():
        """Os assentos de parto multiplo sem a ordem de nascimento.

        **`ibge_gemeo` NAO RESPONDE ESTA PERGUNTA.** Aquele campo diz **se** e
        gemeo; o art. 234 exige **qual e a ordem**, no assento de cada um. Usar
        um pelo outro faria o assento cumprir a remessa do IBGE e descumprir a
        lei.
        """
        if request.method == "POST":
            # O QUE NÃO É NÚMERO É O «INFORME» DO TEXTO (LD13). O `except`
            # já pegava o «abc»; a ordem de 18 ou 30 dígitos passava pelo
            # `int()` e estourava a gravação (`gemeo_ordem` é `integer`).
            assento_id = numero_digitado(request.form.get("assento_id") or 0)
            irmao_id = numero_digitado(request.form.get("irmao_id") or 0)
            ordem = numero_digitado(request.form.get("ordem") or 0,
                                    maximo=MAIOR_INTEGER)
            try:
                if None in (assento_id, irmao_id, ordem):
                    raise ValueError("número que não é número")
                with db.transaction() as con:
                    GEMEOS.amarrar(
                        con, assento_id, irmao_id=irmao_id, ordem=ordem,
                        agora=db.now())
            except (ValueError, TypeError) as erro:
                flash(str(erro) if isinstance(erro, GEMEOS.GemeosError)
                      else "Informe o assento, o irmão e a ordem.", "danger")
                return redirect(url_for("rcpn_gemeos"))
            audit("RCPN_GEMEO_ORDEM", "rc_assentos", assento_id, {})
            flash("Ordem de nascimento registrada.", "success")
            return redirect(url_for("rcpn_gemeos"))

        with db.connect() as con:
            faltando = GEMEOS.pendentes(con)
            # OS CANDIDATOS A IRMAO sao os nascimentos de parto multiplo — e o
            # balcao escolhe, porque quem sabe quem nasceu com quem e quem
            # atendeu, e nao uma regra que compare datas.
            candidatos = banco(con).ler(
                """SELECT id, numero, nome, data_ato, gemeo_ordem
                     FROM rc_assentos
                    WHERE especie='NASCIMENTO'
                      AND COALESCE(situacao,'ATIVO') <> 'CANCELADO'
                      AND ibge_gemeo IS NOT NULL
                 ORDER BY data_ato DESC, id DESC LIMIT 200""")
            candidatos = [c for c in candidatos
                          if GEMEOS.e_parto_multiplo(
                              banco(con).valor("SELECT ibge_gemeo FROM rc_assentos "
                                               "WHERE id=%s", (c["id"],)))]
        return render_template("rcpn_gemeos.html", faltando=faltando,
                               candidatos=candidatos, norma=GEMEOS)

    # ------------------------------------------ o registro tardio

    @app.route("/rcpn/registro-tardio")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_registro_tardio():
        """A regua do registro tardio — art. 249. SO LE, e nao grava nada.

        **A DISPENSA DAS TESTEMUNHAS SE CALCULA, e nao se imprime.** O modelo do
        E-Oficio desta casa traz «Dispensada a presenca de testemunhas» em toda
        folha, e o art. 249, II condiciona: menor de 12 anos **e** com DNV. Um
        papel que afirma a dispensa sempre faz o balcao deixar de colher
        testemunha onde ela e obrigatoria — e e o declarante que assina «sob as
        penas da lei».
        """
        idade = request.values.get("idade", "")
        tem_dnv = bool(request.values.get("tem_dnv"))
        testemunhas = request.values.get("testemunhas", "")
        perguntou = bool(request.values.get("conferir"))
        regra = TARDIO.dispensa_testemunhas(idade=idade, tem_dnv=tem_dnv)             if perguntou else None
        # o que não é número de testemunhas é nenhuma, como o campo vazio (LD13)
        faltas = TARDIO.o_que_conferir(
            idade=idade, tem_dnv=tem_dnv,
            testemunhas=numero_digitado(testemunhas) or 0) if perguntou else []
        return render_template("rcpn_registro_tardio.html", norma=TARDIO,
                               regra=regra, faltas=faltas, idade=idade,
                               tem_dnv=tem_dnv, testemunhas=testemunhas,
                               perguntou=perguntou)

    # ------------------------------------------ o mutirao do art. 347

    @app.route("/rcpn/dados-cadastrais")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_dados_cadastrais():
        """Os assentos anteriores a 14/11/2017 que ainda nao tem CPF. SÓ LÊ.

        O ARTIGO USA DOIS VERBOS: o CPF se **averba**, e o RG, o titulo de
        eleitor e os demais se **anotam**. Sao atos diferentes, e trocar um pelo
        outro seria lavrar o ato errado num assento — e ninguem percebe, porque
        os dois aparecem a margem.
        """
        with db.connect() as con:
            lista = DADOS.pendentes(con)
            quadro = DADOS.resumo(con)
        return render_template("rcpn_dados_cadastrais.html", lista=lista,
                               quadro=quadro, norma=DADOS)

    # --------------------- retificacao, restauracao e suprimento do RCPN

    @app.route("/rcpn/retificacoes")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_retificacoes():
        """Os processos em andamento, do prazo mais apertado. SÓ LÊ."""
        with db.connect() as con:
            abertos = RETRC.em_andamento(con)
            estourados = {x["id"]
                          for x in RETRC.fora_do_prazo(con,
                                                       hoje=db.now()[:10])}
        return render_template("rcpn_retificacoes.html", abertos=abertos,
                               estourados=estourados, norma=RRNORMA,
                               modulo=RETRC)

    @app.route("/rcpn/retificacoes/nova", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_retificacao_nova():
        """Abre o processo.

        O PEDIDO VERBAL EXIGE O TERMO NA HORA (art. 348, § 1º, III) — quem chega
        ao balcao dizendo «meu nome esta errado na certidao» esta formulando um
        requerimento, e manda-lo voltar com peticao e negar o que a norma
        permite.
        """
        if request.method == "POST":
            try:
                with db.transaction() as con:
                    pid = RETRC.abrir(
                        con,
                        instituto=request.form.get("instituto", ""),
                        forma=request.form.get("forma", ""),
                        requerente_nome=request.form.get("requerente_nome", ""),
                        requerente_documento=request.form.get(
                            "requerente_documento", ""),
                        assinado_por=request.form.get("assinado_por", ""),
                        o_que_se_pede=request.form.get("o_que_se_pede", ""),
                        assento_descricao=request.form.get(
                            "assento_descricao", ""),
                        termo_verbal=request.form.get("termo_verbal", ""),
                        ano=int(db.now()[:4]), agora=db.now(),
                        por=usuario_nome())
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_retificacao_nova"))
            audit("RCPN_RETIFICACAO_ABERTA", "rr_processos", pid, {})
            return redirect(url_for("rcpn_retificacao", processo_id=pid))
        return render_template("rcpn_retificacao_nova.html", norma=RRNORMA)

    @app.route("/rcpn/retificacoes/<int:processo_id>", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_retificacao(processo_id: int):
        """A ficha do processo, e os atos dele."""
        acao = request.form.get("acao", "") if request.method == "POST" else ""
        if acao:
            try:
                with db.transaction() as con:
                    if acao == "instruir":
                        RETRC.instruir(con, processo_id, agora=db.now(),
                                       por=usuario_nome())
                    elif acao == "crc":
                        RETRC.registrar_consulta_crc(
                            con, processo_id,
                            o_que_se_procurou=request.form.get(
                                "o_que_se_procurou", ""),
                            resultado=request.form.get("resultado", ""),
                            achou_duplicidade=bool(
                                request.form.get("achou_duplicidade")),
                            achou_ato_em_outra_serventia=bool(
                                request.form.get("achou_outra")),
                            protocolo=request.form.get("protocolo", ""),
                            agora=db.now(), por=usuario_nome())
                    elif acao == "decidir":
                        RETRC.decidir(
                            con, processo_id,
                            decisao=request.form.get("decisao", ""),
                            fundamento=request.form.get("fundamento", ""),
                            erro_da_serventia=bool(
                                request.form.get("erro_da_serventia")),
                            erro_fundamento=request.form.get(
                                "erro_fundamento", ""),
                            agora=db.now(), por=usuario_nome())
                    elif acao == "comunicar":
                        RETRC.registrar_comunicacao_353(
                            con, processo_id,
                            fundo=request.form.get("fundo", ""),
                            teor=request.form.get("teor", ""),
                            canal=request.form.get("canal", ""),
                            protocolo=request.form.get("protocolo", ""),
                            agora=db.now(), por=usuario_nome())
                    elif acao == "ato":
                        RETRC.registrar_ato(
                            con, processo_id,
                            ato_id=int(request.form.get("ato_id") or 0),
                            agora=db.now(), por=usuario_nome())
                    else:
                        raise ValueError("Não conheço essa ação.")
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_retificacao",
                                        processo_id=processo_id))
            audit(f"RCPN_RETIFICACAO_{acao.upper()}", "rr_processos",
                  processo_id, {})
            flash("Registrado.", "success")
            return redirect(url_for("rcpn_retificacao",
                                    processo_id=processo_id))

        with db.connect() as con:
            try:
                processo = RETRC._exigir(con, processo_id)
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_retificacoes"))
            contexto = {
                "processo": processo,
                "consultas": RETRC.consultas(con, processo_id),
                "comunicacoes": RETRC.comunicacoes_353(con, processo_id),
                "passos": RETRC.proximos_passos(con, processo_id),
                "faltas": RETRC.o_que_falta_para_decidir(con, processo_id),
                "andamento": banco(con).ler(
                    """SELECT * FROM rr_andamento WHERE processo_id=%s
                        ORDER BY id DESC""", (processo_id,)),
            }
        return render_template("rcpn_retificacao.html", norma=RRNORMA,
                               modulo=RETRC, **contexto)

    # ------------------------------------------ o painel das comunicacoes

    @app.route("/rcpn/comunicacoes-painel")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_painel():
        """As seis linhas, nove destinos, do prazo mais curto ao mais longo.

        POR QUE UM PAINEL: quem chega de manha nao vai abrir seis telas para
        saber se alguma venceu. Abriria a que lembrasse — e a que se esquece e
        justamente a que nao tem trabalho para lembra-la.

        SO LE, e nao faz comunicacao nenhuma.
        """
        with db.connect() as con:
            linhas = OBRIG.painel(con, hoje=db.now()[:10])
        return render_template("rcpn_painel.html", linhas=linhas, norma=OBRIG,
                               destinos=OBRIG.quantos_destinos())

    # ------------------------------------------ a FUNAI

    @app.route("/rcpn/funai")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_funai():
        """Os nascimentos de indigena que a FUNAI ainda nao recebeu. SÓ LÊ."""
        with db.connect() as con:
            hoje = db.now()[:10]
            esperando = FUNAI.pendentes(con, hoje=hoje)
            historico = FUNAI.historico(con)
        return render_template("rcpn_funai.html", esperando=esperando,
                               historico=historico, norma=FUNAI, hoje=hoje)

    @app.route("/rcpn/funai/<int:assento_id>", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_funai_oficio(assento_id: int):
        """O oficio a FUNAI, e o registro de que ele saiu.

        A ETNIA E A ALDEIA SAO PERGUNTADAS, e nao deduzidas do sobrenome: o
        § 1º permite que o povo seja lancado como sobrenome **a pedido do
        declarante** — permite, nao obriga.
        """
        # `request.values`, E NAO `request.form`. O formulario que refaz o
        # oficio manda por **GET** — ele so recalcula, nao grava —, e com
        # `.form` o que o operador digitasse sumiria: a tela continuaria
        # dizendo «falta preencher a etnia» depois de ele a ter preenchido.
        # Quem achou foi o teste de TELA; o de dominio passava, porque ele
        # chama `montar` direto com os valores na mao.
        etnia = request.values.get("etnia", "")
        aldeia = request.values.get("aldeia", "")
        with db.connect() as con:
            try:
                oficio = FUNAI.montar(
                    con, assento_id,
                    serventia={"nome": db.get_setting("serventia_nome", ""),
                               "cns": _cns_rcpn()},
                    etnia=etnia, aldeia=aldeia)
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_funai"))

        if request.method == "POST" and request.form.get("acao") == "enviei":
            try:
                with db.transaction() as con:
                    FUNAI.registrar_envio(
                        con, assento_id, agora=db.now(),
                        por=usuario_nome(), teor=oficio["teor"],
                        canal=request.form.get("canal", ""),
                        protocolo=request.form.get("protocolo", ""),
                        etnia=etnia, aldeia=aldeia)
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_funai"))
            audit("RCPN_FUNAI_ENVIADA", "rc_funai", assento_id, {})
            flash("Comunicacao a FUNAI registrada.", "success")
            return redirect(url_for("rcpn_funai"))

        if request.method == "POST" and request.form.get("acao") == "dispensar":
            try:
                with db.transaction() as con:
                    FUNAI.dispensar(con, assento_id,
                                    motivo=request.form.get("motivo", ""),
                                    agora=db.now(), por=usuario_nome())
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_funai_oficio",
                                        assento_id=assento_id))
            audit("RCPN_FUNAI_DISPENSADA", "rc_funai", assento_id, {})
            flash("Dispensada, com o motivo registrado.", "success")
            return redirect(url_for("rcpn_funai"))

        return render_template("rcpn_funai_oficio.html", oficio=oficio,
                               assento_id=assento_id, norma=FUNAI,
                               etnia=etnia, aldeia=aldeia)

    # ------------------------------------------ a remessa do SIRC
    #
    # **O QUE JÁ TEM ENVIO REGISTRADO SAI DA LISTA — 06/10/2026.** Até aqui o
    # botão «Enviar» falava com a Central e não anotava nada: o mesmo registro
    # voltava amanhã como devido, podia ser mandado de novo, e o gestor o
    # cobrava como atrasado para sempre. A tela, o arquivo, a validação e o
    # envio passam pela MESMA lista — senão o «lote 2» da tela seria outro
    # lote no envio.

    def _sirc_devendo(con):
        return SIRC.sem_os_ja_enviados(con, SIRC.pendentes_de_remessa(con))

    def _sirc_cancelamentos(con):
        return SIRC.cancelamentos_sem_os_ja_enviados(
            con, SIRC.pendentes_de_cancelamento(con))

    def _anotar_envio_ao_sirc(central, referencias, resultado, o_que):
        """Grava em `ge_envios` o que a Central acabou de receber, com a
        resposta dela como protocolo. Se não der para anotar, o envio NÃO
        se desfaz (já está lá) — a tela diz onde anotar à mão."""
        try:
            with db.transaction() as con:
                GENV.registrar(
                    con, central, protocolo=str(resultado or "")[:200],
                    registrado_por=usuario_nome() or "sistema",
                    referencias=referencias, canal="API",
                    mensagem=f"{o_que}: {resultado}"[:1000], origem="SISTEMA")
        except (GENV.EnvioError, sqlite3.Error) as erro:
            flash(f"O SIRC recebeu, mas o envio não ficou anotado aqui ({erro}). "
                  "Anote em «Envios às Centrais» com o número que o SIRC "
                  "mostrou, senão ele volta a aparecer como devido.", "warning")

    @app.route("/rcpn/sirc/arquivo/<int:lote>", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_sirc_arquivo(lote: int):
        """Baixa um lote da remessa. SÓ LÊ.

        O ARQUIVO SAI EM UTF-8 porque o manual manda, e porque o limite de
        tamanho e em BYTES: acento em dois bytes muda a conta.
        """
        with db.connect() as con:
            devendo = _sirc_devendo(con)
            # **`con` VAI JUNTO, E NÃO MAIS `None`** — achado em 13/09/2026:
            # sem ele, `_registro()` não tinha como buscar o sexo e o CPF do
            # registrado nem as filiações (mãe/pai), que o XSD exige.
            montado = SIRC.montar(
                con, devendo, cns=_cns_rcpn(),
                competencia=request.form.get("competencia", ""))
        if not 1 <= lote <= len(montado["lotes"]):
            flash("Esse lote nao existe na remessa de agora.", "danger")
            return redirect(url_for("rcpn_sirc"))
        xml = montado["lotes"][lote - 1]["xml"]
        return Response(
            xml.encode("utf-8"), mimetype="application/xml",
            headers={"Content-Disposition":
                     f'attachment; filename="sirc-remessa-{lote:03d}.xml"'})

    @app.route("/rcpn/sirc/arquivo/<int:lote>/mrc", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_sirc_arquivo_mrc(lote: int):
        """O MESMO lote, comprimido e cifrado — pronto para o upload manual
        no SIRC-Web (Transmissão de Arquivo → Enviar Arquivo de Movimento).

        **O `.xml` acima NÃO SERVE PARA ISSO** — o SIRC-Web só aceita
        `.mrc` (seção 3.4 do manual); o `.xml` cru é para conferência e
        para o caminho por senha (`sirc_cliente.py`), que recebe o XML
        puro dentro do envelope SOAP.
        """
        with db.connect() as con:
            devendo = _sirc_devendo(con)
            montado = SIRC.montar(con, devendo, cns=_cns_rcpn())
        if not 1 <= lote <= len(montado["lotes"]):
            flash("Esse lote nao existe na remessa de agora.", "danger")
            return redirect(url_for("rcpn_sirc"))
        xml = montado["lotes"][lote - 1]["xml"]
        mrc = SIRC.arquivo_mrc(xml, cns=_cns_rcpn())
        nome = SIRC.nome_do_arquivo_mrc("sirc-remessa", lote)
        return Response(
            mrc, mimetype="application/octet-stream",
            headers={"Content-Disposition":
                     f'attachment; filename="{nome}"'})

    @app.route("/rcpn/sirc/carga/arquivo/<int:lote>", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_sirc_carga_arquivo(lote: int):
        """Baixa um lote da CARGA do acervo — não é a remessa do dia. SÓ LÊ.

        **DECISÃO DO OFICIAL EM 14/09/2026**: o lote de 6.757 assentos
        importados em .docx precisa subir ao SIRC, porque nunca foi
        enviado. Mesmo envelope da remessa; o que muda é de onde os
        assentos vêm (`pendentes_de_carga_do_acervo`, e não
        `pendentes_de_remessa`).
        """
        with db.connect() as con:
            devendo = SIRC.pendentes_de_carga_do_acervo(con)
            montado = SIRC.montar(con, devendo, cns=_cns_rcpn())
        if not 1 <= lote <= len(montado["lotes"]):
            flash("Esse lote nao existe na carga de agora.", "danger")
            return redirect(url_for("rcpn_sirc"))
        xml = montado["lotes"][lote - 1]["xml"]
        return Response(
            xml.encode("utf-8"), mimetype="application/xml",
            headers={"Content-Disposition":
                     f'attachment; filename="sirc-carga-acervo-{lote:03d}.xml"'})

    @app.route("/rcpn/sirc/inexistencia", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_sirc_inexistencia():
        """A declaracao de mes sem movimento — art. 225, § 3º. SÓ LÊ.

        E A OBRIGACAO QUE MAIS SE ESQUECE, justamente porque nao ha trabalho que
        a lembre: nao houve registro, nao houve remessa, e ninguem repara na
        falta.
        """
        try:
            xml = SIRC.declaracao_de_inexistencia(
                competencia=request.form.get("competencia", ""))
        except ValueError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_sirc"))
        return Response(
            xml.encode("utf-8"), mimetype="application/xml",
            headers={"Content-Disposition":
                     'attachment; filename="sirc-sem-movimento.xml"'})

    # ------------------------------------------ o envio pela API, sem A3
    #
    # **CONSTRUÍDO EM 14/09/2026, junto com `sirc_cliente.py`.** Até aqui a
    # tela só sabia MONTAR o arquivo e devolvê-lo para o oficial subir no
    # SIRC-Web à mão. O caminho por senha (sem certificado A3 — ver
    # `sirc_api_nao_exige_a3` na memória) permite mandar direto daqui,
    # **quando a credencial já tiver sido informada**; sem ela, o botão
    # explica onde informar, em vez de estourar HTTP 500.
    RECUSAS_DO_SIRC = (SC.SircClienteError, CENTCRED.CredencialError)

    @app.route("/rcpn/sirc/arquivo/<int:lote>/validar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_sirc_arquivo_validar(lote: int):
        """Confere o lote na Central sem enviá-lo de verdade
        (`validarMovimento<Espécie>`). SÓ FALA COM A CENTRAL — não altera
        nada aqui nem lá."""
        with db.connect() as con:
            devendo = _sirc_devendo(con)
            montado = SIRC.montar(con, devendo, cns=_cns_rcpn())
        if not 1 <= lote <= len(montado["lotes"]):
            flash("Esse lote nao existe na remessa de agora.", "danger")
            return redirect(url_for("rcpn_sirc"))
        alvo = montado["lotes"][lote - 1]
        try:
            resultado = SC.validar(alvo["especie"], alvo["xml"],
                                   cns=_cns_rcpn())
        except RECUSAS_DO_SIRC as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_sirc"))
        flash(f"O SIRC respondeu ao validar o lote {lote}: {resultado}",
             "success")
        return redirect(url_for("rcpn_sirc"))

    @app.route("/rcpn/sirc/arquivo/<int:lote>/enviar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_sirc_arquivo_enviar(lote: int):
        """Manda o lote de verdade — `enviarMovimento<Espécie>`. Só o
        transporte; quem monta o XML continua sendo `sirc_remessa.montar()`."""
        with db.connect() as con:
            devendo = _sirc_devendo(con)
            montado = SIRC.montar(con, devendo, cns=_cns_rcpn())
        if not 1 <= lote <= len(montado["lotes"]):
            flash("Esse lote nao existe na remessa de agora.", "danger")
            return redirect(url_for("rcpn_sirc"))
        alvo = montado["lotes"][lote - 1]
        try:
            resultado = SC.enviar(alvo["especie"], alvo["xml"],
                                  cns=_cns_rcpn())
        except RECUSAS_DO_SIRC as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_sirc"))
        flash(f"O SIRC respondeu ao enviar o lote {lote}: {resultado}",
             "success")
        _anotar_envio_ao_sirc("SIRC", alvo["referencias"], resultado,
                              f"lote {lote} de {alvo['especie'].lower()}")
        return redirect(url_for("rcpn_sirc"))

    @app.route("/rcpn/sirc/inexistencia/enviar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_sirc_inexistencia_enviar():
        """Manda a declaração de mês sem movimento direto pela API, em vez
        de baixar o arquivo para subir no SIRC-Web."""
        try:
            xml = SIRC.declaracao_de_inexistencia(
                competencia=request.form.get("competencia", ""))
            resultado = SC.declarar_inexistencia(xml, cns=_cns_rcpn())
        except (ValueError, *RECUSAS_DO_SIRC) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_sirc"))
        flash(f"O SIRC respondeu à declaração: {resultado}", "success")
        return redirect(url_for("rcpn_sirc"))

    # ------------------------------------------ o cancelamento de termo
    #
    # **NÃO É UM DOS SETE DO ART. 225** — é a seção 5.7 do manual: um termo
    # que nunca valeu (lavrado no livro errado, por exemplo), e não um
    # registro que existe e mudou. `rc_assentos.situacao='CANCELADO'` já é
    # o dado desta casa; o motivo vem da averbação mais recente sobre o
    # assento, porque não há coluna própria para ele.

    @app.route("/rcpn/sirc/cancelamento/arquivo/<int:lote>",
              methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_sirc_cancelamento_arquivo(lote: int):
        """Baixa um lote de cancelamento de termo. SÓ LÊ."""
        with db.connect() as con:
            pendentes = _sirc_cancelamentos(con)
            montado = SIRC.montar_cancelamento(pendentes)
        if not 1 <= lote <= len(montado["lotes"]):
            flash("Esse lote nao existe no cancelamento de agora.", "danger")
            return redirect(url_for("rcpn_sirc"))
        xml = montado["lotes"][lote - 1]["xml"]
        return Response(
            xml.encode("utf-8"), mimetype="application/xml",
            headers={"Content-Disposition":
                     f'attachment; filename="sirc-cancelamento-{lote:03d}.xml"'})

    @app.route("/rcpn/sirc/cancelamento/arquivo/<int:lote>/validar",
              methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_sirc_cancelamento_validar(lote: int):
        with db.connect() as con:
            pendentes = _sirc_cancelamentos(con)
            montado = SIRC.montar_cancelamento(pendentes)
        if not 1 <= lote <= len(montado["lotes"]):
            flash("Esse lote nao existe no cancelamento de agora.", "danger")
            return redirect(url_for("rcpn_sirc"))
        try:
            resultado = SC.validar_cancelamento(
                montado["lotes"][lote - 1]["xml"], cns=_cns_rcpn())
        except RECUSAS_DO_SIRC as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_sirc"))
        flash(f"O SIRC respondeu ao validar o cancelamento {lote}: "
             f"{resultado}", "success")
        return redirect(url_for("rcpn_sirc"))

    @app.route("/rcpn/sirc/cancelamento/arquivo/<int:lote>/enviar",
              methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_sirc_cancelamento_enviar(lote: int):
        with db.connect() as con:
            pendentes = _sirc_cancelamentos(con)
            montado = SIRC.montar_cancelamento(pendentes)
        if not 1 <= lote <= len(montado["lotes"]):
            flash("Esse lote nao existe no cancelamento de agora.", "danger")
            return redirect(url_for("rcpn_sirc"))
        try:
            resultado = SC.enviar_cancelamento(
                montado["lotes"][lote - 1]["xml"], cns=_cns_rcpn())
        except RECUSAS_DO_SIRC as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_sirc"))
        flash(f"O SIRC respondeu ao enviar o cancelamento {lote}: "
             f"{resultado}", "success")
        _anotar_envio_ao_sirc("SIRC_CANCELAMENTO",
                              montado["lotes"][lote - 1]["referencias"],
                              resultado, f"cancelamento {lote}")
        return redirect(url_for("rcpn_sirc"))

    @app.route("/rcpn/sirc")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_sirc():
        """O que o SIRC ainda não recebeu — art. 225, UM dia útil.

        E O PRAZO MAIS CURTO DO SISTEMA INTEIRO, e o que alcanca mais coisa:
        nascimento, natimorto, casamento, obito, **averbacao, anotacao e
        retificacao**. Por isso a lista vem do mais antigo: o que espera ha mais
        tempo ja estourou.
        """
        with db.connect() as con:
            devendo = _sirc_devendo(con)
            montado = SIRC.montar(con, devendo, cns=_cns_rcpn())
            # **RELATO DO OFICIAL EM 13/09/2026: "não aparece todos
            # registros do sistema para envio".** A lista caiu de milhares
            # para poucos depois do conserto do vazamento do acervo — certo,
            # mas sem esse número a tela parecia estar escondendo registro.
            do_acervo = SIRC.quantos_ficam_de_fora_pelo_acervo(con)
            # **A CARGA DO ACERVO — decisão do oficial em 14/09/2026**: o
            # lote de 6.757 assentos em .docx precisa subir ao SIRC, porque
            # nunca foi enviado. Não é a remessa do dia (que conta 1 dia
            # útil de prazo, sem sentido para um nascimento de 1900) — é
            # uma carga à parte, com o mesmo envelope.
            carga = SIRC.pendentes_de_carga_do_acervo(con)
            montado_carga = SIRC.montar(con, carga, cns=_cns_rcpn())
            # **O CANCELAMENTO DE TERMO NÃO É UM DOS SETE DO ART. 225**
            # (seção 5.7 do manual) — por isso é uma lista à parte, e não
            # entra em `devendo`/`montado`.
            cancelamentos = _sirc_cancelamentos(con)
            montado_cancelamento = SIRC.montar_cancelamento(cancelamentos)
        return render_template("rcpn_sirc.html", devendo=devendo,
                               montado=montado, norma=SIRC,
                               cancelamentos=cancelamentos,
                               montado_cancelamento=montado_cancelamento,
                               do_acervo=do_acervo, carga=carga,
                               montado_carga=montado_carga)

    # ------------------------------------------ a remessa do IBGE
    #
    # POR QUE ELA TEM TELA, E POR QUE ELA TEM AGORA
    #     `ibge_geracao.montar()` ficou pronto e testado, e este projeto já tem
    #     SEIS casos de função de domínio pronta que nenhuma tela chamava — o
    #     `obter_selo`, a remessa da CRA, o apontamento do protesto, as telas do
    #     núcleo, o edital, o aviso. Em todos eles o buraco só apareceu meses
    #     depois, no balcão. Desta vez a tela vem junto.

    @app.route("/rcpn/ibge", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_ibge():
        """A remessa trimestral do IBGE — Lei 6.015/1973, art. 49. SÓ LÊ.

        MONTAR NÃO GRAVA NADA: montar o arquivo é ler o que já está lavrado.

        **CORREÇÃO DE 30/08/2026, e ela era minha.** Aqui estava escrito que
        guardar «a remessa do 2º trimestre foi gerada» seria inventar um
        controle que ninguém conferiria. **Gerada, de fato, não; ENTREGUE, sim**
        — e as duas não são a mesma coisa. O art. 224 pune o descumprimento com
        multa de 1 a 5 salários mínimos, «sem prejuízo da ação penal», e numa
        correição a pergunta é «o trimestre passado foi entregue?». Sem resposta,
        o painel das comunicações tinha de declarar um buraco. Agora há o botão
        de **registrar a entrega**, com o teor congelado e o protocolo — e é ele
        que grava, e só ele.

        A CONFERÊNCIA VEM ANTES DO BOTÃO DE BAIXAR, e é deliberado: o IBGE
        **aceita** uma remessa inteira de noves, e ela não serve para nada.
        Quem manda precisa ver quantas posições saíram como «ignorado» antes de
        mandar — cumprir a obrigação e mandar papel em branco parecem a mesma
        coisa do lado de fora.
        """
        hoje_ = date.today()
        # `request.values`, E NAO `_campo`, QUE SO LE O FORMULARIO.
        #
        # O seletor desta tela manda por POST, e por isso `_campo` bastava. Mas
        # o **redirecionamento** de depois de registrar a entrega manda por
        # QUERY STRING (`url_for(..., ano=..., trimestre=...)`) — e a rota o
        # ignorava: quem registrasse a entrega do 1o trimestre voltaria olhando
        # o 2o, sem ver a marca que acabou de gravar.
        #
        # **Segunda vez na mesma noite**: a tela do oficio a FUNAI tinha o
        # defeito espelhado — formulario por GET lido com `request.form`.
        _v = lambda nome: (request.values.get(nome) or "").strip()   # noqa: E731
        ano = numero_digitado(_v("ano")) if _v("ano") else hoje_.year
        # O TRIMESTRE QUE A TELA OFERECE É O ANTERIOR, e não o de hoje: a
        # remessa se manda depois que ele fecha.
        padrao = (hoje_.month - 1) // 3 or 4
        trimestre = numero_digitado(_v("trimestre")) if _v("trimestre") else padrao

        erro, r = None, None
        if ano is None or trimestre is None:
            # «abc» ERA A TELA DE ERRO (LD13). O que não é número não monta
            # remessa nenhuma — e não vira o trimestre padrão, que o «entreguei»
            # marcaria como entregue sem ninguém o ter escolhido.
            erro = "O ano e o trimestre se escrevem em números (ex.: 2026 e 3)."
            ano = hoje_.year if ano is None else ano
            trimestre = padrao if trimestre is None else trimestre
        else:
            try:
                with db.connect() as con:
                    r = IBGEG.montar(con, ano=ano, trimestre=trimestre,
                                     config=db.get_settings())
            except IBGEG.IbgeError as falha:
                erro = str(falha)

        if _v("acao") == "baixar" and r and r["linhas"]:
            return _zip_do_ibge(r)

        if request.method == "POST" and _v("acao") == "entreguei":
            # O TEOR QUE CONGELA E O DO ARQUIVO INTEIRO, e nao o nome dele:
            # quando o IBGE reclamar de um trimestre, e este texto que se le.
            if not (r and r["linhas"]):
                flash("Não há o que registrar: este trimestre não tem linhas.",
                      "danger")
                return redirect(url_for("rcpn_ibge", ano=ano,
                                        trimestre=trimestre))
            teor = "\n\n".join(
                f"### {nome}\n" + IBGE.FIM_DE_LINHA.join(linhas)
                for nome, linhas in sorted(r["arquivos"].items()))
            try:
                with db.transaction() as con:
                    IBGEG.registrar_entrega(
                        con, ano=ano, trimestre=trimestre, teor=teor,
                        quantos=r["linhas"], agora=db.now(),
                        por=usuario_nome(),
                        canal=request.form.get("canal", ""),
                        protocolo=request.form.get("protocolo", ""))
            except ValueError as falha:
                flash(str(falha), "danger")
                return redirect(url_for("rcpn_ibge", ano=ano,
                                        trimestre=trimestre))
            audit("RCPN_IBGE_ENTREGUE", "ib_entregas", None,
                  {"ano": ano, "trimestre": trimestre, "linhas": r["linhas"]})
            flash(f"Entrega do {trimestre}º trimestre de {ano} registrada.",
                  "success")
            return redirect(url_for("rcpn_ibge", ano=ano, trimestre=trimestre))

        with db.connect() as con:
            entregue = IBGEG.entregas(con).get((ano, trimestre))
            atrasados = IBGEG.a_prestar(con, hoje=hoje_.isoformat())
        return render_template("rcpn_ibge.html", ano=ano, trimestre=trimestre,
                               r=r, erro=erro, anos=range(hoje_.year, 2019, -1),
                               larguras=IBGE.ARQUIVOS, entregue=entregue,
                               atrasados=atrasados, norma=IBGEG)

    def _zip_do_ibge(r: dict):
        """Os arquivos num `CARTINF.ZIP`, que é o nome que o IBGE espera.

        EM ISO-8859-1, e não em UTF-8: acento em dois bytes empurraria todos os
        campos da linha para a direita, e o arquivo é de largura fixa. É a
        mesma lição do arquivo da CRA.
        """
        memoria = io.BytesIO(IBGEG.zip_da_remessa(r))
        audit("RCPN_IBGE_REMESSA", "rc_assentos", None,
              {"ano": r["ano"], "trimestre": r["trimestre"],
               "linhas": r["linhas"]})
        # O NOME É `CARTINF.ZIP`, e só ele (28/10/2026): com o ano e o
        # trimestre no nome, o envio ao IBGE recusava o arquivo.
        return send_file(
            memoria, mimetype="application/zip", as_attachment=True,
            download_name=IBGEG.NOME_DO_ZIP)

    @app.route("/rcpn/<int:assento_id>/confirmar-livro", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_confirmar_livro(assento_id: int):
        """Confirma no sistema o livro que alguém foi conferir no papel.

        AVISO SEM SAÍDA É AVISO QUE FICA PARA SEMPRE. Se quem foi até a estante
        não tem onde dizer o que viu, o próximo abre a ficha e vê o mesmo
        aviso — e na terceira vez ninguém lê mais.

        O livro digitado ENTRA como o volume do assento, e a marca sai. Quem
        conferiu fica na auditoria, porque isto é correção de dado de livro.

        E FICA TAMBÉM NO PRÓPRIO ASSENTO (`livro_conferido_em`), por dois
        motivos: a carga precisa saber que já foi conferido, senão ela
        ressuscita a marca na próxima rodada; e quem abrir a ficha daqui a
        cinco anos merece ver que alguém já foi à estante, em vez de ir de
        novo.
        """
        volta = url_for("rcpn_assento", assento_id=assento_id)
        livro = _campo("livro_volume").strip()
        if not livro:
            flash("Informe o livro como está escrito na capa — por exemplo "
                  "«B-1» ou «B-Auxiliar 1».", "danger")
            return redirect(volta)
        with db.transaction() as con:
            linha = banco(con).um(
                "SELECT livro_volume FROM rc_assentos WHERE id=%s",
                (assento_id,))
            if not linha:
                flash("Assento não encontrado.", "danger")
                return redirect(url_for("rcpn_assentos"))
            antes = linha["livro_volume"]
            banco(con).escrever(
                """UPDATE rc_assentos SET livro_volume=%s,
                       livro_a_confirmar=NULL, livro_conferido_em=%s,
                       livro_conferido_por=%s WHERE id=%s""",
                (livro, agora(), usuario_nome(), assento_id))
        # `audit` abre transação própria: FORA do `with`.
        audit("RCPN_LIVRO_CONFERIDO", "rc_assentos", assento_id,
              {"antes": antes, "agora": livro})
        flash(f"Livro confirmado como {livro}, conferido no livro de papel.",
              "success")
        return redirect(volta)

    # ------------------------- a certidão do RCPN, no modelo do CNJ

    def _float_campo(nome, padrao=None):
        bruto = (_campo(nome) or "").strip().replace(",", ".")
        if not bruto:
            return padrao
        try:
            return float(bruto)
        except ValueError:
            return padrao

    def _imagem_da_certidao_inteiro(assento_id: int):
        """Guarda a imagem da via reprográfica. Devolve o caminho ou None."""
        from storage import safe_component, save_upload
        arquivo = request.files.get("imagem_assento")
        if arquivo and arquivo.filename:
            destino = (pasta_dos_arquivos() / "RegistroCivil" / "InteiroTeor"
                       / safe_component(str(assento_id)))
            info = save_upload(arquivo, destino)
            return info.get("stored_path") or info.get("path")
        aid = numero_digitado(_campo("anexo_imagem_id"))   # LD13: «²» era 500
        if aid is not None:
            row = db.get_attachment(aid)
            # SÓ O ANEXO DO TERMO DESTE ASSENTO (LS02, 19/10/2026) — os mesmos
            # que a ficha oferece na lista. O número vem do formulário, e sem
            # esta conferência qualquer anexo da casa entrava cru no `.odt`
            # da certidão: o recibo do COAF, que só o ADMIN abre, inclusive.
            if (row and row["entity_type"] == RCT.ANEXO_DO_TERMO
                    and int(row["entity_id"] or 0) == int(assento_id)
                    and Path(row["stored_path"]).is_file()):
                return row["stored_path"]
        return None

    @app.route("/rcpn/<int:assento_id>/certidao/previa", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_certidao_previa(assento_id: int):
        """Prévia da certidão de inteiro teor — NÃO GRAVA.

        Mostra introdução + teor colado (ou o encaixe da imagem). Não inventa
        o texto do livro: se a caixa estiver vazia, a prévia diz o que falta.
        """
        with db.connect() as con:
            assento = banco(con).um("SELECT * FROM rc_assentos WHERE id=%s",
                                    (assento_id,))
            if not assento:
                flash("Assento não encontrado.", "danger")
                return redirect(url_for("rcpn_assentos"))
            lugar = RCE.lugar_do_assento(con, assento_id)
            atos_previa = banco(con).ler(
                "SELECT * FROM rc_atos WHERE assento_id=%s ORDER BY id",
                (int(assento_id),))
            # Mesma escolha da ficha (rcpn_assento): a folha sugerida
            # continua pré-selecionada, mas o oficial pode trocar por
            # qualquer outra em branco do estoque.
            folhas_disponiveis = PP.listar(con, situacao="EM BRANCO", limite=None)
            folha_sugerida_pp = PP.proxima_folha(con)
            folha_da_1a_via = _folha_da_1a_via(con, assento_id,
                                               assento["especie"])
        modo = RCIT.normalizar_modalidade(
            _campo("modalidade") or _campo("modo_inteiro"))
        tipo = (_campo("tipo_certidao") or "").strip().lower()
        if tipo in ("inteiro", "inteiro_teor") and modo == RCIT.RESUMO:
            modo = RCIT.normalizar_modalidade(
                _campo("modo_inteiro") or "texto")
        tem_img = bool((request.files.get("imagem_assento")
                        and request.files["imagem_assento"].filename)
                       or (_campo("anexo_imagem_id") or "").strip())
        # A INTRODUÇÃO É A DA CASA (LF06C): o papel e a peça do fim saem da
        # busca única, como na emissão (`rc_certidao.emitir`) — a prévia
        # mostra o texto que vai congelar. Só lê.
        with db.connect() as con, TEXTOS.lendo_da_casa(con):
            intro = RCIT.introducao(
                especie=assento["especie"], nome=assento["nome"],
                matricula=assento["matricula"],
                livro=lugar.get("livro") or lugar.get("livro_numero")
                      or assento["livro_volume"],
                folha=lugar.get("folha"),
                termo=lugar.get("termo") or assento["numero"],
                cns=sv().get("ri_cns"), cidade=sv().get("ri_cidade"),
                uf=sv().get("ri_uf"), modo=modo)
            html = RCIT.previa_html(
                modalidade=modo, introducao_txt=intro,
                teor_colado=_campo("teor_colado"), tem_imagem=tem_img,
                atos=atos_previa)
        with db.connect() as _con_sel:
            selagem = RCE.como_vai_selar(_con_sel, int(assento["id"]),
                                         especie=assento["especie"])
        return render_template(
            "rc_certidao_previa.html", assento=dict(assento),
            selagem=selagem,
            previa_html=html, modalidade=modo,
            teor_colado=_campo("teor_colado"),
            modo_inteiro=_campo("modo_inteiro"),
            tipo_certidao=_campo("tipo_certidao") or (
                "inteiro_teor" if RCIT.e_inteiro_teor(modo) else "resumo"),
            folhas_disponiveis=folhas_disponiveis,
            folha_sugerida=(folha_sugerida_pp["codigo"]
                           if folha_sugerida_pp else None),
            folha_da_1a_via=folha_da_1a_via,
            gratuidades=_gratuidades_da_certidao())

    def _folha_da_1a_via(con, assento_id: int, especie=None) -> dict | None:
        """A folha em que a 1a via TEM de sair, ou None. So LE.

        FOLHA_DA_1A_VIA_20261009 - pedido de uma escrevente (16 casos desde
        09/09/2026). A API do selador nao tem como informar ou retificar o
        papel depois (181 servicos, todos POST de gerar selo; `papelMoeda` e
        required no registro de nascimento/obito/natimorto/casamento). Entao a
        folha que foi ao TJMA no selo do registro E a folha da 1a via.

        None quando nao e 1a via, ou quando o registro nao tem folha baixada
        (assento antigo/importado com selo) - ai vale a escolha EM BRANCO, que
        agora da baixa na propria certidao.
        """
        if not RCE.eh_primeira_certidao_do_registro(
                con, int(assento_id), certidao_id=None,
                especie=str(especie or "").strip().upper() or None):
            return None
        return PP.folha_do_registro(con, int(assento_id))

    def _folha_seguranca_do_form() -> str:
        """Folha de seguranca do form: select ou digitada (IA 033467007).

        Preferencia pela digitada quando preenchida - e o numero que o escrevente
        leu no papel da gaveta. Aceita serie+numero; normaliza via papel_seguranca.
        """
        import papel_seguranca as _PP
        digitada = (_campo("folha_seguranca_digitada") or "").strip()
        escolhida = (_campo("folha_seguranca") or "").strip()
        bruto = digitada or escolhida
        return _PP.resolver_codigo(bruto)

    @app.route("/rcpn/<int:assento_id>/certidao", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")

    def rcpn_certidao_emitir(assento_id: int):
        """Emite a certidão do assento. ESCREVE.

        SAI DA FICHA, como a do RCPJ/RTD: é onde o escrevente está quando o
        cliente pede, e onde ele acabou de ver o que o assento diz.

        RESUMO: o teor se monta dos campos no modelo nacional do CNJ.
        INTEIRO TEOR: o oficial escolhe texto corrido (cola o teor) ou
        cópia reprográfica (imagem do livro) — não se inventa o registro.
        """
        volta = url_for("rcpn_assento", assento_id=assento_id)
        tipo = (_campo("tipo_certidao") or "resumo").strip().lower()
        if tipo in ("inteiro", "inteiro_teor"):
            modo = RCIT.normalizar_modalidade(
                _campo("modo_inteiro") or _campo("modalidade") or "texto")
        else:
            modo = RCIT.RESUMO
        img_path = None
        # O BOTÃO «EMITIR REPROGRÁFICA DA DIGITALIZAÇÃO» (problema #121): o
        # inteiro teor por cópia reprográfica sai do termo digitalizado
        # oficial, congelado pelo sha256 — e não da imagem enviada na hora.
        # Folha de segurança, gratuidade e selo seguem o caminho de sempre.
        usar_digi = (_campo("usar_digitalizacao") or "").strip() == "1"
        digi_congelada = None
        if usar_digi:
            modo = RCIT.INTEIRO_REPRO
            try:
                digi_congelada = RCDIGI.congelar_para_certidao(db, assento_id)
            except RCDIGI.DigitalizacaoError as erro:
                flash(str(erro), "danger")
                return redirect(volta)
            img_path = digi_congelada["path"]
        elif modo == RCIT.INTEIRO_REPRO:
            img_path = _imagem_da_certidao_inteiro(assento_id)

        # GRATUIDADE_SEM_MOTIVO — 10/09/2026, do relato «segue sem
        # funcionar, revise o caso do assento 1240».
        #
        # **MARCAR «SELO GRATUITO» SEM ESCREVER O MOTIVO DEIXAVA A CERTIDAO
        # LAVRADA SEM SELO.** Medido numa copia do banco do balcao, no assento
        # 1240: saía «Certidão n. 28/2026 emitida. O ato foi lavrado SEM SELO:
        # Ato gratuito / selo gratuito precisa do motivo escrito» — e a
        # certidao ficava, sem selo. É o desfecho das certidões 16, 17 e 23
        # por outro caminho.
        #
        # **A REGRA «SELAR NUNCA DERRUBA ATO QUE JÁ EXISTE» CONTINUA CERTA, E
        # NÃO É ESTE O CASO.** Ela vale para a recusa do APARELHO — balcão
        # parado é pior que selo atrasado, e ato com selo inventado é pior que
        # os dois. **Motivo em branco não é recusa do aparelho: é campo que o
        # operador não preencheu**, e isso se pega com ele ainda na tela.
        #
        # O precedente é desta mesma rota, de 09/09: a folha de segurança
        # passou a ser exigida antes de emitir, pelo mesmo motivo e pelo mesmo
        # caso.
        try:
            _gratuidade_do_form()
        except AS.AtoError as _erro_grat:
            flash(f"{_erro_grat} Escreva o motivo no campo «Motivo» do bloco "
                  "«Selo gratuito / isento», ou desmarque a caixa para o selo "
                  "sair pago.", "danger")
            return redirect(volta)

        # A BUSCA — pedido do oficial, 15/10/2026: o selo de busca vai junto
        # com a certidão, e a faixa vem sugerida pela data do registro. A 1ª
        # via NÃO leva busca: ela sai gratuita com o selo do próprio registro,
        # e ninguém busca o que acabou de ser lavrado. A recusa da escolha
        # vazia vem AQUI, antes de numerar, como a do motivo da gratuidade.
        with db.connect() as _con_bq:
            _busca_na_1a_via = RCE.eh_primeira_certidao_do_registro(
                _con_bq, assento_id, especie=_especie_do_assento(assento_id))
        busca = None
        if not _busca_na_1a_via:
            try:
                busca = _busca_do_form("RCPN")
            except BU.BuscaError as _erro_busca:
                flash(str(_erro_busca), "danger")
                return redirect(volta)

        # **ESTA VEM ANTES DA FOLHA**, e por uma razão medida: a
        # guarda da folha é pulada na 1ª via (`_ja_primeira`), e a
        # gratuidade sem motivo tem de ser recusada nas duas.
        # FOLHA_SEGURANCA_OBRIGATORIA_CERT — 09/09/2026
        # 2a via (CERTID) gasta folha; sem escolha na tela o ato ficava
        # gravado SEM SELO (incidente da cert. 16). Bloqueia antes de emitir.
        # FOLHA OBRIGATÓRIA EM TODA EMISSÃO — relato #92, 22/09/2026: escolha
        # manual do papel de segurança, inclusive 1ª via; não pega sozinha a
        # «próxima da gaveta» sem o escrevente dizer qual folha está na mão.
        _folha_g = _folha_seguranca_do_form()
        # FOLHA_DA_1A_VIA_20261009: na 1a via vale a folha do REGISTRO - a que
        # o escrevente escolheu na conferencia, que foi baixada e foi ao TJMA
        # no `papelMoeda`. Outra folha aqui e exatamente o defeito dos 16
        # casos: imprimir numa e o sistema/TJMA ficarem com outra.
        with db.connect() as _con_1a:
            _folha_1a = _folha_da_1a_via(_con_1a, assento_id,
                                         _especie_do_assento(assento_id))
        if _folha_1a:
            if _folha_g and PP.resolver_codigo(_folha_g) != PP.resolver_codigo(
                    _folha_1a["codigo"]):
                flash(
                    f"A 1ª via sai na folha {_folha_1a['codigo']}: é a "
                    "folha baixada no registro e informada ao TJMA no selo. "
                    f"A folha {_folha_g} não foi usada. Se a folha do "
                    "registro se perdeu, fale com o oficial antes de emitir.",
                    "danger")
                return redirect(volta)
            _folha_g = _folha_1a["codigo"]
        else:
            if not _folha_g:
                flash(
                    "Escolha a folha de segurança antes de emitir a certidão. "
                    "Sem folha escolhida o sistema não emite.",
                    "danger")
                return redirect(volta)
            import papel_seguranca as _PP_g
            with db.connect() as _con_g2:
                _lf = _PP_g.ler(_con_g2, _folha_g)
                if not _lf or _lf["situacao"] != "EM BRANCO":
                    flash(
                        f"A folha {_folha_g} não está em branco no estoque. "
                        "Escolha outra folha de segurança.",
                        "danger")
                    return redirect(volta)

        try:
            with db.transaction() as con:
                r = RCE.emitir(
                    con, assento_id, sv=sv(), hoje=hoje(),
                    agora=agora(), data_extenso=hoje_extenso(),
                    requerente=_campo("requerente") or None,
                    finalidade=_campo("finalidade") or None,
                    usuario=usuario_nome(),
                    modalidade=modo,
                    teor_colado=_campo("teor_colado") or None,
                    imagem_caminho=img_path,
                    imagem_largura_cm=_float_campo(
                        "imagem_largura_cm", RCIT.LARGURA_CM_PADRAO),
                    imagem_altura_cm=_float_campo("imagem_altura_cm"),
                    imagem_margem_esq_cm=_float_campo(
                        "imagem_margem_esq_cm", RCIT.MARGEM_ESQ_CM_PADRAO),
                    imagem_margem_sup_cm=_float_campo(
                        "imagem_margem_sup_cm", RCIT.MARGEM_SUP_CM_PADRAO),
                )
                if digi_congelada:
                    RCDIGI.marcar_certidao(con, r["certidao_id"],
                                           digi_congelada["sha256"])
                esp = _especie_do_assento(assento_id)
                primeira = RCE.eh_primeira_certidao_do_registro(
                    con, assento_id, certidao_id=r["certidao_id"], especie=esp)
                if primeira:
                    selo_reg = RCE.espelhar_selo_do_registro_na_certidao(
                        con, r["certidao_id"], assento_id)
                    if selo_reg:
                        aviso = (
                            f" 1ª certidão gratuita: selo do registro "
                            f"{selo_reg} (sem CERTID)."
                        )
                        # FOLHA_DA_1A_VIA_20261009: a folha da 1a via fica
                        # registrada. A do registro so se AMARRA (ja esta
                        # USADA e ja foi ao TJMA - sem baixa dupla); sem folha
                        # no registro, a escolhida EM BRANCO e baixada aqui.
                        if _folha_1a:
                            PP.vincular_primeira_via(
                                con, _folha_1a["codigo"],
                                certidao_id=r["certidao_id"], agora=agora(),
                                selo=selo_reg, usuario=usuario_nome())
                            aviso += (f" Folha de segurança "
                                      f"{_folha_1a['codigo']} (a do registro, "
                                      f"informada ao TJMA).")
                        else:
                            PP.usar(con, _folha_g, tabela="rc_certidoes",
                                    ato_id=r["certidao_id"], selo=selo_reg,
                                    agora=agora(), usuario=usuario_nome())
                            aviso += (f" Folha de segurança {_folha_g} "
                                      f"baixada nesta 1ª via.")
                    else:
                        raise RCE.CertidaoRCPNError(
                            "A 1ª certidão de nascimento/óbito/natimorto é "
                            "gratuita e usa o selo do REGISTRO — mas este "
                            "assento ainda não tem selo no registro. "
                            "Sele o registro antes de emitir a 1ª certidão; "
                            "não use CERTID/segunda-via."
                        )
                    # Nao cobra item de certidao paga na 1a via.
                else:
                    aviso = _selar_se_pedido(con, "rc_certidoes",
                                             r["certidao_id"], "RCPN")
                    cob_msg = _cobrar_se_pedido(con, "rc_certidoes",
                                               r["certidao_id"], "CERTIDAO",
                                               busca=busca)
        except (RCE.CertidaoRCPNError, AS.AtoError, RCIT.InteiroTeorError,
                PP.PapelError) as erro:
            flash(str(erro), "danger")
            return redirect(volta)
        esp = _especie_do_assento(assento_id)
        with db.connect() as _con_chk:
            primeira = RCE.eh_primeira_certidao_do_registro(
                _con_chk, assento_id, certidao_id=r["certidao_id"], especie=esp)
        # O QUE O `if` NÃO GARANTE — problema #84, 18/09/2026.
        #
        # `recado_do_selo` e `cob_msg` nasceram SÓ no ramo da 2ª via, e o da 1ª
        # via caía direto no `_motivo_da_falha_do_selo(recado_do_selo)` sem eles:
        # `UnboundLocalError` DEPOIS de a certidão já estar gravada — o balcão
        # lia «erro» sobre um ato praticado. Medido na produção, assento 8283:
        # a 1ª via (gratuita, selo REGNAS do registro) subiu com erro e ficou
        # sem uma linha de auditoria; o 2º clique já não era a 1ª e comprou um
        # `CERTID`, gastando folha de segurança — dinheiro que não era devido.
        #
        # A REGRA DA 1ª VIA NÃO MORA SÓ AQUI: `_selar_o_ato` também a conhece
        # (espelha o REGNAS e recusa se o registro não tem selo). Este ramo
        # existe para NÃO chamar o aparelho nem tocar em folha na via gratuita,
        # e por isso não passa por lá.
        #
        # E `cob_msg` TEM DE NASCER AQUI TAMBÉM: ele nasce no `else` de dentro
        # da transação, e se as duas leituras de `primeira` discordarem o
        # `else` de baixo o leria sem valor — a mesma falha, uma linha depois.
        recado_do_selo = ""
        cob_msg = ""
        if primeira:
            # Ja espelhou o REGNAS; nao chama o aparelho para CERTID.
            # Folha de seguranca: se o escrevente escolheu, o guard / impressao
            # usam o selo do registro — sem comprar segunda-via.
            pass
        else:
            recado_do_selo = _selar_o_ato(
                "rc_certidoes", r["certidao_id"], "CERTIDAO", "RCPN", aviso,
                especie=esp,
                folha_escolhida=_folha_seguranca_do_form() or None,
                busca=busca)
            aviso = (recado_do_selo or "") + cob_msg
        motivo_selo = _motivo_da_falha_do_selo(recado_do_selo)
        if motivo_selo:
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE rc_certidoes
                          SET cancelada_em=%s, cancelada_por=%s,
                              cancelada_motivo=%s
                        WHERE id=%s""",
                    (agora(), usuario_nome(),
                     f"Selo não emitido: {motivo_selo}", r["certidao_id"]))
            audit("RCPN_CERTIDAO_NAO_EMITIDA_SELO_FALHOU",
                  "rc_certidoes", r["certidao_id"],
                  {"numero": r["numero"], "ano": r["ano"],
                   "hash": r["hash"], "motivo": motivo_selo,
                   "modalidade": r.get("modalidade", modo)})
            flash("Certidão NÃO emitida: o selo não saiu. "
                  f"Motivo: {motivo_selo}. Corrija o problema do "
                  "selo e tente de novo.",
                  "danger")
            return redirect(volta)
        audit("RCPN_CERTIDAO", "rc_certidoes", r["certidao_id"],
              {"numero": r["numero"], "ano": r["ano"], "hash": r["hash"],
               "modalidade": r.get("modalidade", modo),
               # A BUSCA ESCOLHIDA FICA AQUI, inclusive o «.9», que não vira
               # selo: é onde a correição acha por que não se cobrou.
               **({"busca": busca} if busca else {}),
               **({"digitalizacao_sha256": digi_congelada["sha256"]}
                  if digi_congelada else {})})
        flash(f"Certidão n. {r['numero']}/{r['ano']} emitida.{aviso}",
              "success")
        return redirect(url_for("rcpn_certidao",
                                certidao_id=r["certidao_id"]))

    # A CERTIDÃO ELETRÔNICA DA CRC — 22/10/2026, o oficial: «no roteiro para
    # emitir certidão da CRC eletrônica precisa colocar na central o número do
    # selo, antes de subir o arquivo de importação. Nesse momento as
    # escreventes estão gerando o selo fora. Vamos criar um botão no registro
    # para emitir o número do selo da certidão eletrônica dentro do sistema
    # para copiar manualmente para a CRC».
    #
    # O PRECEDENTE É DESTA CASA, medido no acervo do E-Ofício (2023): a segunda
    # via da espécie com o item 14.5.7 — «Certidão Eletrônica com buscas e
    # folhas excedentes incluídas» —, e o selo volta com o prefixo CERELE.
    # A FOLHA DE SEGURANÇA NÃO VAI: a eletrônica não se imprime em papel, e o
    # contrato do selador a declara opcional (`DadosSegundaViaCertidao`). Em
    # 2023 o E-Ofício ainda mandava uma folha marcada «utilizado: false»; aqui
    # não vai nenhuma — se o aparelho recusar, a recusa sobe à tela e nada se
    # gasta.
    #
    # A CERTIDÃO SE GRAVA, como as outras (numeração do exercício, teor
    # congelado): ela é certidão desta casa, e o selo se amarra a ela. O selo
    # passa pela mesma trava do selo pago (o protocolo em atendimento), e o
    # que não sela cancela a certidão, como na emissão de sempre.
    #
    # O VALOR VEM PELA CRC, e não pelo caixa (o oficial, no mesmo dia): a
    # trava do selo pago a reconhece pela finalidade gravada e pelo item
    # (`ato_selado.e_certidao_eletronica_da_crc`, forma CENTRAL_CRC).
    CODIGO_CERTIDAO_ELETRONICA = AS.CODIGO_CERTIDAO_ELETRONICA_CRC
    FINALIDADE_CERTIDAO_ELETRONICA = AS.FINALIDADE_CERTIDAO_ELETRONICA_CRC

    @app.route("/rcpn/<int:assento_id>/certidao-eletronica/selo",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_certidao_eletronica_selo(assento_id: int):
        """Emite o selo da certidão eletrônica da CRC (14.5.7), para copiar na
        Central antes de subir o arquivo. ESCREVE (a certidão e o selo) e
        FALA COM A REDE (o selador), fora da transação."""
        import selo_robo as SR
        volta = url_for("rcpn_assento", assento_id=assento_id)
        if not SR.pode_selar_automatico():
            flash(SR.recado_pendente_selo(), "danger")
            return redirect(volta)
        try:
            _grat_cod, motivo_selo, selo_isento = _gratuidade_do_form()
        except AS.AtoError as erro:
            flash(f"{erro} Escreva o motivo, ou desmarque «selo isento».",
                  "danger")
            return redirect(volta)
        esp = _especie_do_assento(assento_id)
        try:
            with db.transaction() as con:
                r = RCE.emitir(
                    con, assento_id, sv=sv(), hoje=hoje(), agora=agora(),
                    data_extenso=hoje_extenso(),
                    requerente=_campo("requerente") or None,
                    finalidade=FINALIDADE_CERTIDAO_ELETRONICA,
                    usuario=usuario_nome(), modalidade=RCIT.RESUMO)
        except (RCE.CertidaoRCPNError, AS.AtoError) as erro:
            flash(str(erro), "danger")
            return redirect(volta)
        certidao_id = int(r["certidao_id"])
        try:
            # O CAMINHO GERAL, E SÓ PARA ESTE SELO — 23/10/2026: pela segunda
            # via o aparelho exige a folha de segurança, que a certidão
            # eletrônica não usa (ver AS.CAMINHO_CERTIDAO_ELETRONICA_CRC).
            with db.connect() as con:
                doc = banco(con).um(
                    "SELECT nome, cpf_registrado FROM rc_assentos WHERE id=%s",
                    (assento_id,))
            envelope = AS.envelope_da_certidao_eletronica_crc(
                nome_parte=(doc["nome"] if doc else ""),
                documento=(doc["cpf_registrado"] if doc else None),
                escrevente=usuario_nome(),
                versao_tabela=AS.versao_da_tabela_de_custas(
                    AS.CAMINHO_CERTIDAO_ELETRONICA_CRC,
                    db.get_setting("selo_tabela_custas_em", "")),
                isento=selo_isento, motivo_isencao=motivo_selo)
            res = AS.selar_o_ato_lavrado(
                db, Path(app.config["DATA_DIR"]), tabela="rc_certidoes",
                ato_id=certidao_id, tipo="CERTIDAO", atribuicao="RCPN",
                agora=agora(), cns=sv().get("ri_cns"), usuario=usuario_nome(),
                especie=esp, dados=envelope,
                caminho=AS.CAMINHO_CERTIDAO_ELETRONICA_CRC,
                referencia=(f"rc_certidoes:{certidao_id}:"
                            f"{CODIGO_CERTIDAO_ELETRONICA}:1"))
        except (AS.AtoError, sqlite3.Error) as erro:
            res = {"selado": False, "motivo": str(erro)}
        if not res.get("selado") or not res.get("numero"):
            motivo = str(res.get("motivo") or "o selador não devolveu número")
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE rc_certidoes
                          SET cancelada_em=%s, cancelada_por=%s,
                              cancelada_motivo=%s
                        WHERE id=%s""",
                    (agora(), usuario_nome(), f"Selo não emitido: {motivo}",
                     certidao_id))
            audit("RCPN_CERTIDAO_ELETRONICA_SELO_FALHOU", "rc_certidoes",
                  certidao_id, {"numero": r["numero"], "ano": r["ano"],
                                "motivo": motivo})
            extra = ""
            flash(f"O selo da certidão eletrônica NÃO saiu: {motivo}.{extra}",
                  "danger")
            return redirect(volta)
        audit("RCPN_CERTIDAO_ELETRONICA_CRC", "rc_certidoes", certidao_id,
              {"numero": r["numero"], "ano": r["ano"], "hash": r["hash"],
               "selo": res["numero"], "codigo": CODIGO_CERTIDAO_ELETRONICA,
               "isento": bool(selo_isento)})
        # O QUE SE COPIA PARA A CRC — 23/10/2026: além do número, o código de
        # validação e a linha de valores. A linha sai do texto do selo; o
        # código, do que o aparelho devolveu além do número, como veio.
        import selo_no_papel as SP
        with db.connect() as con:
            t = banco(con).um("SELECT texto FROM sd_selos WHERE numero=%s",
                              (res["numero"],))
        valores = SP.linha_de_valores((t["texto"] if t else "") or "")
        flash(f"Selo da certidão eletrônica: {res['numero']} — copie-o para a "
              f"CRC antes de subir o arquivo. "
              + (f"Valores: {valores}. " if valores else "")
              + _recado_do_codigo_de_validacao(res["numero"], res.get("extras"))
              + f"Certidão n. {r['numero']}/{r['ano']} registrada com ele.",
              "success")
        return redirect(url_for("rcpn_certidao", certidao_id=certidao_id))

    def _recado_do_codigo_de_validacao(numero: str, extras) -> str:
        """A frase do aviso com o código de validação do selo. ESCREVE
        (guarda o código em `sd_selos.qr_token`).

        O CÓDIGO É O `valorQrCode` — medido na resposta do aparelho em
        26/10/2026: o resumo traz `valorQrCode` (24 caracteres, o mesmo
        `strvalorQRCode` do acervo) e `qrCode`, que é a IMAGEM do QR em base64
        (~660 caracteres). O aviso mostrava os dois crus; agora mostra o
        código com o nome dele, e a imagem não vai para a tela. O código fica
        guardado em `sd_selos.qr_token`, a coluna dele, que ficou vazia desde a
        carga — e NÃO vai para o papel: o oficial, em 23/10/2026, «não precisa
        colocar na certidão»."""
        resto = dict(extras or {})
        codigo = str(resto.pop("valorQrCode", "") or "").strip()
        resto.pop("qrCode", None)
        if codigo:
            try:
                with db.transaction() as con:
                    banco(con).escrever(
                        """UPDATE sd_selos SET qr_token=%s
                            WHERE numero=%s AND COALESCE(qr_token, '')=''""",
                        (codigo, numero))
            except sqlite3.Error:
                # O código já está no aviso; perder a cópia no razão não
                # desfaz o selo, mas fica no registro para quem conferir.
                app.logger.exception("código de validação do selo %s", numero)
        outros = "; ".join(f"{k}: {v}" for k, v in resto.items()
                           if str(v or "").strip())
        frase = ""
        if codigo:
            frase += f"Código de validação: {codigo}. "
        if outros:
            frase += f"O selador devolveu também: {outros}. "
        if not frase:
            frase = "O selador não devolveu código de validação nesta resposta. "
        return frase

    # A MATERIALIZAÇÃO DE CERTIDÃO DE OUTRA SERVENTIA — 26/10/2026, o oficial:
    # «assim como criamos o emissor de selo para certidão eletrônica de
    # registro do cartório, preciso que o sistema emita selo para a
    # materialização de certidão vinda de outros cartórios para entrega a
    # clientes». Item 14.5.1 e pagamento no caixa (decisões dele): o selo
    # passa pela trava de sempre, com o protocolo em atendimento.
    @app.route("/rcpn/materializacoes")
    @login_required
    def rcpn_materializacoes():
        """O formulário e as materializações já seladas. Só LÊ."""
        import rc_materializacao as RCM
        with db.connect() as con:
            linhas = RCM.listar(con, limite=100)
        return render_template("rc_materializacoes.html", linhas=linhas,
                               codigo_ato=RCM.CODIGO_ATO)

    @app.route("/rcpn/materializacoes", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_materializacao_selar():
        """Registra a materialização e pede o selo. ESCREVE (a materialização
        e o selo) e FALA COM A REDE (o selador), fora da transação."""
        import rc_materializacao as RCM
        import selo_robo as SR
        volta = url_for("rcpn_materializacoes")
        if not SR.pode_selar_automatico():
            flash(SR.recado_pendente_selo(), "danger")
            return redirect(volta)
        try:
            _grat_cod, motivo_selo, selo_isento = _gratuidade_do_form()
        except AS.AtoError as erro:
            flash(f"{erro} Escreva o motivo, ou desmarque «selo isento».",
                  "danger")
            return redirect(volta)
        dados = {k: _campo(k) for k in (
            "nome_parte", "requerente", "cartorio_nome", "cartorio_cidade",
            "cartorio_uf", "funcionario_expedidor", "valor_emolumentos",
            "especie", "matricula")}
        # O ENVELOPE SE MONTA ANTES DE GRAVAR: o que falta no formulário ou no
        # cadastro (a versão da tabela) recusa aqui, sem deixar materialização
        # cancelada para trás.
        try:
            conferido = RCM.conferir(dados)
            envelope = RCM.envelope(
                conferido, escrevente=usuario_nome(),
                versao_tabela=AS.versao_da_tabela_de_custas(
                    RCM.CAMINHO, db.get_setting("selo_tabela_custas_em", "")),
                isento=selo_isento, motivo_isencao=motivo_selo)
            with db.transaction() as con:
                mid = RCM.registrar(con, dados, agora=agora(),
                                    usuario=usuario_nome())
        except RCM.MaterializacaoError as erro:
            flash(str(erro), "danger")
            return redirect(volta)
        try:
            res = AS.selar_o_ato_lavrado(
                db, Path(app.config["DATA_DIR"]), tabela=RCM.TABELA,
                ato_id=mid, tipo="MATERIALIZACAO", atribuicao="RCPN",
                agora=agora(), cns=sv().get("ri_cns"), usuario=usuario_nome(),
                dados=envelope, caminho=RCM.CAMINHO,
                referencia=f"{RCM.TABELA}:{mid}:{RCM.CODIGO_ATO}:1")
        except (AS.AtoError, sqlite3.Error) as erro:
            res = {"selado": False, "motivo": str(erro)}
        if not res.get("selado") or not res.get("numero"):
            motivo = str(res.get("motivo") or "o selador não devolveu número")
            with db.transaction() as con:
                RCM.cancelar(con, mid, motivo=f"Selo não emitido: {motivo}",
                             agora=agora(), usuario=usuario_nome())
            audit("RCPN_MATERIALIZACAO_SELO_FALHOU", RCM.TABELA, mid,
                  {"motivo": motivo})
            flash(f"O selo da materialização NÃO saiu: {motivo}.", "danger")
            return redirect(volta)
        audit("RCPN_MATERIALIZACAO_SELADA", RCM.TABELA, mid,
              {"selo": res["numero"], "codigo": RCM.CODIGO_ATO,
               "isento": bool(selo_isento)})
        import selo_no_papel as SP
        with db.connect() as con:
            t = banco(con).um("SELECT texto FROM sd_selos WHERE numero=%s",
                              (res["numero"],))
        valores = SP.linha_de_valores((t["texto"] if t else "") or "")
        flash(f"Selo da materialização: {res['numero']}. "
              + (f"Valores: {valores}. " if valores else "")
              + _recado_do_codigo_de_validacao(res["numero"], res.get("extras")),
              "success")
        return redirect(volta)

    @app.route("/rcpn/certidoes")
    @login_required
    def rcpn_certidoes():
        """As certidões do Registro Civil emitidas, e a busca do balcão.

        A BUSCA VEM JUNTO porque a pergunta do guichê é "a certidão de
        fulano", e não "o assento 84 do Livro A-3". Quem chega pedindo
        certidão dá o nome, e mais nada.
        """
        termo = (request.args.get("q") or "").strip()
        with db.connect() as con:
            achados = RCE.buscar(con, termo) if termo else []
            linhas = RCE.listar(con, limite=100)
        return render_template("rc_certidoes.html", linhas=linhas,
                               achados=achados, termo=termo)

    @app.route("/rcpn/certidoes/<int:certidao_id>")
    @login_required
    def rcpn_certidao(certidao_id: int):
        """A certidão como saiu — para conferir, imprimir e reimprimir."""
        with db.connect() as con:
            linha = RCE.ler(con, certidao_id)
            if not linha:
                flash("Certidão não encontrada.", "danger")
                return redirect(url_for("rcpn_certidoes"))
            certidao = dict(linha)
        return render_template("rc_certidao.html", certidao=certidao)

    def _odt_preenchido_da_certidao(certidao_id: int):
        """O molde ODT com os @ da certidao. SÓ LÊ."""
        with db.connect() as con:
            linha = RCE.ler(con, certidao_id)
            if not linha:
                abort(404)
            certidao = dict(linha)
            selos = []
            try:
                selos = banco(con).ler(
                    """SELECT numero, texto FROM sd_selos
                        WHERE tabela='rc_certidoes' AND ato_id=%s
                        ORDER BY id""", (certidao_id,))
            except sqlite3.Error:
                selos = []
            if not selos and (certidao.get("selo") or "").strip():
                row = banco(con).um(
                    "SELECT numero, texto FROM sd_selos WHERE numero=%s",
                    (certidao["selo"],))
                if row:
                    selos = [dict(row)]
            certidao["selos"] = selos
            if selos:
                certidao["selo_texto"] = selos[0].get("texto") or ""
            # Emitente e localização do assento — a via de inteiro teor assina
            # quem emitiu (não só o titular) e mostra LIVRO/FOLHA/TERMO no
            # cabeçalho Notas. Só LÊ.
            emitente = (certidao.get("emitida_por") or "").strip()
            if emitente and not certidao.get("emitida_funcao"):
                u = banco(con).um(
                    "SELECT funcao FROM users WHERE full_name=%s "
                    "OR lower(username)=lower(%s) ORDER BY id LIMIT 1",
                    (emitente, emitente))
                if u and (u["funcao"] or "").strip():
                    certidao["emitida_funcao"] = u["funcao"].strip()
            if not (certidao.get("livro") or certidao.get("folha") or certidao.get("termo")):
                ass = banco(con).um(
                    "SELECT numero, livro_volume, dados_json FROM rc_assentos WHERE id=%s",
                    (certidao.get("assento_id"),))
                if ass:
                    import json as _json
                    try:
                        dj = _json.loads(ass["dados_json"] or "{}")
                    except Exception:
                        dj = {}
                    certidao.setdefault("livro", dj.get("livro") or ass["livro_volume"] or "")
                    certidao.setdefault("folha", dj.get("folha") or "")
                    certidao.setdefault("termo", dj.get("termo") or ass["numero"] or "")
            quadro = RCQ.quadro_da_certidao(con, certidao, sv())
        # INTEIRO TEOR: ODT próprio (texto ou imagem), sem o quadro CNJ.
        if RCIT.e_inteiro_teor(certidao.get("modalidade")):
            img_bytes = None
            caminho = (certidao.get("imagem_caminho") or "").strip()
            if caminho and Path(caminho).is_file():
                img_bytes = Path(caminho).read_bytes()
            try:
                # A VIA QUE SAIU DO TERMO DIGITALIZADO (problema #121) monta as
                # páginas do PDF/TIFF uma por folha; a antiga, uma foto só.
                if (certidao.get("digitalizacao_sha256") or "").strip():
                    arquivo = RCDIGI.odt_da_certidao(
                        certidao, sv(), hoje_extenso=hoje_extenso())
                else:
                    arquivo = RCIT.arquivo_odt(
                        certidao, sv(), hoje_extenso=hoje_extenso(),
                        imagem_bytes=img_bytes)
            # ValueError: a recusa do inteiro teor, a da digitalização e a do
            # leitor do PDF (`ri_digitalizacao.paginas_png`) — todas de regra.
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_certidao",
                                        certidao_id=certidao_id)), None
        else:
            # ERRO DE REGRA NAO E HTTP 500 — o molde recusa a especie que ele nao
            # serve, e quem esta no balcao precisa da frase, nao de uma tela de
            # erro. Ver `rc_certidao_odt.ESPECIES_QUE_O_MOLDE_SERVE`.
            try:
                # O PAPEL AJUSTADO PELA CASA, quando ha um — pedido do oficial
                # em 10/09/2026 («atualizar esses modelos no modulo de
                # modelos, para poder editar por la»). Sem linha em
                # `mo_moldes` sai o `.odt` do pacote: o codigo e o piso.
                _chave_molde = MOLDES_ODT.chave_da_especie(
                    (quadro or {}).get("especie"))
                _molde_bytes = None
                if _chave_molde:
                    with db.connect() as _con_m:
                        _molde_bytes = MOLDES_ODT.arquivo_que_vale(
                            _con_m, _chave_molde)
                arquivo = RCODT.arquivo_da_certidao(
                    quadro, certidao, sv(), molde_bytes=_molde_bytes)
            except MOLDES_ODT.PapelError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_certidao",
                                        certidao_id=certidao_id)), None
            except RCODT.MoldeError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_certidao",
                                        certidao_id=certidao_id)), None
        # O BOTAO ENTREGA PDF; `?formato=odt` devolve o editavel. Decisao do
        # oficial em 01/09/2026, e ela mora em `impressao_web` — uma so para
        # os sete papeis da casa.
        nome = f"certidao-rcpn-{linha['numero']}-{linha['ano']}"
        return IMPW.resposta_do_papel(
            arquivo, nome=nome, get_setting=db.get_setting,
            voltar_para=url_for("rcpn_certidao", certidao_id=certidao_id)), linha

    @app.route("/rcpn/certidoes/<int:certidao_id>/imprimir")
    @login_required
    def rcpn_certidao_imprimir(certidao_id: int):
        """A certidao no ODT da casa, para o oficial abrir e imprimir. SÓ LÊ.

        O botao Imprimir baixa o molde preenchido. O HTML antigo
        (rcpn_certidao_impressa.html) nao sai mais neste caminho — e foi
        apagado no LF06C, porque nenhuma rota o desenhava mais.
        """
        resp, linha = _odt_preenchido_da_certidao(certidao_id)
        # RECUSA NAO SE AUDITA COMO EMISSAO: nao saiu papel nenhum, e
        # registrar «certidao emitida» aqui seria carimbo que mente.
        if linha is None:
            return resp
        audit("RCPN_CERTIDAO_ODT", "rc_certidoes", certidao_id,
              {"numero": linha["numero"], "ano": linha["ano"],
               "via": "imprimir"})
        return resp

    @app.route("/rcpn/certidoes/<int:certidao_id>/odt")
    @login_required
    def rcpn_certidao_odt(certidao_id: int):
        """A certidao no ODT da casa: o molde, so os @ preenchidos."""
        resp, linha = _odt_preenchido_da_certidao(certidao_id)
        if linha is None:
            return resp
        audit("RCPN_CERTIDAO_ODT", "rc_certidoes", certidao_id,
              {"numero": linha["numero"], "ano": linha["ano"]})
        return resp

    @app.route("/rcpn/certidoes/<int:certidao_id>/cancelar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_certidao_cancelar(certidao_id: int):
        """Cancela a certidão emitida. ESCREVE. O teor fica."""
        try:
            with db.transaction() as con:
                resultado = RCE.cancelar(
                    con, certidao_id, motivo=_campo("motivo"),
                    agora=agora(), usuario=usuario_nome(),
                    selo_cancelado_tjma=_campo("selo_cancelado_tjma"))
        except RCE.CertidaoRCPNError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_certidao", certidao_id=certidao_id))
        audit("RCPN_CERTIDAO_CANCELADA", "rc_certidoes", certidao_id,
              {"motivo": _campo("motivo"), "declaracao_selo_tjma": True,
               **resultado})
        folhas = resultado.get("folhas_recuperadas") or []
        recado = (f" Folha(s) {', '.join(folhas)} devolvida(s) ao estoque."
                  if folhas else "")
        flash("Certidão cancelada. O teor fica guardado." + recado, "success")
        return redirect(url_for("rcpn_certidao", certidao_id=certidao_id))

    # ----------------------------------------------------------- RCPJ e RTD

    @app.route("/rcpj-rtd")
    @login_required
    def rcpj_rtd_registros():
        """Os registros de pessoa jurídica e de títulos e documentos."""
        return render_template("atrib_lista.html", **_listar("rcpj_rtd"))

    @app.route("/rcpj-rtd/atos")
    @login_required
    def rcpj_rtd_ultimos_atos():
        """Os últimos atos praticados — registro, averbação e cancelamento
        juntos, das duas atribuições, na ordem em que foram lavrados.

        Achado do oficial em 12/09/2026: «não encontrei as averbações que
        fiz sem precisar abrir o registro». `/rcpj-rtd` lista os REGISTROS,
        ordenados por quando o registro foi ABERTO — uma averbação lançada
        hoje num registro de 2011 não sobe nessa lista, porque quem decide a
        posição é a idade do registro, não a do ato. Esta tela lê `rg_atos`
        direto, ordenada pelo `id` do ATO (a ordem em que cada um foi
        praticado), com o vínculo para abrir o registro de onde ele saiu.
        """
        POR_PAGINA_ATOS = 50
        pagina = _inteiro(request.args.get("pagina"), maximo=PAGINA_MAIS_ALTA) or 1
        atribuicao = (request.args.get("atribuicao") or "").strip()
        tipo = (request.args.get("tipo") or "").strip()
        onde, params = [], []
        if atribuicao in ("3", "4"):
            onde.append("r.atribuicao = %s")
            params.append(int(atribuicao))
        if tipo in ("REGISTRO", "AVERBACAO", "CANCELAMENTO"):
            onde.append("a.tipo = %s")
            params.append(tipo)
        filtro = (" WHERE " + " AND ".join(onde)) if onde else ""
        with db.connect() as con:
            total = int(banco(con).valor(
                f"""SELECT COUNT(*) n FROM rg_atos a
                      JOIN rg_registros r ON r.id = a.registro_id{filtro}""",
                params))
            atos = banco(con).ler(
                f"""SELECT a.id, a.tipo, a.data_ato, a.numero_ordem,
                           a.rotulo, a.folha, a.selo, a.registro_id,
                           r.numero AS registro_numero, r.serie,
                           r.atribuicao, r.requerente_nome, r.natureza
                      FROM rg_atos a
                      JOIN rg_registros r ON r.id = a.registro_id
                      {filtro}
                     ORDER BY a.id DESC
                     LIMIT %s OFFSET %s""",
                params + [POR_PAGINA_ATOS, (pagina - 1) * POR_PAGINA_ATOS])
        paginas = max(1, -(-total // POR_PAGINA_ATOS))
        return render_template(
            "atrib_rcpj_rtd_ultimos_atos.html", atos=atos, total=total,
            pagina=pagina, paginas=paginas, atribuicao=atribuicao, tipo=tipo)

    @app.route("/rcpj-rtd/novo", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpj_rtd_registro_novo():
        """Abre registro novo de pessoa jurídica ou de título e documento.

        AQUI A SÉRIE É ESCOLHIDA, e no RCPN não. Não é incoerência: no RCPN a
        espécie do fato manda no livro — nascimento vai no A, óbito no C —, e
        no RCPJ/RTD é a natureza jurídica do que se registra que decide qual
        livro recebe, e quem a conhece é quem está atendendo.

        A ATRIBUIÇÃO NÃO SE PERGUNTA: vem da série, em `livro_nucleo.SERIES`.
        Dois lugares não podem discordar de a qual atribuição uma série
        pertence.
        """
        def tela():
            series = [{"codigo": c, "nome": LN.serie(c).nome,
                       "atribuicao": "RCPJ" if c in RG.SERIES_RCPJ else "RTD"}
                      for c in RG.SERIES_CONHECIDAS]
            with db.connect() as con:
                contexto = _para_cobrar(con, "rg_atos", "REGISTRO")
            return render_template("atrib_registro_novo.html", series=series,
                                   form=request.form,
                                   declaracoes_do_termo=RG.DECLARACOES_POR_SERIE,
                                   **contexto)

        if request.method != "POST":
            return tela()

        try:
            with db.transaction() as con:
                # as declarações do termo do livro (LD09) — o extrato do
                # Livro C, a inscrição da PJ, a matrícula do periódico
                r = RG.abrir_registro(
                    con, serie=_campo("serie"), sv=sv(), agora=agora(),
                    data_extenso=hoje_extenso(),
                    natureza=_campo("natureza") or None,
                    requerente_nome=_campo("requerente_nome") or None,
                    requerente_documento=_campo("requerente_documento") or None,
                    teor=_campo("teor") or None, usuario=usuario_nome(),
                    declaracoes=RG.declaracoes_do_formulario(request.form))
                # A sigla vem da série escolhida — RCPJ e RTD compartilham a
                # tela, e hardcodar «RTD» gravaria selo mentiroso no RCPJ.
                serie = _campo("serie")
                sigla = "RCPJ" if serie in RG.SERIES_RCPJ else "RTD"
                aviso = _selar_se_pedido(con, "rg_atos", r["ato_id"], sigla)
                cob_msg = _cobrar_se_pedido(con, "rg_atos", r["ato_id"],
                                           "REGISTRO")
        except (RG.RgError, AS.AtoError) as erro:
            flash(str(erro), "danger")
            return tela()
        # Selo automático depois da lavratura — como no RCPN. Sem item/
        # protocolo a selar, _selar_o_ato explica e não inventa número.
        recado_do_selo = _selar_o_ato(
            "rg_atos", r["ato_id"], "REGISTRO", sigla, aviso, especie=serie)
        aviso = (recado_do_selo or "") + cob_msg
        motivo_selo = _motivo_da_falha_do_selo(recado_do_selo)
        if motivo_selo:
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE rg_atos
                          SET motivo_cancelamento=%s
                        WHERE id=%s""",
                    (f"Selo não emitido: {motivo_selo}", r["ato_id"]))
                banco(con).escrever(
                    """UPDATE rg_registros
                          SET situacao='CANCELADO'
                        WHERE id=%s""",
                    (r["registro_id"],))
            audit("RG_REGISTRO_NAO_ABERTO_SELO_FALHOU", "rg_atos",
                  r["ato_id"], {"registro_id": r["registro_id"],
                                "serie": serie, "motivo": motivo_selo})
            flash("Registro NÃO aberto: o selo não saiu. "
                  f"Motivo: {motivo_selo}. Corrija o problema do "
                  "selo e tente de novo.",
                  "danger")
            return tela()
        audit("RG_REGISTRO_NOVO", "rg_registros", r["registro_id"],
              {"serie": _campo("serie"), "numero_ordem": r.get("numero_ordem")})
        flash(f"Registro aberto no Livro {r.get('livro_numero')}, "
              f"fl. {r.get('rotulo')}, nº {r.get('numero_ordem')}.{aviso} "
              f"Se o título veio em papel, imprima a etiqueta e cole nele "
              f"antes de devolvê-lo.",
              "success")
        return _destino_apos_selar_rtdpj(r["ato_id"], r["registro_id"])

    @app.route("/rcpj-rtd/<int:registro_id>/lancar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpj_rtd_lancar(registro_id: int):
        """Averba ou cancela o registro. ESCREVE.

        Aqui cada ato ocupa FOLHA NOVA — as séries do RCPJ/RTD são de folha
        nova, e no acervo cada ato é escritura à parte. É o oposto do RCPN.
        """
        tipo = _campo("tipo")
        # O ROBÔ AVERBA, MAS NÃO CANCELA (revisão de segurança, 26/10/2026).
        import selo_robo as SR
        if SR.lancamento_vedado_ao_robo(tipo):
            abort(403)
        voltar = redirect(url_for("rcpj_rtd_registro", registro_id=registro_id))
        try:
            with db.transaction() as con:
                if tipo == "AVERBACAO":
                    natureza_ato = _campo("natureza_ato")
                    data_assinatura = _campo("data_assinatura")
                    # Teor padronizado: intro CERTIFICO + Tipo/Data (oficial
                    # 11/09/2026). Número do registro entra na intro.
                    #
                    # O texto é a ===INTRO=== do PADRÃO desde o LF06F
                    # (19/10/2026), e não o ajuste da casa: o livro grava o
                    # que gravava antes — ver `rg_teor_rtdpj.intro`.
                    reg_row = banco(con).um(
                        "SELECT numero FROM rg_registros WHERE id=%s",
                        (registro_id,))
                    numero_reg = (reg_row["numero"] if reg_row else None) or ""
                    if natureza_ato or data_assinatura:
                        teor = RGTEOR.intro(
                            numero_reg, tipo_ato="AVERBACAO",
                            natureza_ato=natureza_ato,
                            data_assinatura=data_assinatura)
                    else:
                        teor = _campo("teor") or RGTEOR.intro(
                            numero_reg, tipo_ato="AVERBACAO")
                    r = RG.lancar_averbacao(con, registro_id,
                                            teor=teor, sv=sv(),
                                            agora=agora(),
                                            data_extenso=hoje_extenso(),
                                            usuario=usuario_nome())
                elif tipo == "CANCELAMENTO":
                    r = RG.lancar_cancelamento(con, registro_id,
                                               motivo=_campo("motivo"), sv=sv(),
                                               agora=agora(),
                                               data_extenso=hoje_extenso(),
                                               usuario=usuario_nome())
                else:
                    raise RG.RgError(f"Tipo de lançamento desconhecido: {tipo!r}.")
                # Sigla pela série do registro — não pela tela. Averbar num
                # RCPJ com selo marcado «RTD» mentiria na conferência.
                linha = banco(con).um(
                    "SELECT serie FROM rg_registros WHERE id=%s",
                    (registro_id,))
                serie = linha["serie"] if linha else ""
                sigla = "RCPJ" if serie in RG.SERIES_RCPJ else "RTD"
                aviso = _selar_se_pedido(con, "rg_atos", r["ato_id"], sigla)
                cob_msg = _cobrar_se_pedido(con, "rg_atos", r["ato_id"], tipo)
        except (RG.RgError, AS.AtoError) as erro:
            flash(str(erro), "danger")
            return voltar
        # O SELO SAI AGORA, com o ato já lavrado — e fora da transação dele.
        # Mesma ordem do RCPN e da casa Santa Isabel: teor/averbação primeiro,
        # selo depois. Se a máquina cair, o ato fica sem selo (não inventa).
        recado_do_selo = _selar_o_ato(
            "rg_atos", r["ato_id"], tipo, sigla, aviso, especie=serie)
        aviso = (recado_do_selo or "") + cob_msg
        motivo_selo = _motivo_da_falha_do_selo(recado_do_selo)
        if motivo_selo:
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE rg_atos
                          SET motivo_cancelamento=%s
                        WHERE id=%s""",
                    (f"Selo não emitido: {motivo_selo}", r["ato_id"]))
            audit("RG_ATO_NAO_LAVRADO_SELO_FALHOU", "rg_atos",
                  r["ato_id"], {"tipo": tipo, "motivo": motivo_selo})
            flash("Ato NÃO lançado: o selo não saiu. "
                  f"Motivo: {motivo_selo}. Corrija o problema do "
                  "selo e tente de novo.",
                  "danger")
            return voltar
        audit("RG_ATO", "rg_atos", r["ato_id"], {"tipo": tipo})
        if tipo == "AVERBACAO":
            # **OS ARQUIVOS PODEM CHEGAR AGORA, JUNTO COM O LANÇAMENTO** —
            # pedido do oficial (11/09/2026): antes só dava para marcar
            # anexo já subido antes, numa seção separada da tela. O que for
            # escolhido em "novo_arquivo" sobe para o registro e já entra na
            # lista de ids a ligar ao ato, ao lado dos que vieram marcados
            # por checkbox.
            novos_ids = _anexar_novos_arquivos_ao_registro(
                db, registro_id=registro_id, serie=serie,
                numero=numero_reg, arquivos=request.files.getlist("novo_arquivo"),
                descricao="Anexo da averbação",
                user_id=usuario_id_do_sistema(),
                pasta_dos_arquivos=pasta_dos_arquivos)
            ids_anexo = request.form.getlist("anexo_id") + [
                str(i) for i in novos_ids]
            n_anex = _vincular_anexos_rg_ato(
                db, ato_id=r["ato_id"], registro_id=registro_id,
                anexo_ids=ids_anexo,
                user_id=usuario_id_do_sistema())
            if n_anex:
                aviso = (aviso or "") + f" {n_anex} anexo(s) ligado(s) ao ato."
        if tipo == "AVERBACAO":
            flash(f"{tipo.capitalize()} lançada. Livro {r.get('livro_numero')}, "
                  f"fl. {r.get('rotulo')}, nº {r.get('numero_ordem')}.{aviso} "
                  f"Se o documento veio em papel, imprima a etiqueta e cole "
                  f"nele antes de devolvê-lo.",
                  "success")
            return _destino_apos_selar_rtdpj(r["ato_id"], registro_id)
        flash(f"{tipo.capitalize()} lançada. Livro {r.get('livro_numero')}, "
              f"fl. {r.get('rotulo')}, nº {r.get('numero_ordem')}.{aviso}",
              "success")
        return voltar

    @app.route("/rcpj-rtd/<int:registro_id>/dados-pj", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def rcpj_rtd_dados_pj(registro_id: int):
        """Grava os dados da pessoa jurídica que o breve relato certifica. ESCREVE.

        CN-MA art. 420, II (LD05, 21/10/2026). Quem lê o estatuto e as atas
        grava a leitura na ficha — e é ela que a certidão em breve relato
        reproduz; o que havia antes vai para a auditoria. Do qualificador
        (ADMIN e MANAGER), como a qualificação: é afirmação sobre o que o
        livro diz.
        """
        voltar = redirect(url_for("rcpj_rtd_registro", registro_id=registro_id))
        try:
            with db.transaction() as con:
                r = RG.gravar_dados_da_pj(
                    con, registro_id, sede=_campo("pj_sede"),
                    objeto=_campo("pj_objeto"), capital=_campo("pj_capital"),
                    socios=_campo("pj_socios"), diretoria=_campo("pj_diretoria"),
                    agora=agora(), usuario=usuario_nome())
        except RG.RgError as erro:
            flash(str(erro), "danger")
            return voltar
        audit("RG_DADOS_DA_PJ", "rg_registros", registro_id, r)
        flash("Dados da pessoa jurídica gravados.", "success")
        return voltar

    @app.route("/rcpj-rtd/<int:registro_id>/corrigir-requerente",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpj_rtd_corrigir_requerente(registro_id: int):
        """Corrige nome/documento do requerente NO CADASTRO. ESCREVE.

        Pedido do oficial em 12/09/2026: «uma pj mudou de nome e preciso
        atualizar no sistema». A denominação/documento só se gravavam ao
        abrir o registro (`RG.abrir_registro`), e não havia tela nenhuma
        para corrigir depois — nem quando a mudança já estava averbada e
        lavrada no livro. Isto NÃO reescreve teor nenhum: é o mesmo tipo de
        correção de `ri_correcoes.py`, cadastro em volta do ato, com motivo
        obrigatório e o nome/documento de antes gravados na auditoria.
        """
        voltar = redirect(url_for("rcpj_rtd_registro", registro_id=registro_id))
        try:
            with db.transaction() as con:
                r = RG.corrigir_requerente(
                    con, registro_id,
                    requerente_nome=_campo("requerente_nome"),
                    requerente_documento=_campo("requerente_documento"),
                    motivo=_campo("motivo"))
        except RG.RgError as erro:
            flash(str(erro), "danger")
            return voltar
        audit("RG_REQUERENTE_CORRIGIDO", "rg_registros", registro_id, r)
        flash("Dados do requerente corrigidos.", "success")
        return voltar

    @app.route("/rcpj-rtd/<int:registro_id>")
    @login_required
    def rcpj_rtd_registro(registro_id: int):
        with db.connect() as con:
            registro = banco(con).um("SELECT * FROM rg_registros WHERE id=%s",
                                     (registro_id,))
            if not registro:
                flash("Registro não encontrado.", "danger")
                return redirect(url_for("rcpj_rtd_registros"))
            atos = banco(con).ler(
                "SELECT * FROM rg_atos WHERE registro_id=%s ORDER BY id",
                (registro_id,))
            receitas = _receitas_de(con, "rg_atos",
                                    ("AVERBACAO", "CANCELAMENTO"))
            # A ATRIBUICAO VAI DECLARADA, e nao pelo padrao: `at_certidoes`
            # serve os dois livros, e o que a funcao devolve sem ela e o
            # caminho DESTE — acertar por omissao e coincidencia, e
            # coincidencia nao e razao.
            certidao = _receitas_de(con, "at_certidoes", ("CERTIDAO",),
                                    "RCPJ_RTD").get("CERTIDAO")
            certidoes = [dict(x) for x in CE.listar(
                con, atribuicao="RCPJ_RTD", limite=200)
                if int(x["registro_id"]) == registro_id]
            caixa = _caixa_aberto(con)
            cobrancas = _cobrancas_de(con, "rg_atos", atos)
            protocolos = _protocolos_abertos(con)
            # **TODOS OS SELOS DE CADA ATO** — pedido do oficial em
            # 11/09/2026: `rg_atos` só guarda dois números (selo e selo de
            # arquivamento), e um ato pode ter mais de um item selado. A
            # ficha mostra a lista inteira, lida de `sd_selos`.
            selos_por_ato = {
                int(a["id"]): [dict(x) for x in AS.selos_do_ato(
                    con, "rg_atos", int(a["id"]))]
                for a in atos}
            # **OS ITENS AINDA NÃO USADOS DO PROTOCOLO ESCOLHIDO** — pedido do
            # oficial em 11/09/2026: um protocolo serve o trabalho inteiro do
            # cliente, e cada ato aponta quais dos itens dele são seus. A
            # escolha é por `?protocolo_id=` na URL (recarrega a ficha em GET,
            # sem framework nenhum) — os que já foram usados por um ato
            # anterior deste mesmo protocolo não aparecem mais.
            protocolo_escolhido = request.args.get("protocolo_id")
            itens_do_protocolo = []
            # o «²» e os 5.000 dígitos passavam pelo `isdigit()` (LD13)
            if numero_digitado(protocolo_escolhido) is not None:
                itens_do_protocolo = banco(con).ler(
                    """SELECT id, codigo_ato, descricao, quantidade,
                              valor_total, servico_codigo
                         FROM cx_protocolo_atos
                        WHERE protocolo_id=%s AND usado_em IS NULL
                          AND codigo_ato IS NOT NULL AND TRIM(codigo_ato) <> ''
                        ORDER BY id""",
                    (numero_digitado(protocolo_escolhido),))
            # NO RCPJ/RTD A PESSOA E O REQUERENTE — quem pediu o registro.
            fraudes = _fraudes_de(con, [
                {"nome": registro["requerente_nome"],
                 "documento": registro["requerente_documento"],
                 "papel_no_ato": "requerente"},
            ])
        anexos = [dict(x) for x in db.get_attachments(
            "RG_REGISTRO", registro_id)]
        atos_com_imagem = set()
        for a in atos:
            if any(_caminhos_imagens_anexos(
                    [dict(x) for x in db.get_attachments("RG_ATO", a["id"])])):
                atos_com_imagem.add(int(a["id"]))
        return render_template("atrib_registro_ficha.html",
                               registro=dict(registro), atos=atos,
                               receitas=receitas, caixa=caixa, fraudes=fraudes,
                               cobrancas=cobrancas, protocolos=protocolos,
                               certidao_receita=certidao,
                               certidoes=certidoes, atribuicao="RCPJ_RTD",
                               voltar="rcpj_rtd_registros",
                               anexos=anexos,
                               atos_com_imagem=atos_com_imagem,
                               selos_por_ato=selos_por_ato,
                               protocolo_escolhido=protocolo_escolhido,
                               itens_do_protocolo=itens_do_protocolo,
                               titulo="Registro — RCPJ / RTD")


    @app.route("/rcpj-rtd/<int:registro_id>/teor-averbacao/previa", methods=["GET", "POST"])
    @app.route("/rcpj-rtd/<int:registro_id>/teor/previa", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpj_rtd_teor_averbacao_previa(registro_id: int):
        """Prévia do PDF do teor RTDPJ (modelo da casa). NÃO grava ato.

        Query/form `tipo=AVERBACAO|REGISTRO` (default AVERBACAO). A atribuição
        (RCPJ/RTD) sai da série do registro. O texto vem de `modelos_da_casa`
        (ajuste em `mo_modelos` ou piso em `rg_teor_rtdpj`). Faixa do selo só
        na última página; `com_arquivamento=1` reserva também espaço para o
        selo de arquivamento (TJ 15.22) — SE o item estiver marcado para
        ESTE ato (não há regra que ligue arquivamento a "a 1ª averbação").
        Não sela.
        """
        voltar = redirect(url_for("rcpj_rtd_registro", registro_id=registro_id))
        with db.connect() as con:
            registro = banco(con).um(
                "SELECT * FROM rg_registros WHERE id=%s", (registro_id,)
            )
        if not registro:
            flash("Registro não encontrado.", "danger")
            return redirect(url_for("rcpj_rtd_registros"))
        numero = registro["numero"]
        if not numero:
            flash("Este registro ainda não tem número — não dá para montar o teor.",
                  "danger")
            return voltar

        tipo = (request.values.get("tipo") or "AVERBACAO").strip().upper()
        # **NÃO SE MARCA MAIS NA MÃO, E NÃO HÁ REGRA DE "1ª AVERBAÇÃO"** —
        # correção do oficial em 11/09/2026: «não tem nada que ligue 1
        # averbação a arquivamento, foi algo que o projeto entendeu errado».
        # A versão anterior caía, sem protocolo, na suposição de que a
        # PRIMEIRA averbação do registro sempre leva o arquivamento — sem
        # base nenhuma na tabela de emolumentos. Agora: com item(ns) do
        # protocolo marcados na tela (`protocolo_item_id`), reserva o espaço
        # só se um deles for o 15.22; sem marcação explícita, cai no que o
        # protocolo TEM ainda disponível (o mesmo que `_itens_para_selar`
        # pega para selar de verdade); sem protocolo, não há como saber, e
        # não se reserva.
        # O NÚMERO QUE NÃO É NÚMERO (LD13): o protocolo é nenhum, e o item ou o
        # anexo marcado que passa pelo `isdigit()` e não é id do banco vira -1,
        # o id de ninguém — o «não achei» que o de 30 dígitos já dava. Tirá-lo
        # da lista a deixaria vazia, e vazia aqui quer dizer «qualquer um».
        protocolo_id = numero_digitado(request.values.get("protocolo_id"))
        marcados = [numero_digitado(x) or -1
                    for x in request.values.getlist("protocolo_item_id")
                    if str(x).strip().isdigit()]
        com_arquivamento = False
        if protocolo_id is not None:
            with db.connect() as con:
                if marcados:
                    lugares = ",".join(["%s"] * len(marcados))
                    tem_item = banco(con).um(
                        f"""SELECT 1 AS tem FROM cx_protocolo_atos
                             WHERE protocolo_id=%s AND codigo_ato=%s
                               AND id IN ({lugares}) LIMIT 1""",
                        [protocolo_id, CODIGO_TJ_ARQUIVAMENTO_RTDPJ] + marcados)
                else:
                    tem_item = banco(con).um(
                        """SELECT 1 AS tem FROM cx_protocolo_atos
                            WHERE protocolo_id=%s AND codigo_ato=%s
                              AND usado_em IS NULL LIMIT 1""",
                        (protocolo_id, CODIGO_TJ_ARQUIVAMENTO_RTDPJ)
                    )
            com_arquivamento = bool(tem_item)
        anexos = [dict(x) for x in db.get_attachments("RG_REGISTRO", registro_id)]
        escolhidos = request.values.getlist("anexo_id")
        if escolhidos:
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
                "Anexe ao menos uma imagem ou PDF digitalizado do documento "
                "antes de gerar a prévia do teor.",
                "danger")
            return voltar

        s = sv()
        try:
            with db.connect() as con:
                # A PRÉVIA DO REGISTRO DECLARA O QUE O TERMO DECLARA (LD09): o
                # protocolo do título e as declarações do livro, do ato de
                # registro. A da averbação nova não tem número ainda — a linha
                # dele sai.
                declarado = {}
                if tipo.startswith("REG"):
                    ato_do_registro = banco(con).um(
                        """SELECT * FROM rg_atos
                            WHERE registro_id=%s AND tipo='REGISTRO'
                            ORDER BY id LIMIT 1""", (registro_id,))
                    if ato_do_registro:
                        declarado = RG.dados_do_termo(con, ato_do_registro,
                                                      registro)
                pdf = RGTEOR.gerar_pdf(
                    numero_registro=numero,
                    imagens=caminhos,
                    lavrante_nome=usuario_nome(),
                    lavrante_funcao=usuario_funcao(),
                    **declarado,
                    cns=s.get("ri_cns") or "",
                    # o nome da serventia no cabeçalho (LT05) — ver `rcpj_rtd_ato_teor`
                    unit_short=s.get("unit_name") or "",
                    cidade=s.get("ri_cidade") or "",
                    uf=s.get("ri_uf") or "MA",
                    serie=registro["serie"],
                    atribuicao=registro["atribuicao"],
                    tipo_ato=tipo,
                    natureza_ato=(request.values.get("natureza_ato") or "").strip(),
                    data_assinatura=(request.values.get("data_assinatura") or "").strip(),
                    con=con,
                    com_arquivamento=com_arquivamento,
                )
        except RGTEOR.TeorRtdpjError as erro:
            flash(str(erro), "danger")
            return voltar

        rotulo = "averbacao" if tipo.startswith("AVERB") else "registro"
        nome = f"teor-{rotulo}-registro-{numero}.pdf"
        return send_file(
            io.BytesIO(pdf),
            mimetype="application/pdf",
            as_attachment=False,
            download_name=nome,
        )


    @app.route("/rcpj-rtd/<int:registro_id>/certidao/previa", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpj_rtd_certidao_previa(registro_id: int):
        """Prévia PDF da certidão de registro RCPJ/RTD. NÃO emite, NÃO sela.

        Capa + folhas internas (faixa) via `rg_certidao_pdf`. Anexos
        RG_REGISTRO escolhidos por checkbox; default sensato exclui pacotes
        mistos grandes (DOCUMENTOS / registro_originario).
        """
        voltar = redirect(url_for("rcpj_rtd_registro", registro_id=registro_id))
        with db.connect() as con:
            registro = banco(con).um(
                "SELECT * FROM rg_registros WHERE id=%s", (registro_id,)
            )
            # Protocolo da averbação mais recente (se houver), senão vazio.
            prot = banco(con).um(
                """SELECT p.numero, p.data_abertura
                     FROM rg_atos a
                     JOIN cx_protocolos p ON p.id = a.protocolo_id
                    WHERE a.registro_id=%s AND a.protocolo_id IS NOT NULL
                    ORDER BY a.id DESC LIMIT 1""",
                (registro_id,),
            )
            ato_reg = banco(con).um(
                """SELECT data_ato FROM rg_atos
                    WHERE registro_id=%s AND tipo='REGISTRO'
                    ORDER BY id LIMIT 1""",
                (registro_id,),
            )
        if not registro:
            flash("Registro não encontrado.", "danger")
            return redirect(url_for("rcpj_rtd_registros"))
        numero = registro["numero"]
        if not numero:
            flash("Este registro ainda não tem número — não dá para montar a certidão.",
                  "danger")
            return voltar

        anexos = [dict(x) for x in db.get_attachments("RG_REGISTRO", registro_id)]
        with db.connect() as con_atos:
            atos_reg = banco(con_atos).ler(
                "SELECT * FROM rg_atos WHERE registro_id=%s ORDER BY id",
                (registro_id,))
        ato_ids_raw = request.values.getlist("ato_id")
        # o marcado que passa pelo `isdigit()` e não é id do banco é -1, o id
        # de ninguém — e não a lista vazia, que quer dizer «todos» (LD13)
        ato_ids = [numero_digitado(x) or -1
                   for x in ato_ids_raw if str(x).isdigit()] or None
        atos_escolhidos = RGCERT.filtrar_atos_por_ids(atos_reg, ato_ids)
        anexos_por_ato = {
            int(a["id"]): [dict(x) for x in db.get_attachments("RG_ATO", int(a["id"]))]
            for a in atos_escolhidos
        }
        anexo_ids_form = [
            numero_digitado(x) or -1
            for x in request.values.getlist("anexo_id") if str(x).isdigit()
        ] or None
        caminhos = RGCERT.imagens_dos_atos(
            atos_escolhidos,
            anexos_por_ato=anexos_por_ato,
            anexos_registro=anexos,
            anexo_ids_override=anexo_ids_form,
        )
        if not caminhos:
            flash(
                "Anexe ao menos uma imagem ou PDF digitalizado do documento "
                "antes de gerar a prévia da certidão.",
                "danger")
            return voltar

        s = sv()
        protocolo = (request.values.get("protocolo") or "").strip()
        data_apresentacao = (request.values.get("data_apresentacao") or "").strip()
        if not protocolo and prot:
            protocolo = str(prot["numero"] or "")
            if not data_apresentacao:
                data_apresentacao = str(prot["data_abertura"] or "")
        if not protocolo and registro.get("titulo_id"):
            # O título que gerou o registro tem o número e a data no Livro de
            # Protocolo (LT05) — a mesma régua da certidão emitida, em
            # `atribuicoes_certidao_imprimir`. `rg_atos.protocolo_id` nenhuma
            # tela grava, e a prévia saía «protocolado sob nº —».
            with db.connect() as con_tit:
                tit = banco(con_tit).um(
                    "SELECT numero, data_apresentacao FROM rg_titulos WHERE id=%s",
                    (int(registro["titulo_id"]),))
            if tit and tit["numero"] is not None:
                protocolo = str(tit["numero"])
                if not data_apresentacao:
                    data_apresentacao = str(tit["data_apresentacao"] or "")[:10]
        data_registro = (request.values.get("data_registro") or "").strip()
        if not data_registro and ato_reg and ato_reg["data_ato"]:
            data_registro = str(ato_reg["data_ato"])[:10]
        denominacao = (request.values.get("denominacao") or "").strip() or (
            registro["requerente_nome"] or "")
        natureza = (request.values.get("natureza") or "").strip() or (
            registro["natureza"] or "")

        try:
            with db.connect() as con:
                pdf = RGCERT.gerar_pdf(
                    numero=numero,
                    imagens=caminhos,
                    lavrante_nome=usuario_nome(),
                    lavrante_funcao=usuario_funcao(),
                    denominacao=denominacao,
                    natureza=natureza,
                    data_registro=data_registro,
                    protocolo=protocolo,
                    data_apresentacao=data_apresentacao,
                    cns=s.get("ri_cns") or "",
                    unit_short=(s.get("unit_name")
                                or ""),
                    oficial=(s.get("serventia_titular")
                             or ""),
                    endereco=s.get("serventia_endereco") or "",
                    telefone=s.get("serventia_telefone") or "",
                    email=s.get("serventia_email") or "",
                    cidade=s.get("ri_cidade") or "",
                    uf=s.get("ri_uf") or "MA",
                    serie=registro["serie"],
                    atribuicao=registro["atribuicao"],
                    volume=registro["volume"],
                    con=con,
                    # **SEM QUADRO DE EMOLUMENTOS** — pedido do oficial em
                    # 12/09/2026: «retire a tabela». O quadro só saía com
                    # zeros mesmo (nenhuma chamada calcula valor real ainda:
                    # ver o "placeholder" citado no topo deste módulo), e as
                    # categorias que ele tinha (Estado/Secretaria da
                    # Fazenda/TJ, depois FERC/FADEP/FEMP/FERRFIS) não
                    # resolvem isso — o problema era mostrar uma tabela sem
                    # conteúdo nenhum. `com_emolumentos=False` desliga o
                    # desenho; a função continua existindo para quando
                    # houver valor de verdade a mostrar.
                    com_emolumentos=False,
                )
        except RGCERT.CertidaoPdfError as erro:
            flash(str(erro), "danger")
            return voltar

        nome = f"previa-certidao-registro-{numero}.pdf"
        return send_file(
            io.BytesIO(pdf),
            mimetype="application/pdf",
            as_attachment=False,
            download_name=nome,
        )


    @app.route("/rcpj-rtd/ato/<int:ato_id>/teor", methods=["GET", "POST"])
    @login_required
    @roles_required(*PRATICA, metodos=("POST",))
    def rcpj_rtd_ato_teor(ato_id: int):
        """PDF completo do teor do ato (averbação/registro) com imagens.

        Cabeçalho + natureza_ato + data_assinatura + digitalizações +
        encerramento + faixa do selo na última página. Não grava, não sela.
        `com_arquivamento` automático na 1ª averbação do registro ou se o
        ato tiver selo TJ 15.22.

        **O CANCELAMENTO TAMBÉM TEM TERMO** (LD05, 21/10/2026): a certidão do
        oficial com a causa e o documento que o autorizou, datada e assinada
        (LRP art. 165; CN-MA art. 994, § 1º). A rota o recusava, e o ato
        guardava só o motivo. O documento digitalizado vai junto se estiver
        ligado ao ato; sem ele, o termo sai sem imagem.

        **QUEM SUBSCREVE É QUEM LAVROU** (LD05): `rg_registro.
        subscritor_do_ato`; o ato do acervo, sem lavrante gravado, continua
        saindo com quem imprime, como sempre saiu.

        **E O TERMO DECLARA O QUE A LEI MANDA DECLARAR** (LD09, 21/10/2026):
        o registro, o protocolo do título — data, número e apresentante (LRP
        arts. 136 e 143; art. 120) — e as declarações do livro que a lavratura
        gravou no ato (o extrato do Livro C, a inscrição da pessoa jurídica, a
        matrícula do periódico); a averbação, o número de ordem dela (LRP
        arts. 149 e 153). Tudo por `rg_registro.dados_do_termo`.
        """
        with db.connect() as con:
            ato = banco(con).um(
                "SELECT * FROM rg_atos WHERE id=%s", (ato_id,)
            )
            if not ato:
                flash("Ato não encontrado.", "danger")
                return redirect(url_for("rcpj_rtd_registros"))
            registro = banco(con).um(
                "SELECT * FROM rg_registros WHERE id=%s",
                (ato["registro_id"],))
        if not registro:
            flash("Registro do ato não encontrado.", "danger")
            return redirect(url_for("rcpj_rtd_registros"))

        voltar = redirect(url_for("rcpj_rtd_registro",
                                  registro_id=registro["id"]))
        tipo = (ato["tipo"] or "").strip().upper()
        if not (tipo.startswith("AVERB") or tipo in ("REGISTRO", "CANCELAMENTO")):
            flash("Só registro, averbação e cancelamento têm teor PDF.",
                  "danger")
            return voltar
        numero = registro["numero"]
        if not numero:
            flash("Este registro ainda não tem número — não dá para montar o teor.",
                  "danger")
            return voltar

        nat_teor, data_teor = RGTEOR.parse_campos_do_teor(ato["teor"])
        natureza_ato = (
            (request.values.get("natureza_ato") or "").strip()
            or nat_teor
            # O REGISTRO DIZ A NATUREZA DO TÍTULO — LT05, 20/10/2026. A
            # averbação a tem no teor («Tipo do ato: …»); o registro lavrado
            # pelo título guarda o teor que se digitou, e a natureza fica no
            # cadastro (`rg_registros.natureza`, a do protocolo). Sem isto o
            # termo do registro saía sem a linha «Tipo do ato» que o papel tem.
            or ((registro.get("natureza") or "").strip()
                if tipo == "REGISTRO" else ""))
        data_assinatura = (
            (request.values.get("data_assinatura") or "").strip()
            or data_teor)

        anexos = [dict(x) for x in db.get_attachments("RG_ATO", ato_id)]
        if not anexos and tipo == "REGISTRO":
            # O TERMO DO REGISTRO NÃO SAÍA PELA TELA — LT05, 20/10/2026. Só a
            # averbação liga arquivo ao ATO (`_vincular_anexos_rg_ato`); o
            # registro guarda o documento no REGISTRO (a ficha) ou no TÍTULO
            # que o protocolo recebeu, e esta rota recusava o registro com
            # selo por falta de um vínculo que nenhuma tela faz. O documento
            # trasladado é o mesmo: o do registro, e na falta dele o do título.
            # Na averbação não se cai para o registro — seria trasladar como
            # dela o documento de outro ato.
            anexos = [dict(x) for x in db.get_attachments(
                "RG_REGISTRO", int(registro["id"]))]
            if not anexos and registro.get("titulo_id"):
                anexos = [dict(x) for x in db.get_attachments(
                    "RG_TITULO", int(registro["titulo_id"]))]
        caminhos = _caminhos_imagens_anexos(anexos)
        if not caminhos and tipo != "CANCELAMENTO":
            flash(
                "Este ato ainda não tem imagem/PDF vinculado (RG_ATO). "
                "Na averbação nova marque os anexos; nos atos já lavrados "
                "é preciso ligar o arquivo ao ato.",
                "danger")
            return voltar

        with db.connect() as con:
            com_arq = RGTEOR.com_arquivamento_para_ato(
                con, int(registro["id"]), int(ato_id))
            selo_averbacao = _selo_para_teor(con, ato["selo"])
            selo_arquivamento = (
                _selo_para_teor(con, ato["selo_arquivamento"])
                if com_arq else None)
            # **TODOS OS SELOS, E NÃO SÓ OS DOIS QUE `rg_atos` GUARDA** —
            # pedido do oficial em 11/09/2026: um ato pode consumir mais de
            # um item da tabela de emolumentos, e cada item vira o SEU
            # PRÓPRIO selo — `sd_selos` (via `AS.selos_do_ato`) tem todos.
            ja_mostrados = {s["numero"] for s in
                            (selo_averbacao, selo_arquivamento) if s}
            selos_extra = _selos_extras_para_teor(
                con, "rg_atos", int(ato_id), ja_mostrados)

        s = sv()
        # A DATA DO TERMO É A DO ATO, E NÃO A DE HOJE — LT05, 20/10/2026. Sem
        # `dia`, o PDF punha a data da impressão no fecho («Cidade/UF, …»), e a
        # segunda via de amanhã diria que o ato foi lavrado amanhã.
        try:
            dia_do_ato = date.fromisoformat(str(ato["data_ato"] or "")[:10])
        except ValueError:
            dia_do_ato = None
        try:
            with db.connect() as con:
                lavrante = (RG.subscritor_do_ato(con, ato)
                            or (usuario_nome(), usuario_funcao()))
                declarado = RG.dados_do_termo(con, ato, registro)
                pdf = RGTEOR.gerar_pdf(
                    numero_registro=numero,
                    imagens=caminhos,
                    lavrante_nome=lavrante[0],
                    lavrante_funcao=lavrante[1],
                    motivo=(ato.get("motivo_cancelamento")
                            if tipo == "CANCELAMENTO" else None),
                    **declarado,
                    cns=s.get("ri_cns") or "",
                    # O NOME DA SERVENTIA NO CABEÇALHO — LT05. O papel abre com
                    # «{unit_short} — CNS {cns}», e esta rota não mandava o
                    # nome: o termo saía «— CNS 000000», sem dizer de que
                    # serventia é. A certidão em PDF já mandava (`unit_name`).
                    unit_short=s.get("unit_name") or "",
                    dia=dia_do_ato,
                    cidade=s.get("ri_cidade") or "",
                    uf=s.get("ri_uf") or "MA",
                    serie=registro["serie"],
                    atribuicao=registro["atribuicao"],
                    tipo_ato=tipo,
                    natureza_ato=natureza_ato,
                    data_assinatura=data_assinatura,
                    con=con,
                    com_arquivamento=com_arq,
                    selo_averbacao=selo_averbacao,
                    selo_arquivamento=selo_arquivamento,
                    selos_extra=selos_extra,
                )
        except RGTEOR.TeorRtdpjError as erro:
            flash(str(erro), "danger")
            return voltar

        rotulo = ("averbacao" if tipo.startswith("AVERB")
                  else "cancelamento" if tipo == "CANCELAMENTO" else "registro")
        nome = f"teor-{rotulo}-ato-{ato_id}-registro-{numero}.pdf"
        return send_file(
            io.BytesIO(pdf),
            mimetype="application/pdf",
            as_attachment=False,
            download_name=nome,
        )


    @app.route("/rcpj-rtd/<int:registro_id>/arquivo", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpj_rtd_registro_arquivo(registro_id: int):
        """Anexa imagem/PDF do livro ao registro RCPJ/RTD. ESCREVE.

        A tabela é a `attachments` — a mesma do termo RCPN e do título.
        entity_type `RG_REGISTRO` já é o usado nos anexos vindos do acervo
        (folha do livro + pacote). Não se cria tabela nova.
        """
        from storage import safe_component, save_upload
        voltar = redirect(url_for("rcpj_rtd_registro", registro_id=registro_id))
        with db.connect() as con:
            registro = banco(con).um(
                "SELECT * FROM rg_registros WHERE id=%s", (registro_id,)
            )
        if not registro:
            flash("Registro não encontrado.", "danger")
            return redirect(url_for("rcpj_rtd_registros"))
        arquivos = [f for f in request.files.getlist("arquivo") if f and f.filename]
        if not arquivos:
            flash("Escolha o arquivo a anexar — PDF ou imagem do livro.",
                  "danger")
            return voltar
        destino = (pasta_dos_arquivos() / "RCPJ"
                   / safe_component(str(registro["serie"] or "RCPJ"))
                   / safe_component(str(registro["numero"] or registro_id)))
        nomes = []
        for arquivo in arquivos:
            info = save_upload(arquivo, destino)
            anexo = db.add_attachment(
                "RG_REGISTRO", registro_id, info, usuario_id_do_sistema(),
                request.form.get("descricao") or "Anexo do livro")
            audit("RG_REGISTRO_ARQUIVO", "rg_registros", registro_id,
                  {"anexo": anexo, "sha256": info["sha256"]})
            nomes.append(info.get("original_name") or arquivo.filename)
        if len(nomes) == 1:
            flash("Arquivo anexado ao registro.", "success")
        else:
            flash(f"{len(nomes)} arquivos anexados ao registro.", "success")
        return voltar

    # -------------------------------------------------------------- Livro 3

    @app.route("/livro3")
    @login_required
    def livro3_registros():
        """O Registro Auxiliar — cédulas de crédito e o mais do art. 178."""
        return render_template("atrib_lista.html", **_listar("livro3"))

    @app.route("/livro3/importar-do-acervo", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")   # aberta ao USER por ordem dele (11/10/2026)
    def livro3_importar_acervo():
        """Trazer do acervo o Livro 3 — o registro, as partes e as averbações.

        O MESMO CAMINHO QUE O LIVRO 2 JÁ TEM, e que faltava aqui. Pedido do
        oficial em 18/09/2026: «preciso que tenha campo para importar do acervo
        registro do livro 3 do RI, igual temos no livro 2». A lista das
        matrículas tem a porta «Importações» desde sempre; a do Livro 3 só
        oferecia o registro manual, um de cada vez.

        O CAMPO É O DO ACERVO, e vem preenchido com o da casa. Quem quiser
        conferir outro arquivo — a cópia de outra máquina, o acervo que acabou
        de chegar — troca o caminho e aperta «Conferir». Só a importação GRAVA.

        CONFERIR E IMPORTAR SÃO DOIS BOTÕES, como na carga do RCPN e no padrão
        geral: aqui não há como desfazer, porque acervo importado vira o livro.

        O QUE ENTRA, MEDIDO NA PRODUÇÃO EM 18/09/2026, antes desta tela: os 14
        registros e o ato R-1 já estavam gravados, com **ZERO partes** — as 25
        de `LivroAuxiliarPartes` e as 5 averbações de `LivroAuxiliarAverbacao`
        ficaram no acervo. A passada olha o que FALTA, e por isso alcança
        também os registros que já estavam aqui.
        """
        # O CAMINHO SÓ VEM PELO FORMULÁRIO, E SÓ DE DENTRO DA CASA (LS02 A2;
        # LX12, 19/10/2026). Ele vinha também pelo endereço (`?caminho=`): GET
        # não leva o token do formulário e o cookie é `SameSite=Lax`, e um
        # link `...?caminho=\\maquina\x` clicado por quem estava logado fazia
        # o servidor ir à rede e abrir SQLite de fora. O GET mostra o acervo
        # da casa; trocar o caminho é o «Conferir», que é POST.
        caminho = str(acervo_no_disco())
        previa = None
        resultado = None
        erro = None
        digitado = ((request.form.get("caminho") or "").strip()
                    if request.method == "POST" else "")
        if digitado:
            try:
                caminho = str(app.extensions["pasta_da_casa"](digitado))
            except PDC.ForaDaCasa as recusa:
                flash(str(recusa), "danger")
                return redirect(url_for("livro3_importar_acervo"))

        def conferir(onde: str) -> dict:
            """Monta a prévia. Só LÊ o acervo e o banco do sistema."""
            acervo = AC.abrir_acervo(onde)
            try:
                with db.connect() as con:
                    return AC.previa_registro_auxiliar(con, acervo)
            finally:
                acervo.close()

        def frase_do_que_falta(p: dict) -> str:
            """O que a prévia achou, em uma frase — e ela cita o que NÃO entra."""
            falta = (f"{p['total_novos']} registro(s), "
                     f"{p['averbacoes_novas']} averbação(ões) e "
                     f"{p['partes_novas']} parte(s)")
            if p.get("partes_sem_pessoa"):
                falta += (f" — e {p['partes_sem_pessoa']} parte(s) que o "
                          f"`tbOrtoga` não resolve, que NÃO entram")
            return falta

        if request.method == "POST":
            o_que = (request.form.get("o_que") or "").strip()
            try:
                if o_que == "conferir":
                    previa = conferir(caminho)
                    flash(f"No acervo de {caminho}: {frase_do_que_falta(previa)}.",
                          "success")
                elif o_que == "importar":
                    acervo = AC.abrir_acervo(caminho)
                    try:
                        with db.transaction() as con:
                            resultado = AC.carregar_registro_auxiliar(
                                con, acervo, agora=agora())
                    finally:
                        acervo.close()
                    # O `audit` fica FORA da transação: ele abre a dele, e
                    # dentro travaria contra o `BEGIN IMMEDIATE` de fora.
                    feito = resultado.como_dict()
                    audit("LIVRO3_ACERVO_CARGA", "ACERVO", None,
                          {"caminho": caminho, **feito})
                    contagens = feito["contagens"]
                    partes = (contagens.get("partes do registro", 0)
                              + contagens.get("partes das averbações", 0))
                    flash(f"Livro 3 do acervo: {feito['inseridos']} registro(s) "
                          f"novo(s), {contagens.get('averbações', 0)} averbação(ões) "
                          f"e {partes} parte(s). O que já estava (mesma "
                          f"`origem_chave`) não entrou de novo.", "success")
                    previa = conferir(caminho)
                else:
                    flash("Não reconheci a ação pedida.", "danger")
            except AC.CargaError as falha:
                erro = str(falha)
                flash(erro, "danger")
        else:
            # A prévia já vem montada no GET: quem abre a tela quer ver o que
            # falta antes de decidir, e ver antes de gravar é a regra da casa.
            try:
                previa = conferir(caminho)
            except AC.CargaError as falha:
                erro = str(falha)

        return render_template(
            "atrib_livro3_importar.html",
            caminho=caminho,
            tem_acervo=Path(caminho).exists(),
            previa=previa,
            resultado=(resultado.como_dict() if resultado is not None else None),
            erro=erro,
        )

    def _quem_lavra_no_livro3() -> dict:
        """Quem pratica o ato do Livro 3 que se lavra agora. Só calcula.

        LH13, 21/10/2026 — o oficial, «15 a»: o Livro 3 como o Livro 2. É a
        MESMA regra (`ri_web.quem_pratica_o_ato`, publicada no `app`): o nome
        e a função de quem está logado, e o artigo do fecho. Vão para
        `ra_atos.lavrado_*` na lavratura e lá ficam congelados — a ficha
        impressa fecha o ato com eles (CN-MA art. 458).
        """
        nome, titulo, artigo = app.extensions["quem_pratica_o_ato"]()
        return {"lavrado_nome": nome, "lavrado_titulo": titulo,
                "lavrado_tratamento": artigo}

    @app.route("/livro3/novo", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_registro_novo():
        """Registra título novo no Livro 3 — o Registro Auxiliar. ESCREVE.

        O NÚMERO SAI DO CONTADOR DO RI (`ri_numeracao`, livro '3'), e não do
        `nu_numeracao` do núcleo. Duas fontes para o mesmo número é o defeito
        de 18/08/2026 outra vez; quem cuida disso é `ra_registro`, e esta rota
        não escolhe número nenhum.

        O SELO E A COBRANÇA AMARRAM-SE AO R-1, que é o ato que acabou de
        nascer com o registro — `ra_registro.registrar` devolve o registro, e
        o ato dele é o de número 1.
        """
        def tela():
            with db.connect() as con:
                contexto = _para_cobrar(con, "ra_atos", "R")
                itens_tabela = RS.itens_disponiveis(con)
            # AS LINHAS DE PARTE VOLTAM PREENCHIDAS quando o registro é
            # recusado — perder quatro nomes digitados por um campo é o que
            # faz o balcão desistir da tela.
            def _i(campo: str, i: int) -> str:
                lista = request.form.getlist(campo)
                return lista[i] if i < len(lista) else ""

            linhas = [
                {"nome": n, "tipo": _i("parte_documento_tipo", i),
                 "numero": _i("parte_documento", i),
                 "papel": _i("parte_papel", i)}
                for i, n in enumerate(request.form.getlist("parte_nome"))
                if (n or "").strip()] if request.method == "POST" else []
            return render_template("atrib_livro3_novo.html",
                                   naturezas=RA.NATUREZAS, form=request.form,
                                   itens_tabela=itens_tabela,
                                   papeis=RAPT.PAPEIS,
                                   partes_digitadas=linhas or [{}, {}],
                                   **contexto)

        if request.method != "POST":
            return tela()

        # QUANTAS PARTES FOREM PRECISAS — 19/10/2026, pedido do oficial
        # («adicionar mais partes no ato»). A tela tinha duas linhas fixas e
        # o papel em texto livre; agora as linhas são do botão
        # «+ Adicionar parte» e passam pela regra de `ra_parte`.
        try:
            partes = RAPT.partes_do_formulario(
                request.form.getlist("parte_nome"),
                request.form.getlist("parte_documento_tipo"),
                request.form.getlist("parte_documento"),
                request.form.getlist("parte_papel"))
        except RAPT.ParteError as erro:
            flash(str(erro), "danger")
            return tela()

        gerar_arquivamento = _campo("gerar_arquivamento") == "1"
        folhas_arquivamento = 0
        if gerar_arquivamento:
            # o mesmo `integer` de `livro3_lancar` (LD13)
            folhas_arquivamento = numero_digitado(
                _campo("folhas_arquivamento"), maximo=MAIOR_INTEGER) or 0
            if folhas_arquivamento < 1:
                flash("Informe a quantidade de folhas do arquivamento (>= 1).",
                      "danger")
                return tela()

        try:
            with db.transaction() as con:
                r = RA.registrar(
                    con, natureza=_campo("natureza"), agora=agora(),
                    titulo_tipo=_campo("titulo_tipo") or None,
                    titulo_numero=_campo("titulo_numero") or None,
                    data_titulo=_campo("data_titulo") or None,
                    valor=_campo("valor") or None,
                    parcelas=_campo("parcelas") or None,
                    vencimento_inicial=_campo("vencimento_inicial") or None,
                    vencimento_final=_campo("vencimento_final") or None,
                    juros=_campo("juros") or None,
                    garantia=_campo("garantia") or None,
                    condicoes=_campo("condicoes") or None,
                    teor=_campo("teor") or None, partes=partes,
                    usuario=usuario_nome(), **_quem_lavra_no_livro3())
                bd = banco(con)
                r1 = bd.um(
                    "SELECT id FROM ra_atos WHERE registro_id=%s AND numero=1 "
                    "ORDER BY id LIMIT 1",
                    (r["registro_id"],))
                ato_id = int(r1["id"])
                bd.escrever(
                    "UPDATE ra_registros SET prenotacao=%s WHERE id=%s",
                    (_campo("prenotacao") or None, r["registro_id"]))
                bd.escrever(
                    """UPDATE ra_atos SET natureza_titulo=%s, codigo_tj=%s,
                              base_calculo_centavos=%s, folhas_arquivamento=%s
                        WHERE id=%s""",
                    (_campo("natureza_titulo") or None,
                     _campo("codigo_tj") or None,
                     RS.centavos_do_valor(_campo("base_calculo")),
                     folhas_arquivamento or None, ato_id))
                aviso = _selar_se_pedido(con, "ra_atos", ato_id, "RI")
                aviso += _cobrar_se_pedido(con, "ra_atos", ato_id, "R")
        except (RA.RaError, AS.AtoError) as erro:
            flash(str(erro), "danger")
            return tela()
        selar = app.extensions.get("selar_o_ato_do_livro3")
        selo_ok = bool(_campo("selo"))
        if selar and not _campo("selo"):
            with db.connect() as con:
                ato = banco(con).um("SELECT * FROM ra_atos WHERE id=%s",
                                    (ato_id,))
                registro = banco(con).um("SELECT * FROM ra_registros WHERE id=%s",
                                         (r["registro_id"],))
            resposta_selo = selar(
                ato=ato, registro=registro,
                natureza=_campo("natureza_titulo"),
                codigo_tj=_campo("codigo_tj"),
                base_calculo=RS.centavos_do_valor(_campo("base_calculo")),
                isento=False, motivo_isencao=None)
            aviso += resposta_selo["recado"]
            selo_ok = resposta_selo["selado"]
        arq_ok = True
        if gerar_arquivamento:
            arquivar = app.extensions.get("arquivar_o_ato_do_livro3")
            if arquivar:
                arq = arquivar(ato_id=ato_id, folhas=folhas_arquivamento)
                aviso += " " + arq["recado"]
                arq_ok = arq["ok"]
        audit("RA_REGISTRO_NOVO", "ra_registros", r["registro_id"],
              {"natureza": _campo("natureza"), "numero": r["numero"]})
        flash(f"Registro {r['numero']} do Livro 3 lavrado, como "
              f"{r['rotulo']}.{aviso}",
              "success" if selo_ok and arq_ok else "danger")
        return redirect(url_for("livro3_registro",
                                registro_id=r["registro_id"]))

    @app.route("/livro3/<int:registro_id>/lancar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_lancar(registro_id: int):
        """Averba ou cancela no Livro 3. ESCREVE.

        A numeração do ato é contínua com o registro: depois do R-1 vem o AV-2.
        O cancelamento é uma AVERBAÇÃO — o registro fica na ficha, com a
        averbação dizendo que foi cancelado e por quê.
        """
        tipo = _campo("tipo")
        # O ROBÔ AVERBA, MAS NÃO CANCELA (revisão de segurança, 26/10/2026).
        import selo_robo as SR
        if SR.lancamento_vedado_ao_robo(tipo):
            abort(403)
        voltar = redirect(url_for("livro3_registro", registro_id=registro_id))
        gerar_arquivamento = _campo("gerar_arquivamento") == "1"
        folhas_arquivamento = 0
        if gerar_arquivamento:
            # vai gravado em `ra_atos.folhas_arquivamento` (`integer`): o de 18
            # ou 30 dígitos passava pelo `int()` e estourava a gravação, e o de
            # 5.000 o Python recusa — é o mesmo «informe» do texto (LD13)
            folhas_arquivamento = numero_digitado(
                _campo("folhas_arquivamento"), maximo=MAIOR_INTEGER) or 0
            if folhas_arquivamento < 1:
                flash("Informe a quantidade de folhas do arquivamento (>= 1).",
                      "danger")
                return voltar
        try:
            with db.transaction() as con:
                if tipo == "AVERBACAO":
                    r = RA.averbar(con, registro_id, teor=_campo("teor"),
                                   agora=agora(),
                                   natureza=_campo("natureza") or None,
                                   usuario=usuario_nome(),
                                   **_quem_lavra_no_livro3())
                elif tipo == "CANCELAMENTO":
                    r = RA.cancelar(con, registro_id, motivo=_campo("motivo"),
                                    agora=agora(), usuario=usuario_nome(),
                                    **_quem_lavra_no_livro3())
                else:
                    raise RA.RaError(f"Tipo de lançamento desconhecido: {tipo!r}.")
                aviso = _selar_se_pedido(con, "ra_atos", r["ato_id"], "RI")
                aviso += _cobrar_se_pedido(con, "ra_atos", r["ato_id"],
                                           "AV" if tipo == "AVERBACAO" else tipo)
                # O QUE FOI INFORMADO PARA O SELO FICA NO ATO, e dentro da
                # mesma transacao que o lavrou: se o aparelho nao responder, a
                # qualificacao digitada nao se perde e o botao «selar este
                # ato» ja abre preenchido.
                banco(con).escrever(
                    """UPDATE ra_atos SET natureza_titulo=%s, codigo_tj=%s,
                              base_calculo_centavos=%s, folhas_arquivamento=%s
                        WHERE id=%s""",
                    (_campo("natureza_titulo") or None,
                     _campo("codigo_tj") or None,
                     RS.centavos_do_valor(_campo("base_calculo")),
                     folhas_arquivamento or None, r["ato_id"]))
                # A MINUTA SE MARCA LAVRADA NA MESMA TRANSACAO DO ATO — regra,
                # e nao conselho: ato que nao entra tem de deixar a minuta
                # onde estava, esperando. E a mesma do Livro 2.
                if _campo("minuta_id"):
                    # a minuta que não é número é a de ninguém (-1): a recusa
                    # que o id que não existe já dava, e não a tela de erro
                    # (LD13)
                    MIN.marcar_lavrada(con, numero_digitado(_campo("minuta_id")) or -1,
                                       ato_id=r["ato_id"], agora=agora(),
                                       usuario=usuario_nome())
        except (RA.RaError, AS.AtoError, MIN.MinutaError) as erro:
            flash(str(erro), "danger")
            return voltar

        # O SELO AUTOMATICO DO LIVRO 3 — 20/09/2026, relato do oficial: «fiz a
        # averbacao da 1243 e nao emitiu selo».
        #
        #   ATE AQUI ESTA ROTA SO SABIA GRAVAR O NUMERO QUE O ESCREVENTE
        #   DIGITASSE (`_selar_se_pedido`): ela nunca pediu selo ao aparelho.
        #   O Livro 2 pede desde 14/09; o Livro 3 ficou de fora, e ninguem
        #   viu porque ato sem selo nao da erro nenhum — ele so nao existe
        #   para o Tribunal.
        #
        #   ELE VEM DEPOIS DA TRANSACAO, e isso e regra da casa: a chamada ao
        #   selador tem prazo de 20 s, e segura-la dentro de um `BEGIN
        #   IMMEDIATE` poria todo outro balcao no `busy_timeout`.
        #
        #   E SELO QUE NAO SAI NAO DERRUBA O ATO AQUI. No Livro 2 a ordem do
        #   oficial de 16/09 e suspender — la o ato se relavra. Aqui o ato ja
        #   esta escrito e o registro pode ate ter sido CANCELADO por ele;
        #   desfaze-lo seria desfazer o cancelamento. Ele fica lavrado, com o
        #   aviso, e o botao «selar este ato» na ficha resolve depois.
        selar = app.extensions.get("selar_o_ato_do_livro3")
        selo_ok = bool(_campo("selo"))
        if selar and not _campo("selo"):
            with db.connect() as con:
                ato = banco(con).um("SELECT * FROM ra_atos WHERE id=%s",
                                    (r["ato_id"],))
                registro = banco(con).um(
                    "SELECT * FROM ra_registros WHERE id=%s",
                    (registro_id,))
            resposta_selo = selar(
                ato=ato, registro=registro,
                natureza=_campo("natureza_titulo"),
                codigo_tj=_campo("codigo_tj"),
                base_calculo=RS.centavos_do_valor(_campo("base_calculo")),
                isento=False, motivo_isencao=None)
            aviso += resposta_selo["recado"]
            selo_ok = resposta_selo["selado"]

        arq_ok = True
        if gerar_arquivamento:
            arquivar = app.extensions.get("arquivar_o_ato_do_livro3")
            if arquivar:
                arq = arquivar(ato_id=r["ato_id"], folhas=folhas_arquivamento)
                aviso += " " + arq["recado"]
                arq_ok = arq["ok"]

        audit("RA_ATO", "ra_atos", r["ato_id"], {"tipo": tipo})
        flash(f"{r['rotulo']} lançado.{aviso}",
              "success" if selo_ok and arq_ok else "danger")
        return voltar

    @app.route("/livro3/<int:registro_id>")
    @login_required
    def livro3_registro(registro_id: int):
        with db.connect() as con:
            registro = banco(con).um("SELECT * FROM ra_registros WHERE id=%s",
                                     (registro_id,))
            if not registro:
                flash("Registro não encontrado.", "danger")
                return redirect(url_for("livro3_registros"))
            atos = banco(con).ler(
                "SELECT * FROM ra_atos WHERE registro_id=%s ORDER BY numero",
                (registro_id,))
            partes = banco(con).ler(
                "SELECT * FROM ra_partes WHERE registro_id=%s ORDER BY id",
                (registro_id,))
            itens_tabela = RS.itens_disponiveis(con)
            receitas = _receitas_de(con, "ra_atos", ("AV",))
            # A ATRIBUICAO VAI JUNTO — e o que separa o item do Livro 3 do
            # item do RTD/PJ. Ver `AS.caminho_do_ato`.
            certidao = _receitas_de(con, "at_certidoes", ("CERTIDAO",),
                                    "LIVRO3").get("CERTIDAO")
            certidoes = [dict(x) for x in CE.listar(
                con, atribuicao="LIVRO3", limite=200)
                if int(x["registro_id"]) == registro_id]
            caixa = _caixa_aberto(con)
            cobrancas = _cobrancas_de(con, "ra_atos", atos)
            protocolos = _protocolos_abertos(con)
            # AS MINUTAS DE VERDADE, com situacao e descarte com motivo.
            minutas = MIN.listar(con, registro_id, situacao=None)
            # O QUE FALTA CONFERIR e COMO OS ATOS ESTAO NUMERADOS — itens 2 e
            # 5 da fila de 20/09/2026.
            revisoes = RREV.do_registro(con, registro_id)
            numeracao = CORR.numeracao_dos_atos(con, registro_id)
            # AS ATAS DE OCORRENCIA — o papel de cada ato que deixou de
            # existir. Item 6 da fila.
            expurgos = EXPU.listar(con, registro_id)
            minuta_av = None
            row_m = banco(con).um(
                """SELECT id, titulo, dados_json FROM rascunhos_de_tela
                    WHERE tela='livro3_minuta_av' AND chave=%s
                    ORDER BY id DESC LIMIT 1""",
                (f"livro3-cancelamento:{registro['numero']}",))
            if row_m:
                import json as _json
                try:
                    dados_m = _json.loads(row_m["dados_json"] or "{}")
                except _json.JSONDecodeError:
                    dados_m = {}
                minuta_av = {
                    "id": row_m["id"], "titulo": row_m["titulo"],
                    "teor": dados_m.get("teor") or "",
                    "rotulo_origem": dados_m.get("rotulo_origem") or "",
                }
            # NO LIVRO 3 AS PESSOAS SAO AS PARTES — emitente, credor,
            # avalista. Sao varias, e cada uma tem papel proprio.
            fraudes = _fraudes_de(con, [
                {"nome": x.get("nome"), "documento": x.get("documento_numero"),
                 "papel_no_ato": (x.get("papel") or "parte")}
                for x in partes])
        return render_template("atrib_livro3_ficha.html",
                               registro=dict(registro), atos=atos,
                               partes=partes, naturezas=RA.NATUREZAS,
                               receitas=receitas, caixa=caixa,
                               cobrancas=cobrancas, protocolos=protocolos,
                               certidao_receita=certidao, fraudes=fraudes,
                               certidoes=certidoes, atribuicao="LIVRO3",
                               minuta_av=minuta_av,
                               # OS ITENS QUE ESTA CASA USOU NO LIVRO 3, por
                               # tipo de ato — medidos no acervo em
                               # 20/09/2026. A tela os OFERECE; quem escolhe e
                               # quem atende, porque o item nao sai do tipo do
                               # ato. Ver `ra_selo.ITENS_MEDIDOS`.
                               itens_de_selo={
                                   "R": RS.itens_do_tipo("R"),
                                   "AV": RS.itens_do_tipo("AV")},
                               itens_tabela=itens_tabela,
                               # AS MINUTAS DESTE REGISTRO — item 1 da fila de
                               # 20/09/2026. Vao as tres situacoes: a
                               # descartada NAO some, porque a pergunta que
                               # aparece meses depois e «e aquela averbacao
                               # que estava para sair?».
                               minutas=minutas, situacoes=MIN.SITUACOES,
                               # OS PAPEIS DAS PARTES sao os medidos nas 25 do
                               # acervo, e depois o catalogo da casa. Ver
                               # `ra_parte.PAPEIS`.
                               papeis=RAPT.PAPEIS,
                               revisoes=revisoes, numeracao=numeracao,
                               campos_editaveis=CORR.CAMPOS_EDITAVEIS,
                               expurgos=expurgos)

    # ------------------------- o aviso de intimação, a entrega e o edital

    @app.route("/protesto/avisos")
    @login_required
    def protesto_avisos():
        """O que saiu, o que voltou e o que espera edital. Só LÊ.

        O EDITAL É ROTINA NESTA CASA, e não exceção: 1.092 dos 1.618 avisos do
        acervo terminaram publicados, e 94% das não-entregas dizem «Ausente».
        Por isso a lista do edital vem primeiro — é a que mais enche.
        """
        with db.connect() as con:
            para_edital = AV.esperando_edital(con)
            for a in para_edital:
                a["tentativas"] = AV.tentativas(con, a["id"])
                # O PRÓXIMO PASSO — Resolve, esperar, lavrar a digital ou
                # edital (15/10/2026). A régua é do domínio; a tela só mostra.
                a["caminho"] = AV.depois_da_nao_entrega(con, a)
                a["comprovantes"] = AV.comprovantes(con, a["id"])
                a["base"] = PBE.ultima_consulta(con, a)
            esperando = AV.esperando_entrega(con, hoje=hoje())
            # O TÍTULO APONTADO SEM AVISO NÃO SOME MAIS (21/10/2026): os que
            # vieram do E-Ofício sem aviso ficavam invisíveis aqui. E o
            # apontado há mais de seis meses vai para a sua própria lista.
            sem_aviso = AV.apontados_sem_aviso(con, hoje())
            antigos = AV.apontados_antigos(con, hoje())
            for a in esperando:
                a["tentativas"] = AV.tentativas(con, a["id"])
            entregues = AV.entregues(con)
            for a in entregues:
                a["base_cadastro"] = PBE.cadastro(con, a["id"])
            contas = AV.contagens(con)
            do_dia = AV.editais_do_dia(con, hoje())
            # O ENVIO À CENPROT, DIA A DIA, COM O COMPROVANTE (#142).
            envios = AV.envios_do_edital(con, hoje())
        motivos = AV.motivos_para_escolher()
        destaque = [{"codigo": c, "motivo": AV.ROTULO_DO_DESTAQUE[c]}
                    for c in AV.MOTIVOS_EM_DESTAQUE]
        outros = [m for m in motivos
                  if m["codigo"] not in AV.MOTIVOS_EM_DESTAQUE]
        return render_template("protesto_avisos.html", para_edital=para_edital,
                               esperando=esperando, entregues=entregues,
                               sem_aviso=sem_aviso, antigos=antigos,
                               antigo_dias=AV.ANTIGO_DIAS,
                               contas=contas, do_dia=do_dia, envios=envios,
                               motivos=motivos,
                               motivos_destaque=destaque,
                               motivos_outros=outros,
                               entregadores=AV.ENTREGADORES, hoje=hoje())

    @app.route("/protesto/<int:titulo_id>/aviso", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_aviso_emitir(titulo_id: int):
        """Emite o aviso de intimação do título. ESCREVE.

        SAI DA FICHA DO TÍTULO, e não de uma tela à parte: é ali que o
        escrevente vê o devedor, o endereço e o protocolo — e é ali que ele
        corrige o endereço quando o cliente traz um melhor.
        """
        volta = url_for("protesto_titulo", titulo_id=titulo_id)
        endereco = {c: _campo(c) for c in
                    ("endereco", "bairro", "cep", "cidade", "uf")
                    if _campo(c)}
        try:
            with db.transaction() as con:
                r = AV.emitir(con, titulo_id, hoje=hoje(), agora=agora(),
                              usuario=usuario_nome(),
                              endereco=endereco or None)
        except (AV.AvisoError, PT.ProtestoError) as erro:
            flash(str(erro), "danger")
            return redirect(volta)
        audit("PROTESTO_AVISO", "pt_avisos", r["aviso_id"],
              {"titulo_id": titulo_id, "numero": r["numero"],
               "ano": r["ano"], "devedor": r["devedor_nome"]})
        flash(f"Aviso {r['numero']}/{r['ano']} emitido para "
              f"{r['devedor_nome']}. Imprima pelo botão «Imprimir» na lista "
              f"de avisos da ficha e mande entregar.", "success")
        return redirect(volta)

    @app.route("/protesto/avisos/<int:aviso_id>/entrega", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_aviso_entrega(aviso_id: int):
        """Registra o que aconteceu com o aviso. ESCREVE.

        ENTREGA COM ÊXITO LAVRA A INTIMAÇÃO PESSOAL — o devedor recebeu o papel
        na mão, e isso é a intimação. Entrega SEM êxito não lavra nada: é
        tentativa, e o que ela produz é o caminho do edital. Se a tentativa
        frustrada lavrasse intimação, o título ficaria intimado sem ninguém ter
        sido intimado, e o protesto sairia em cima disso.
        """
        entregue = _campo("entregue") == "1"
        # O COMPROVANTE PODE VIR JUNTO DA ENTREGA (15/10/2026), na mesma
        # transação: entrega que não entra não deixa comprovante solto, e
        # comprovante recusado desfaz a entrega — o balcão corrige e manda de
        # novo, sem meia operação gravada.
        enviado = request.files.get("comprovante")
        tem_arquivo = bool(enviado and enviado.filename)
        anexo = None
        try:
            with db.transaction() as con:
                r = AV.registrar_entrega(
                    con, aviso_id, entregue=entregue, agora=agora(),
                    quando=_campo("quando") or None,
                    entregador=_campo("entregador") or AV.ENTREGADOR_DA_CASA,
                    motivo=_campo("motivo") or None,
                    recebido_por=_campo("recebido_por") or None,
                    observacao=_campo("observacao") or None,
                    usuario=usuario_nome())
                if entregue and tem_arquivo:
                    anexo = AV.guardar_comprovante(
                        con, aviso_id, nome=enviado.filename,
                        conteudo=enviado.read(),
                        pasta_de_arquivos=pasta_dos_arquivos(), agora=agora(),
                        usuario_id=usuario_id_do_sistema())
        except (AV.AvisoError, PT.ProtestoError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_avisos"))
        audit("PROTESTO_AVISO_ENTREGA", "pt_avisos", aviso_id,
              {"entregue": entregue, "motivo": _campo("motivo") or None,
               "ato_id": r["ato_id"],
               "comprovante": (anexo or {}).get("anexo_id")})
        if entregue:
            flash("Entrega registrada, e a intimação pessoal foi lavrada."
                  + (" O comprovante ficou anexado." if anexo else
                     " Falta anexar o comprovante assinado — é a lista "
                     "«Entregues» desta tela."),
                  "success")
        else:
            flash(f"Não-entrega registrada: "
                  f"{AV.motivo_rotulo(_campo('motivo'))}. O aviso está na "
                  f"lista «Não entregues — Resolve, e depois edital».",
                  "warning")
        return redirect(url_for("protesto_avisos"))

    @app.route("/protesto/avisos/<int:aviso_id>/edital", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_aviso_edital(aviso_id: int):
        """Publica o edital do aviso que não foi entregue. ESCREVE.

        É ELE QUE LAVRA A INTIMAÇÃO POR EDITAL, com o código. Antes disto o
        código era digitado à mão na ficha — e edital que só existe como texto
        num campo não se confere depois.
        """
        try:
            with db.transaction() as con:
                r = AV.publicar_edital(con, aviso_id, sv=sv(), hoje=hoje(),
                                       agora=agora(),
                                       data_extenso=hoje_extenso(),
                                       usuario=usuario_nome(),
                                       justificativa=_campo("justificativa"))
        except (AV.AvisoError, PT.ProtestoError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_avisos"))
        audit("PROTESTO_EDITAL", "pt_editais", r["edital_id"],
              {"aviso_id": aviso_id, "codigo": r["codigo"],
               "ato_id": r["ato_id"],
               "justificativa": _campo("justificativa") or None})
        flash(f"Edital {r['codigo']} publicado, e a intimação por edital foi "
              f"lavrada. Imprima a folha do dia e afixe.", "success")
        return redirect(url_for("protesto_avisos"))

    @app.route("/protesto/avisos/<int:aviso_id>/comprovante", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_aviso_comprovante(aviso_id: int):
        """Anexa o comprovante da intimação entregue. ESCREVE.

        Pedido do oficial, 15/10/2026: «lugar de upload das intimações dos
        títulos entregues». O papel assinado é o que comprova a intimação
        (CN-MA art. 921, § 6º, I); a entrega pode ter sido registrada antes de
        ele voltar escaneado, e por isso o upload também é separado.
        """
        enviado = request.files.get("comprovante")
        if not enviado or not enviado.filename:
            flash("Escolha o arquivo do comprovante.", "danger")
            return redirect(url_for("protesto_avisos"))
        try:
            with db.transaction() as con:
                r = AV.guardar_comprovante(
                    con, aviso_id, nome=enviado.filename,
                    conteudo=enviado.read(),
                    pasta_de_arquivos=pasta_dos_arquivos(), agora=agora(),
                    usuario_id=usuario_id_do_sistema())
        except AV.AvisoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_avisos"))
        audit("PROTESTO_AVISO_COMPROVANTE", "pt_avisos", aviso_id,
              {"anexo_id": r["anexo_id"], "nome": r["nome"]})
        flash(f"Comprovante anexado ({r['nome']}).", "success")
        return redirect(url_for("protesto_avisos") + "#entregues")

    @app.route("/protesto/editais/comprovante-cenprot", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_edital_comprovante_cenprot():
        """Anexa o comprovante do envio dos editais do dia à CENPROT. ESCREVE.

        Pedido do oficial, 26/10/2026 (problema #142): «vamos criar um campo
        para anexar o comprovante de envio do edital». CN-MA art. 922, § 1º.
        """
        voltar = redirect(url_for("protesto_avisos") + "#envio-do-edital")
        enviado = request.files.get("comprovante")
        if not enviado or not enviado.filename:
            flash("Escolha o arquivo do comprovante do envio.", "danger")
            return voltar
        dia = (_campo("dia") or hoje())[:10]
        try:
            with db.transaction() as con:
                r = AV.guardar_comprovante_do_envio(
                    con, dia, nome=enviado.filename, conteudo=enviado.read(),
                    pasta_de_arquivos=pasta_dos_arquivos(), agora=agora(),
                    usuario_id=usuario_id_do_sistema())
        except AV.AvisoError as erro:
            flash(str(erro), "danger")
            return voltar
        audit("PROTESTO_EDITAL_ENVIO_CENPROT", "pt_editais", None,
              {"dia": dia, "editais": r["editais"], "anexos": r["anexos"],
               "nome": r["nome"]})
        flash(f"Comprovante do envio à CENPROT anexado aos {r['editais']} "
              f"edital(is) de {dia}.", "success")
        return voltar

    @app.route("/protesto/avisos/<int:aviso_id>/resolve", methods=["POST"])
    # 21/10/2026: aberto às escreventes por ordem do oficial (era ("ADMIN", "MANAGER")).
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_aviso_resolve(aviso_id: int):
        """Manda pela Intimação Digital o título do aviso não entregue.
        **ESCREVE NA CENTRAL.**

        É o mesmo `resolve_intimacao.enviar` da tela da Resolve — um título
        só, o deste aviso —, e por isso as mesmas guardas: só produção, chave
        do CENPROT, conferência antes da rede, e a chamada fora da transação.
        Quem envia é quem envia lá (ADMIN e gerente).
        """
        import resolve_api as RAPI
        import resolve_intimacao as RS
        with db.connect() as con:
            aviso = AV.ler(con, aviso_id)
        if not aviso:
            flash(f"Aviso {aviso_id} não encontrado.", "danger")
            return redirect(url_for("protesto_avisos"))
        try:
            r = RS.enviar(db, [int(aviso["titulo_id"])], quem=usuario_nome())
        except (RS.IntimacaoDigitalError, RAPI.ResolveError,
                CENTCRED.CredencialError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_avisos"))
        audit("PROTESTO_AVISO_RESOLVE", "pt_avisos", aviso_id,
              {"titulo_id": int(aviso["titulo_id"]),
               "lote_id": r.get("lote_id"), "gravadas": r.get("gravadas")})
        flash(f"Intimação Digital enviada pela Resolve (lote "
              f"{r.get('lote_id') or 'sem número'}). Acompanhe aqui: quando "
              f"a plataforma confirmar, lavre a intimação digital; se não "
              f"der, publique o edital.", "success")
        return redirect(url_for("protesto_avisos"))

    # ---------------- a base nacional de endereços da CENPROT (15/10/2026)

    @app.route("/protesto/avisos/<int:aviso_id>/base-cenprot/consultar",
               methods=["POST"])
    # 21/10/2026: aberto às escreventes por ordem do oficial (era ("ADMIN", "MANAGER")).
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_aviso_base_consultar(aviso_id: int):
        """Procura o devedor do aviso não entregue na base nacional de
        endereços da CENPROT. Manda o CPF/CNPJ para fora, por isso só com
        clique, e a resposta fica guardada. A chamada é FORA da transação."""
        import cenprot_api as CAPI
        import protesto_base_endereco as PBE
        try:
            with db.connect() as con:
                av = PBE.aviso(con, aviso_id)
            achados = CAPI.consultar_endereco(PBE.documento(av))
            with db.transaction() as con:
                PBE.registrar(con, av, acao=PBE.CONSULTA,
                              ambiente=CENTCRED.PRODUCAO, agora=agora(),
                              usuario=usuario_nome(), resposta=achados)
        except (PBE.BaseEnderecoError, CAPI.CenprotError,
                CENTCRED.CredencialError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_avisos"))
        audit("PROTESTO_BASE_ENDERECO_CONSULTA", "pt_avisos", aviso_id,
              {"achados": len(achados)})
        flash(f"A base da CENPROT trouxe {len(achados)} endereço(s) para o "
              f"devedor do aviso — veja na linha dele." if achados else
              "A base da CENPROT não tem endereço para este documento.",
              "success" if achados else "info")
        return redirect(url_for("protesto_avisos") + f"#aviso-{aviso_id}")

    @app.route("/protesto/avisos/<int:aviso_id>/base-cenprot/cadastrar",
               methods=["POST"])
    # 21/10/2026: aberto às escreventes por ordem do oficial (era ("ADMIN", "MANAGER")).
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_aviso_base_cadastrar(aviso_id: int):
        """Cadastra na base nacional o endereço em que o aviso FOI ENTREGUE.
        **ESCREVE NA CENTRAL.** Só insere; o que já foi mandado não se manda
        de novo."""
        import cenprot_api as CAPI
        import protesto_base_endereco as PBE
        try:
            with db.connect() as con:
                av = PBE.aviso(con, aviso_id)
                if PBE.cadastro(con, aviso_id):
                    raise PBE.BaseEnderecoError(
                        "O endereço deste aviso já foi cadastrado na base da "
                        "CENPROT — a base só insere, e mandar de novo o "
                        "duplicaria.")
            corpo = PBE.corpo_do_cadastro(av)
            resposta = CAPI.cadastrar_endereco(corpo)
            with db.transaction() as con:
                PBE.registrar(con, av, acao=PBE.CADASTRO,
                              ambiente=CENTCRED.PRODUCAO, agora=agora(),
                              usuario=usuario_nome(), enviado=corpo,
                              resposta=resposta)
        except (PBE.BaseEnderecoError, CAPI.CenprotError,
                CENTCRED.CredencialError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_avisos"))
        audit("PROTESTO_BASE_ENDERECO_CADASTRO", "pt_avisos", aviso_id, None)
        flash("Endereço cadastrado na base nacional da CENPROT.", "success")
        return redirect(url_for("protesto_avisos") + f"#aviso-{aviso_id}")

    # ------------------------- o PDF com várias intimações (15/10/2026)

    @app.route("/protesto/avisos/lote", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_avisos_lote():
        """Um PDF com várias intimações entregues: o sistema separa pelo QR do
        aviso e mostra a conferência. NÃO GRAVA ATO NENHUM — só guarda o PDF
        para o segundo passo, com o hash do conteúdo como nome."""
        if request.method == "GET":
            return render_template("protesto_avisos_lote.html", visto=None,
                                   hoje=hoje())
        enviado = request.files.get("pdf")
        if not enviado or not enviado.filename:
            flash("Escolha o PDF com as intimações escaneadas.", "danger")
            return redirect(url_for("protesto_avisos_lote"))
        pdf = enviado.read()
        try:
            with db.connect() as con:
                visto = PILOTE.conferir(con, pdf)
            PILOTE.guardar_lote(pasta_dos_arquivos(), pdf)
        except (PILOTE.LoteError, AV.AvisoError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_avisos_lote"))
        motivos = AV.motivos_para_escolher()
        return render_template(
            "protesto_avisos_lote.html", visto=visto, nome=enviado.filename,
            hoje=hoje(),
            motivos_destaque=[{"codigo": c, "motivo": AV.ROTULO_DO_DESTAQUE[c]}
                              for c in AV.MOTIVOS_EM_DESTAQUE],
            motivos_outros=[m for m in motivos
                            if m["codigo"] not in AV.MOTIVOS_EM_DESTAQUE])

    @app.route("/protesto/avisos/lote/<sha>/folhas")
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_avisos_lote_folhas(sha: str):
        """As folhas de um aviso do lote, NA TELA, para conferir antes de
        registrar. Só LÊ."""
        try:
            pdf = PILOTE.ler_lote(pasta_dos_arquivos(), sha)
            # a folha que não é número não foi pedida; a que passa do `int` do
            # leitor de PDF o derrubava (LD13)
            paginas = [n for n in (numero_digitado(x, maximo=MAIOR_INTEGER)
                                   for x in str(request.args.get("p") or "").split(","))
                       if n is not None]
            if not paginas:
                abort(404)
            parte = PILOTE.fatia(pdf, paginas)
        except PILOTE.LoteError:
            abort(404)
        return Response(parte, mimetype="application/pdf",
                        headers={"Content-Disposition": "inline",
                                 "X-Content-Type-Options": "nosniff"})

    @app.route("/protesto/avisos/lote/<sha>/registrar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_avisos_lote_registrar(sha: str):
        """Registra os avisos MARCADOS do lote. ESCREVE.

        Um por vez, cada um na sua transação: um que falha não derruba os
        outros, e a frase diz qual falhou e por quê. A entrega lavra a
        intimação pessoal pelo caminho de sempre.
        """
        try:
            pdf = PILOTE.ler_lote(pasta_dos_arquivos(), sha)
        except PILOTE.LoteError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_avisos_lote"))
        # o que não é número não foi marcado (LD13 — o «²» era a tela de erro)
        marcados = [n for n in (numero_digitado(x)
                                for x in request.form.getlist("aviso_id"))
                    if n is not None]
        if not marcados:
            flash("Nenhum aviso foi marcado.", "warning")
            return redirect(url_for("protesto_avisos_lote"))
        feitos, falhas = [], []
        for aviso_id in marcados:
            try:
                with db.transaction() as con:
                    r = PILOTE.registrar_um(
                        con, pdf, aviso_id,
                        quando=_campo(f"quando_{aviso_id}") or None,
                        desfecho=_campo(f"desfecho_{aviso_id}") or None,
                        pasta_de_arquivos=pasta_dos_arquivos(), agora=agora(),
                        usuario=usuario_nome(),
                        usuario_id=usuario_id_do_sistema())
            except (PILOTE.LoteError, AV.AvisoError, PT.ProtestoError) as erro:
                falhas.append(str(erro))
                continue
            feitos.append(r)
            audit("PROTESTO_AVISO_LOTE", "pt_avisos", aviso_id,
                  {"acao": r["acao"], "ato_id": r["ato_id"],
                   "anexo_id": r["anexo_id"], "paginas": r["paginas"],
                   "lote": sha})
        if feitos:
            entregas = sum(1 for r in feitos if r["acao"] == "ENTREGA")
            tentativas = sum(1 for r in feitos if r["acao"] == "TENTATIVA")
            flash(f"{len(feitos)} aviso(s) do PDF registrados: {entregas} "
                  f"entrega(s) lavrada(s), {tentativas} tentativa(s) "
                  f"registrada(s) e {len(feitos)} comprovante(s) "
                  f"anexado(s).", "success")
        for f in falhas:
            flash(f, "danger")
        return redirect(url_for("protesto_avisos") + "#entregues")

    @app.route("/protesto/avisos/<int:aviso_id>/digital", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_aviso_digital(aviso_id: int):
        """Lavra a intimação que a Resolve confirmou. ESCREVE.

        Só com a confirmação da plataforma (CN-MA art. 921, § 6º, II) — a
        recusa está no domínio, e diz o que falta.
        """
        try:
            with db.transaction() as con:
                r = AV.lavrar_intimacao_digital(con, aviso_id, agora=agora(),
                                                usuario=usuario_nome())
        except (AV.AvisoError, PT.ProtestoError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_avisos"))
        audit("PROTESTO_INTIMACAO_DIGITAL", "pt_avisos", aviso_id,
              {"ato_id": r["ato_id"], "identificador": r["identificador"],
               "so_entregue": r.get("so_entregue")})
        flash("Intimação digital lavrada, pela entrega comprovada na Resolve "
              "(CN-MA art. 919, § 1º)." if r.get("so_entregue") else
              "Intimação digital lavrada, com a confirmação da Resolve.",
              "success")
        return redirect(url_for("protesto_avisos"))

    def _papel_do_protesto(html: str, *, titulo: str,
                           qr_png: bytes | None = None,
                           qr_legenda: str = "",
                           rodape_html: str = "") -> bytes:
        """O `.odt` de um papel do protesto com o CABEÇALHO DA CASA.

        O mesmo `cabecalho_certidao_completo_odf` das certidões do RI e do
        RCPJ/RTD/Livro 3. Até 14/10/2026 o edital saía sem cabeçalho nenhum e
        o aviso nem tinha papel (conferência dos modelos do protesto).

        `qr_png` (15/10/2026) é o QR que identifica o papel quando ele volta
        escaneado — o do aviso, lido por `protesto_intimacoes_lote`. Ele vai
        onde o papel escrever `@@QRPAPEL@@` sozinho num parágrafo ou numa
        célula; sem a marca, vai no alto da primeira folha. `rodape_html` vem
        DEPOIS da assinatura — é onde mora o canhoto destacável do aviso.
        """
        s = sv()
        assinatura = (f'<p></p><p align="center">_________________________________</p>'
                      f'<p align="center">{s["serventia_titular"]}</p>'
                      f'<p align="center">{s["serventia_titulo"]}</p>')
        cab_odf, cab_imgs = RODT.cabecalho_certidao_completo_odf(s)
        imagens = dict(cab_imgs or {})
        fragmentos = None
        if qr_png:
            imagens["qr-do-papel.png"] = (qr_png, "image/png")
            fragmentos = {"@@QRPAPEL@@": (
                '<text:p text:style-name="P-centro">'
                '<draw:frame draw:style-name="Fr-qr" '
                'text:anchor-type="as-char" svg:width="2.5cm" '
                'svg:height="2.5cm"><draw:image '
                'xlink:href="Pictures/qr-do-papel.png" xlink:type="simple" '
                'xlink:show="embed" xlink:actuate="onLoad"/></draw:frame>'
                '</text:p>')}
            from html import escape as _esc
            if "@@QRPAPEL@@" not in html + rodape_html:
                html = ("<p>@@QRPAPEL@@</p>"
                        + (f'<p align="center"><small>{_esc(qr_legenda)}'
                           f'</small></p>' if qr_legenda else "")
                        + html)
        return gerar_odt(html_para_odf(html + assinatura + rodape_html,
                                       fragmentos=fragmentos), titulo=titulo,
                         cabecalho_odf=cab_odf, imagens=imagens or None,
                         cabecalho_altura_min="2.0cm",
                         cabecalho_margem_baixo="0.25cm",
                         cabecalho_borda=False)

    def _linhas_em_html(teor: str) -> str:
        from html import escape as _esc
        return "<p>" + "</p><p>".join(
            (_esc(x) or "&#160;") for x in str(teor).split("\n")) + "</p>"

    # ------------------------- os livros que a inspeção não achou (14/10/2026)

    # QUAIS colunas cada livro tem, e em que ordem, é daqui (CN-MA arts. 930
    # e 908); o título, o artigo e o nome de cada coluna são a peça
    # `PT_MOLDURAS` (LF06E), lida a cada pedido — `_livro_do_protesto`.
    LIVROS_DO_PROTESTO = {
        "pagamentos": {
            "colunas": ("ordem", "data", "protocolo", "natureza", "valor",
                        "emolumentos", "devedor", "favorecido", "ocorrencias"),
            "montar": PLIV.livro_de_pagamentos,
        },
        # O CPF/CNPJ DO DEVEDOR É COLUNA DO LIVRO (LD04) — CN-MA art. 906: o
        # número identificador consta «no Livro de Protocolo e em todos os
        # registros e certidões». Vai NO FIM (LD11, revisão do LD04): as oito
        # colunas de antes ficam onde estavam, e quem lê o livro por posição
        # não passa a ler o documento no lugar das ocorrências.
        "protocolo": {
            "colunas": ("ordem", "protocolo", "data", "natureza", "valor",
                        "apresentante", "devedor", "ocorrencias", "documento"),
            "montar": PLIV.livro_de_protocolo,
        },
    }

    def _livro_do_protesto(con, qual: str) -> dict | None:
        """O livro com o título, o artigo e as colunas por extenso. Só LÊ."""
        import protesto_pecas as PECAS
        livro = LIVROS_DO_PROTESTO.get(qual)
        if not livro:
            return None
        m = PECAS.rotulos(con, "PT_MOLDURAS")
        return {**livro, "titulo": m(f"{qual}_titulo"),
                "artigo": m(f"{qual}_artigo"),
                "colunas": [(c, m(f"{qual}_{c}")) for c in livro["colunas"]],
                "periodo": m}

    @app.route("/protesto/livros/<qual>")
    @login_required
    def protesto_livro(qual: str):
        """O Livro de Pagamentos ou o de Protocolo, por período. Só LÊ.

        A inspeção de 2021 marcou o Livro de Registro de Pagamentos como
        inexistente, e a de 2026 de novo (tarefas #52 e #54, relato #128).
        Com `?formato=odt` sai o papel, com o cabeçalho da casa.
        """
        if qual not in LIVROS_DO_PROTESTO:
            abort(404)
        de = (request.args.get("de") or hoje()[:8] + "01")[:10]
        ate = (request.args.get("ate") or hoje())[:10]
        with db.connect() as con:
            livro = _livro_do_protesto(con, qual)
            linhas = livro["montar"](con, de=de, ate=ate)
        if request.args.get("formato") == "odt":
            from html import escape as _esc
            cab = "".join(f"<th>{_esc(r)}</th>" for _, r in livro["colunas"])
            corpo = "".join(
                "<tr>" + "".join(f"<td>{_esc(str(l.get(c) if l.get(c) is not None else ''))}</td>"
                                 for c, _ in livro["colunas"]) + "</tr>"
                for l in linhas)
            periodo = livro["periodo"]("livro_periodo", de=_br_data(de),
                                       ate=_br_data(ate), quantos=len(linhas),
                                       artigo=_esc(livro["artigo"]))
            html = (f'<p align="center"><b>{_esc(livro["titulo"]).upper()}</b></p>'
                    f'<p align="center">{periodo}</p>'
                    f'<table border="1"><tr>{cab}</tr>{corpo}</table>')
            audit("PROTESTO_LIVRO_ODT", "pt_atos", 0,
                  {"livro": qual, "de": de, "ate": ate, "linhas": len(linhas)})
            return Response(
                _papel_do_protesto(html, titulo=livro["titulo"]),
                mimetype="application/vnd.oasis.opendocument.text",
                headers={"Content-Disposition":
                         f'attachment; filename="livro-{qual}-{de}-a-{ate}.odt"'})
        return render_template("protesto_livro.html", livro=livro, qual=qual,
                               linhas=linhas, de=de, ate=ate)

    def _br_data(iso: str) -> str:
        s_ = str(iso or "")[:10]
        return f"{s_[8:10]}/{s_[5:7]}/{s_[:4]}" if len(s_) == 10 else s_

    @app.route("/protesto/pagamentos/<int:ato_id>/quitacao.odt")
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_quitacao_odt(ato_id: int):
        """A QUITAÇÃO DO TÍTULO EM PAPEL — que até 21/10/2026 não existia (LD04).

        Lei 9.492/1997, art. 19, § 2º: «No ato do pagamento, o Tabelionato de
        Protesto dará a respectiva quitação»; CN-MA art. 927. O recibo do
        Caixa é o dos emolumentos; este é o do valor do título, e sai do
        pagamento já lançado no Livro de Registro de Pagamentos (art. 930,
        § 1º) — por isso o endereço é o do ATO. Só LÊ: o teor se remonta do
        que o ato guardou, com o selo do próprio pagamento (CN-MA art. 131).

        QUEM EMITE É QUEM LANÇA O PAGAMENTO (LD11, revisão do LD04): os mesmos
        papéis de `protesto_lancar`. Só com o login, qualquer conta tirava a
        quitação de qualquer pagamento — e ela é o papel que o devedor mostra
        para provar que pagou. O AUDITOR confere a ficha e o livro, e não
        entrega quitação. A auditoria fica: é o rastro de quem tirou o papel.
        """
        import protesto_pecas as PECAS
        with db.connect() as con:
            try:
                q = PLIV.quitacao(con, ato_id)
            except PLIV.QuitacaoError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("protesto_titulos"))
            etiqueta = AS.etiqueta_do_ato(con, "pt_atos", int(ato_id), "")
            m = PECAS.rotulos(con, "PT_MOLDURAS")
        s = sv()
        from datetime import date as _date
        from html import escape as _esc
        try:
            quando = data_por_extenso(_date.fromisoformat(str(q["data_ato"])[:10]))
        except (TypeError, ValueError):
            quando = _br_data(q["data_ato"])
        html = (f'<p align="center"><b>{m("quitacao_titulo")}</b></p><p></p>'
                + "".join(f"<p>{_esc(x)}</p>" for x in q["linhas"])
                + f'<p></p><p>{m("local_e_data", cidade=s.get("ri_cidade", ""), uf=s.get("ri_uf", ""), data=quando)}</p>'
                f'<p></p><p></p>'
                f'<p align="center">_________________________________</p>'
                f'<p align="center">{s["serventia_titular"]}</p>'
                f'<p align="center">{s["serventia_titulo"]}</p>')
        frag_do_selo, imagens_do_selo = RODT.carimbo_da_certidao_odf(etiqueta)
        cab_odf, cab_imgs = RODT.cabecalho_certidao_completo_odf(s)
        todas = dict(cab_imgs or {})
        todas.update(imagens_do_selo or {})
        arquivo = gerar_odt(html_para_odf(html) + frag_do_selo,
                            titulo=m("quitacao_titulo"),
                            cabecalho_odf=cab_odf, imagens=todas or None,
                            cabecalho_altura_min="2.0cm",
                            cabecalho_margem_baixo="0.25cm",
                            cabecalho_borda=False)
        audit("PROTESTO_QUITACAO_ODT", "pt_atos", ato_id,
              {"titulo_id": q["titulo_id"]})
        return IMPW.resposta_do_papel(
            arquivo, nome=f"quitacao-{ato_id}", get_setting=db.get_setting,
            voltar_para=url_for("protesto_titulo", titulo_id=q["titulo_id"]))

    @app.route("/protesto/avisos/<int:aviso_id>.odt")
    @login_required
    def protesto_aviso_odt(aviso_id: int):
        """O AVISO DE INTIMAÇÃO EM PAPEL — que até 14/10/2026 não existia.

        Os itens são os do Código de Normas, arts. 920 e 923 (ver
        `protesto_aviso.montar_teor_do_aviso`). A assinatura pode ser chancela
        ou pré-impressão (art. 923, parágrafo único).
        """
        with db.connect() as con:
            aviso = AV.ler(con, aviso_id)
            if not aviso:
                abort(404)
            try:
                teor = AV.montar_teor_do_aviso(con, aviso, sv=sv())
            except AV.AvisoError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("protesto_titulo",
                                        titulo_id=aviso["titulo_id"]))
        audit("PROTESTO_AVISO_ODT", "pt_avisos", aviso_id,
              {"numero": aviso["numero"], "ano": aviso["ano"]})
        # O QR DO AVISO (15/10/2026): quando o papel volta assinado e
        # escaneado num maço, é ele que diz de que aviso é cada folha.
        with db.connect() as con:
            tit = banco(con).um("SELECT protocolo FROM pt_titulos WHERE id=%s",
                                (int(aviso["titulo_id"]),))
        qr = PILOTE.png_do_qr(PILOTE.conteudo_do_qr(
            aviso, tit["protocolo"] if tit else ""))
        # O CANHOTO DESTACÁVEL (15/10/2026): o aviso fica com o devedor; a
        # parte de baixo volta assinada, e é ela que se escaneia no lote — por
        # isso o QR mora nela.
        import protesto_pecas as PECAS
        with db.connect() as con:
            canhoto = AV.canhoto_do_aviso(con, aviso)
            destaque = PECAS.rotulos(con, "PT_MOLDURAS")("canhoto_destaque")
        from html import escape as _esc
        rodape = (
            f'<p align="center">{destaque}</p>'
            f'<p align="center"><strong>{_esc(canhoto["titulo"])}</strong></p>'
            '<table cols="3cm,14cm"><tr><td><p>@@QRPAPEL@@</p></td><td>'
            + "".join(f"<p>{_esc(x)}</p>" for x in canhoto["identificacao"])
            + "</td></tr></table>"
            + "".join(f"<p>{_esc(x)}</p>" for x in canhoto["campos"])
            + f'<p><strong>{_esc(canhoto["tentativas_titulo"])}</strong></p>'
            + "".join(f"<p>{_esc(x)}</p>" for x in canhoto["tentativas"]))
        arquivo = _papel_do_protesto(
            _linhas_em_html(teor),
            titulo=f"Aviso {aviso['numero']}/{aviso['ano']}", qr_png=qr,
            rodape_html=rodape)
        return IMPW.resposta_do_papel(
            arquivo, nome=f"aviso-{aviso['numero']}-{aviso['ano']}",
            get_setting=db.get_setting,
            voltar_para=url_for("protesto_titulo", titulo_id=aviso["titulo_id"]))

    @app.route("/protesto/editais/<int:edital_id>.odt")
    @login_required
    def protesto_edital_odt(edital_id: int):
        """O edital em `.odt`, para imprimir e afixar.

        Sai o TEOR CONGELADO, e não um texto montado agora: é o papel que
        substitui a intimação pessoal, e se ele mudasse depois ninguém saberia
        o que foi afixado.
        """
        with db.connect() as con:
            linha = AV.edital(con, edital_id)
        if not linha:
            abort(404)
        html = _linhas_em_html(linha["teor"])
        audit("PROTESTO_EDITAL_ODT", "pt_editais", edital_id,
              {"numero": linha["numero"], "ano": linha["ano"]})
        return Response(
            _papel_do_protesto(html, titulo=f"Edital {linha['numero']}/{linha['ano']}"),
            mimetype="application/vnd.oasis.opendocument.text",
            headers={"Content-Disposition":
                     f'attachment; filename="edital-{linha["numero"]}-'
                     f'{linha["ano"]}.odt"'})

    @app.route("/protesto/editais/dia.odt")
    @login_required
    def protesto_editais_do_dia_odt():
        """A folha do dia, com todos os editais publicados. Para a parede.

        UMA FOLHA, VÁRIOS EDITAIS. O registro é um por aviso — como em
        `tbEdital`, 1.086 linhas —, mas o que se prega na parede é uma folha
        só. Isso é relatório, e não registro.
        """
        import protesto_pecas as PECAS
        dia = (request.args.get("dia") or hoje())[:10]
        with db.connect() as con:
            editais = AV.editais_do_dia(con, dia)
            separador = PECAS.rotulos(con, "PT_MOLDURAS")("editais_separador")
        if not editais:
            flash(f"Nenhum edital publicado em {dia}.", "warning")
            return redirect(url_for("protesto_avisos"))
        partes = []
        for e in editais:
            partes.append("<p>" + "</p><p>".join(
                (x or "&#160;") for x in str(e["teor"]).split("\n")) + "</p>")
        html = f"<p>&#160;</p><p>{separador}</p><p>&#160;</p>".join(partes)
        audit("PROTESTO_EDITAIS_DIA", "pt_editais", 0,
              {"dia": dia, "editais": len(editais)})
        return Response(
            _papel_do_protesto(html, titulo=f"Editais de {dia}"),
            mimetype="application/vnd.oasis.opendocument.text",
            headers={"Content-Disposition":
                     f'attachment; filename="editais-{dia}.odt"'})

    # --------------------------------------- a remessa que CHEGA da CRA

    @app.route("/protesto/remessas")
    @login_required
    def protesto_remessas():
        """O que a CRA mandou, e o que a casa recebeu. Só LÊ.

        É O PASSO DO MEIO-DIA do roteiro do oficial: «recebimento de remessa,
        confirmação e emissão do aviso». 93% dos títulos desta casa entram por
        aqui — até esta tela existir, não havia por onde.
        """
        with db.connect() as con:
            recebidas = PRM.listar(con)
        return render_template("protesto_remessas.html", recebidas=recebidas,
                               hoje=hoje(), remessas_salvas=PCIMG.listar_xml(pasta_dos_arquivos()))

    @app.route("/protesto/remessas/conferir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_remessa_conferir():
        """Lê o arquivo e mostra o que vai acontecer. NÃO GRAVA NADA.

        É o primeiro dos dois passos, e ele existe para o lote não entrar sem
        ninguém olhar: cinquenta títulos que entram sem conferência são
        cinquenta atos para desfazer à mão.
        """
        enviado = request.files.get("arquivo")
        if not enviado or not enviado.filename:
            flash("Escolha o arquivo da remessa que baixou da CRA.", "warning")
            return redirect(url_for("protesto_remessas"))
        return _conferir_a_remessa(enviado.read(), enviado.filename)

    @app.route("/protesto/remessas/da-cra", methods=["POST"])
    # 21/10/2026: aberto às escreventes por ordem do oficial (era ("ADMIN", "MANAGER")).
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_remessa_da_cra():
        """Traz a remessa da CRA pela API e LEVA DIRETO À CONFERÊNCIA.

        Até 14/10/2026 o botão da API só baixava o arquivo cru para o
        computador, e era preciso subi-lo à mão na tela da remessa. Aqui ele
        cai na MESMA conferência do upload — que não grava nada: os títulos
        só entram no «Receber», depois de alguém olhar. Se o leitor não
        entender o que a Central devolveu, a tela diz isso, e o arquivo cru
        continua a um clique na tela da API.

        BAIXAR MARCA DO LADO DE LÁ (manual da CRA): por isso é botão, e não
        relógio.
        """
        import cra21_web as CRAW
        qual = (_campo("o_que") or "remessa").strip()
        if qual not in ("remessa", "pendentes"):
            flash("Só a remessa do dia e as pendentes vão à conferência.", "warning")
            return redirect(url_for("protesto_remessas"))
        nome = _campo("nome")
        try:
            PCIMG.preparar_pasta(pasta_dos_arquivos())
            texto = CRAW._trazer(qual, nome, CENTCRED.PRODUCAO,
                                 com_imagem=_campo("com_imagem") != "0")
        except (*CRAW.RECUSAS_DO_BALCAO, PCIMG.ImagemCraError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_remessas"))
        audit("cra_baixar_e_conferir", None, None,
              {"o_que": qual, "nome": nome, "tamanho": len(texto or "")})
        if not str(texto or "").strip():
            flash("A CRA não devolveu remessa nenhuma agora.", "warning")
            return redirect(url_for("protesto_remessas"))
        return _conferir_a_remessa(texto, nome or f"cra-{qual}")

    def _conferir_a_remessa(bruto, nome_arquivo: str):
        """A conferência da remessa — a mesma para o upload e para a API."""
        if PCRAXML.parece_xml(bruto):
            # SÓ PRODUÇÃO desde 14/10/2026: o padrão era HOMOLOGACAO.
            ambiente = str(request.form.get("origem_xml_ambiente")
                           or CENTCRED.PRODUCAO).strip().upper()
            if isinstance(bruto, str):
                bruto = re.sub(r"(?i)(<\?xml[^>]*encoding\s*=\s*['\"])(?:iso-8859-1|windows-1252)(['\"])",
                               r"\1UTF-8\2", bruto, count=1).encode("utf-8")
            try:
                token = PCIMG.guardar_xml(pasta_dos_arquivos(), bruto)
            except PCIMG.ImagemCraError as erro:
                # Se o disco falhar depois da resposta, entregar o XML ao
                # navegador preserva o arquivo sem pedir outro download à CRA.
                flash(str(erro) + " Guarde o XML que está sendo baixado no computador.", "danger")
                return Response(bruto, mimetype="application/xml",
                                headers={"Content-Disposition": 'attachment; filename="remessa-cra-recuperar.xml"'})
            try:
                previa = PCRAXML.ler(bruto)
                with db.connect() as con:
                    visto = PRM.conferir_xml(con, bruto, ambiente)
            except (PCRAXML.RemessaXmlError, PRM.RemessaError, PCIMG.ImagemCraError,
                    PA.ArquivoError) as erro:
                flash(str(erro), "danger")
                return redirect(url_for("protesto_remessas"))
            return render_template(
                "protesto_remessa_conferir.html", visto=visto,
                nome_arquivo=nome_arquivo, conteudo="", origem_xml_token=token,
                hoje=hoje(), xml_previa=previa,
                origem_xml_ambiente=ambiente)
        try:
            with db.connect() as con:
                visto = PRM.conferir(con, bruto)
        except (PRM.RemessaError, PA.ArquivoError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_remessas"))
        return render_template("protesto_remessa_conferir.html", visto=visto,
                               nome_arquivo=nome_arquivo,
                               conteudo=PRM.normalizar(bruto), hoje=hoje())

    @app.route("/protesto/remessas/salvas/<token>")
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_remessa_salva(token):
        """Baixa a cópia local do XML que a CRA mandou. Só LÊ (3.6.293.3).

        A cópia existe para não pedir de novo à Central: baixar marca a
        remessa como baixada do lado de lá, e o segundo pedido pode vir vazio.
        """
        try:
            caminho = PCIMG.caminho_xml(pasta_dos_arquivos(), token)
        except PCIMG.ImagemCraError:
            abort(404)
        return send_file(caminho, as_attachment=True, download_name=f"remessa-cra-{token[:12]}.xml")

    @app.route("/protesto/remessas/salvas/<token>/conferir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_remessa_salva_conferir(token):
        """Retoma a conferência pela cópia local, sem chamar a CRA. NÃO GRAVA."""
        try:
            bruto = PCIMG.caminho_xml(pasta_dos_arquivos(), token).read_bytes()
        except PCIMG.ImagemCraError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_remessas"))
        return _conferir_a_remessa(bruto, "remessa-cra.xml")

    @app.route("/protesto/remessas/receber", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_remessa_receber():
        """Recebe o lote: cadastra, aponta e confirma. ESCREVE.

        O LOTE NÃO SELA E NÃO COBRA, e é de propósito: selar cinquenta títulos
        são cinquenta chamadas de rede de 20 s dentro de um `BEGIN IMMEDIATE`,
        e a casa inteira ficaria esperando o lote. Eles entram e aparecem em
        *atos sem selo* e *atos sem cobrança*, que são as telas do outro lado.

        AS IMAGENS t51 (3.6.293.3) entram na MESMA transação dos títulos: a
        remessa XML vem pela cópia local (`origem_xml_token`), e não por um
        campo escondido do formulário — com as imagens em base64 ela pode ir
        a 64 MB, e o que se recebe é o arquivo conferido, pelo sha256.
        """
        conteudo = request.form.get("conteudo") or ""
        token = _campo("origem_xml_token")
        if token:
            try:
                conteudo = PCIMG.caminho_xml(pasta_dos_arquivos(), token).read_bytes()
            except PCIMG.ImagemCraError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("protesto_remessas"))
        if not conteudo.strip():
            flash("O arquivo não veio junto. Escolha-o de novo.", "warning")
            return redirect(url_for("protesto_remessas"))
        try:
            with db.transaction() as con:
                if PCRAXML.parece_xml(conteudo):
                    r = PRM.receber_xml(
                        con, conteudo,
                        ambiente=_campo("origem_xml_ambiente") or "HOMOLOGACAO",
                        agora=agora(), data_extenso=hoje_extenso(),
                        sv=sv(), nome_arquivo=_campo("nome_arquivo") or None,
                        apontar=_campo("apontar") != "0",
                        marca=_campo("marca") or None,
                        usuario=usuario_nome(), pasta_de_arquivos=pasta_dos_arquivos(),
                        usuario_id=usuario_id_do_sistema())
                else:
                    r = PRM.receber(
                        con, conteudo, agora=agora(), data_extenso=hoje_extenso(),
                        sv=sv(), nome_arquivo=_campo("nome_arquivo") or None,
                        apontar=_campo("apontar") != "0",
                        marca=_campo("marca") or None,
                        usuario=usuario_nome())
        except (PCRAXML.RemessaXmlError, PRM.RemessaError, PA.ArquivoError,
                PT.ProtestoError, PCIMG.ImagemCraError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_remessas"))
        # `audit` abre transação própria: FORA do `with`, como no resto da casa.
        for lote in r["lotes"]:
            audit("PROTESTO_REMESSA", "pt_remessas", lote["remessa_id"],
                  {"apresentante": lote["apresentante_codigo"],
                   "recebidos": lote["recebidos"],
                   "apontados": lote["apontados"],
                   "recusados": lote["recusados"],
                   "confirmacao_id": lote["confirmacao_id"]})
        # O ANDAMENTO SAI JUNTO — ordem do oficial em 31/08/2026: «sempre que
        # recebe remessa, precisa gerar o andamento para atualizar a CRA sobre
        # o andamento».
        #
        # A confirmação diz «recebi»; o andamento diz «apontei», e é o que a
        # Central espera depois do apontamento. Medido nos arquivos de 2026:
        # 38 dos 39 títulos recebidos por remessa aparecem num andamento, e
        # ele vem na data da remessa ou depois em 38 de 38.
        #
        # UM POR APRESENTANTE: um arquivo traz mais de um lote em 3 de 25 das
        # remessas de 2026, e 2 delas com apresentantes diferentes. O
        # andamento volta para quem mandou.
        #
        # E FALHAR AQUI NÃO DESFAZ O RECEBIMENTO: os títulos entraram e foram
        # apontados, e isso é ato lavrado. O que não sair fica pendente, e a
        # tela do retorno o alcança.
        andamentos, sem_andamento = [], []
        for codigo in dict.fromkeys(l["apresentante_codigo"]
                                    for l in r["lotes"]):
            try:
                with db.transaction() as con:
                    a = PRE.gerar_andamento(
                        con, apresentante_codigo=codigo, dia=hoje(),
                        agora=agora(), marca=_campo("marca") or None,
                        usuario=usuario_nome())
                andamentos.append((codigo, a))
            except (PRE.RetornoError, PA.ArquivoError) as erro:
                sem_andamento.append((codigo, str(erro)))
        for codigo, a in andamentos:
            # `audit` abre transação própria: FORA do `with`.
            audit("PROTESTO_ANDAMENTO", "pt_retornos", a["andamento_id"],
                  {"apresentante": codigo, "titulos": len(a["atos"]),
                   "de": "remessa recebida"})

        recusados = r["recusados"]
        aviso = (f" {recusados} título(s) o contrato da CRA recusou — o motivo "
                 f"está no lote." if recusados else "")
        lotes = ("" if r["quantidade_de_lotes"] == 1
                 else f" em {r['quantidade_de_lotes']} lotes")
        andou = ("" if not andamentos else
                 f" O andamento saiu para "
                 f"{len(andamentos)} apresentante(s):"
                 f" {sum(len(a['atos']) for _, a in andamentos)} apontamento(s).")
        flash(f"Remessa recebida{lotes}: {r['recebidos']} título(s), "
              f"{r['apontados']} apontado(s).{aviso}{andou} "
              f"Confirmação e andamento seguem para a CRA quando o envio "
              f"automático estiver ligado; senão, baixe os dois arquivos e "
              f"suba na Central.", "success")
        for codigo, motivo in sem_andamento:
            flash(f"O andamento do apresentante {codigo} não saiu: {motivo} "
                  f"Os títulos foram apontados assim mesmo — o andamento fica "
                  f"pendente e sai pela tela do retorno.", "warning")

        ambiente_cra = PCRAENV.ambiente_da_remessa(
            r["lotes"][0] if r.get("lotes") else {})

        # A REDE FORA DA TRANSAÇÃO (13/10/2026): o envio recebe QUEM ABRE a
        # transação, e abre duas curtas — ler e gravar —, com a CRA no meio.
        from contextlib import contextmanager

        @contextmanager
        def _transacao_com_linhas():
            with db.transaction() as con:
                yield con

        try:
            envio = PCRAENV.enviar_pos_remessa(
                _transacao_com_linhas, lotes=r["lotes"], andamentos=andamentos,
                ambiente=ambiente_cra, ler_config=db.get_setting,
                usuario=usuario_nome())
        except (PCRAENV.CraEnvioError, CRAAPI.CraError, CENTCRED.CredencialError) as erro:
            flash(f"Envio automático à CRA não concluiu: {erro}", "warning")
            envio = None
        if envio and envio.get("auto") and not envio.get("motivo"):
            for item in envio.get("enviados") or []:
                audit("CRA_ENVIO", "pt_retornos", item["retorno_id"],
                      {"operacao": item["operacao"],
                       "ambiente": item["ambiente"],
                       "nome": item["nome_arquivo"],
                       "codigo": item.get("codigo")})
            for falha in envio.get("falhas") or []:
                audit("CRA_ENVIO_FALHA", "pt_retornos", falha["retorno_id"],
                      {"operacao": falha["operacao"], "erro": falha["erro"]})
            q_ok = len(envio.get("enviados") or [])
            q_err = len(envio.get("falhas") or [])
            if q_ok and not q_err:
                q_and = sum(1 for x in envio.get("enviados") or []
                            if x["operacao"] == "TituloComplemento")
                partes = [f"{q_ok - q_and} confirmação(ões)"]
                if q_and:
                    partes.append(f"{q_and} andamento(s)")
                flash(f"A CRA ({envio['ambiente'].lower()}) recebeu "
                      f"{' e '.join(partes)} pela API.", "success")
            elif q_ok:
                flash(f"A CRA recebeu {q_ok} arquivo(s); {q_err} falha(s) — "
                      f"veja o aviso abaixo e confira na Central antes de "
                      f"repetir.", "warning")
            for falha in envio.get("falhas") or []:
                flash(f"CRA — {falha['operacao']}: {falha['erro']}", "danger")
        elif envio and envio.get("motivo") and envio.get("auto"):
            flash(envio["motivo"], "info")

        return redirect(url_for("protesto_remessa",
                                remessa_id=r["remessas"][0]))

    @app.route("/protesto/remessas/<int:remessa_id>")
    @login_required
    def protesto_remessa(remessa_id: int):
        """O lote recebido: o que entrou, o que foi recusado e a confirmação."""
        with db.connect() as con:
            linha = PRM.remessa(con, remessa_id)
            if not linha:
                abort(404)
            titulos = PRM.titulos_da_remessa(con, remessa_id)
            recusas = PRM.recusas(linha)
            confirmacao = (PRE.retorno(con, linha["confirmacao_id"])
                           if linha["confirmacao_id"] else None)
        achados = []
        if linha["achados_json"]:
            try:
                achados = json.loads(linha["achados_json"])
            except ValueError:
                achados = []
        return render_template("protesto_remessa.html", remessa=dict(linha),
                               titulos=titulos, recusas=recusas,
                               achados=achados,
                               confirmacao=dict(confirmacao) if confirmacao
                               else None)

    @app.route("/protesto/remessas/<int:remessa_id>/arquivo")
    @login_required
    def protesto_remessa_arquivo(remessa_id: int):
        """O arquivo como CHEGOU, guardado inteiro.

        Quando a Central reclamar de um título, é este teor que se lê — a
        mesma regra do retorno. Sai em ISO-8859-1, que é como ele chegou.
        """
        with db.connect() as con:
            linha = PRM.remessa(con, remessa_id)
        if not linha:
            abort(404)
        nome = linha["nome_arquivo"] or f"remessa-{remessa_id}.txt"
        return Response(
            linha["conteudo"].encode("latin-1", errors="replace"),
            mimetype="text/plain; charset=ISO-8859-1",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    # ---------------------------- a desistência, que se confere 3x por dia

    # ------------------------------- o passo da tarde: gerar protesto

    @app.route("/protesto/a-protestar")
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_a_protestar():
        """Os títulos intimados e sem movimentação. SÓ LÊ.

        É o passo da tarde do roteiro que o oficial trouxe: «gerar protesto,
        sem movimentação, calcular, listar, gerar». Era o único passo do dia
        sem tela nenhuma — o título intimado ficava esperando alguém lembrar
        dele, um a um, na lista geral.

        O TRÍDUO SE CALCULA DESDE A TAREFA 56 (23/10/2026), que substituiu a
        decisão do oficial de 24/08/2026 («contar, e não julgar»). A tela
        mostra o termo inicial e o final de cada título; o que ainda não
        chegou ao termo inicial não se marca, e o que passou do final pede o
        motivo do atraso — a régua é `protesto_triduo`.
        """
        with db.connect() as con:
            # O TRÍDUO DE CADA UM (tarefa 56, 23/10/2026): o termo inicial e o
            # final, e onde hoje cai — a conta é `protesto_triduo`, a mesma
            # que `lancar_protesto` confere ao lavrar.
            linhas = TRIDUO.para_a_lista(
                con, PT.esperando_protesto(con, hoje=hoje()), hoje=hoje())
            # AS DUAS PONTAS DA SUSTACAO JUDICIAL — Lei 9.492/1997, art. 17.
            #
            # `revogados` vem PRIMEIRO na tela: e o unico titulo do Protesto
            # com prazo de UM DIA UTIL na lei (§ 2o), e sem nova intimacao.
            # `sustados` aparece porque saiu da fila de proposito — e titulo a
            # disposicao do Juizo que ninguem enxerga e titulo esquecido.
            revogados = PT.sustacao_revogada(con, hoje=hoje())
            sustados = PT.sustados(con)
        return render_template("protesto_a_protestar.html", linhas=linhas,
                               revogados=revogados, sustados=sustados,
                               hoje=hoje())

    @app.route("/protesto/a-protestar/lavrar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_a_protestar_lavrar():
        """Lavra o protesto dos títulos MARCADOS. ESCREVE.

        MARCADOS, E NÃO TODOS. A tela lista; quem escolhe é o oficial, título
        a título — «gerar» no roteiro dele vem depois de «listar», e entre os
        dois está a decisão. Um botão que protestasse a lista inteira faria o
        clique valer por vinte atos que não se desfazem.

        CADA UM É UM ATO PRÓPRIO, com número de ordem, lugar no livro e a sua
        data. O que se junta é o trabalho de clicar, e não o ato.

        O LOTE NÃO SELA E NÃO COBRA — a mesma regra da remessa, e pelo mesmo
        motivo: vinte selos são vinte chamadas de rede de 20 s, e segurá-las
        aqui poria toda a casa no `busy_timeout`. Eles aparecem em *atos sem
        selo* e *atos sem cobrança*, que são as telas do outro lado.

        E UM QUE FALHA NÃO DERRUBA OS OUTROS: cada título é lavrado na sua
        própria transação. Protesto lavrado é protesto lavrado; desfazer
        dezenove porque o vigésimo tinha um impedimento seria pior.
        """
        # o que não é número não foi marcado (LD13 — o «²» era a tela de erro)
        escolhidos = [n for n in (numero_digitado(x)
                                  for x in request.form.getlist("titulo_id"))
                      if n is not None]
        if not escolhidos:
            flash("Marque os títulos que vão a protesto. A lista não protesta "
                  "sozinha: quem decide é você, título a título.", "warning")
            return redirect(url_for("protesto_a_protestar"))

        feitos, falharam = [], []
        for titulo_id in escolhidos:
            try:
                with db.transaction() as con:
                    # O motivo do atraso é por título: cada um tem o seu
                    # tríduo, e o instrumento de cada um diz o seu motivo.
                    r = PT.lancar_protesto(
                        con, titulo_id, sv=sv(), agora=agora(),
                        data_extenso=hoje_extenso(), usuario=usuario_nome(),
                        modelo_do_termo=_modelo_do_termo(con),
                        conferir_triduo=True,
                        motivo_atraso=_campo(f"motivo_atraso_{titulo_id}") or None)
                feitos.append((titulo_id, r))
            except (PT.ProtestoError, LN.LivroError,
                    PTERMO.TermoError) as erro:
                falharam.append((titulo_id, str(erro)))

        for titulo_id, r in feitos:
            # `audit` abre transação própria: FORA do `with`.
            audit("PROTESTO_LAVRADO", "pt_atos", r.get("ato_id"),
                  {"titulo_id": titulo_id, "numero_ordem": r.get("numero_ordem"),
                   "em_lote": True})
        if feitos:
            flash(f"{len(feitos)} protesto(s) lavrado(s). Eles ainda não têm "
                  f"selo nem cobrança — veja em «Atos sem selo» e «Atos sem "
                  f"cobrança». E lembre de gerar o retorno E o andamento.",
                  "success")
        for titulo_id, motivo in falharam:
            flash(f"Título {titulo_id}: {motivo}", "danger")
        return redirect(url_for("protesto_a_protestar"))

    # ------------------------- as imagens dos títulos que a CRA entrega

    @app.route("/protesto/imagens", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_imagens():
        """Traz o pacote de imagens da CRA e anexa cada uma ao seu título.

        É A OUTRA METADE DO «DOWNLOAD» DA CRA. A tela da Central lista duas
        pendências lado a lado — «Download remessa» e **«Download imagens»** —,
        e o sistema fazia só a primeira. A imagem não é enfeite: **é o
        título**. O que se protesta é o documento, e é ele que o devedor pede
        para ver quando vem discutir a dívida no balcão.

        UM PASSO SÓ, E ISSO É DIFERENTE DA REMESSA — de propósito. Lá são dois
        (conferir e receber) porque **apontamento não se desfaz**: cinquenta
        títulos apontados sem ninguém olhar são cinquenta atos para desfazer à
        mão. Aqui nada é lavrado, nada toma número e nada gasta selo; e o que
        protege contra o erro grave — anexar a imagem ao título de outra
        pessoa — não é o clique de conferência, é a **dupla chave**: o módulo
        só anexa quando o nosso número E o documento do devedor apontam para o
        mesmo título.

        O que não casa **não entra**, e a tela diz de cada um por quê.
        """
        with db.connect() as con:
            sem_imagem = PIMG.titulos_sem_imagem(con, limite=50)

        resultado = None
        if request.method == "POST":
            enviado = request.files.get("arquivo")
            if not enviado or not enviado.filename:
                flash("Escolha o pacote .zip que você baixou em «Download "
                      "imagens» na CRA.", "warning")
                return redirect(url_for("protesto_imagens"))
            try:
                with db.transaction() as con:
                    resultado = PIMG.guardar(
                        con, enviado.read(),
                        pasta_de_arquivos=pasta_dos_arquivos(),
                        agora=agora(), usuario_id=usuario_id_do_sistema(),
                        origem=enviado.filename)
            except PIMG.ImagemError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("protesto_imagens"))
            # `audit` abre transação própria: FORA do `with`.
            audit("PROTESTO_IMAGENS", "attachments", None,
                  {"arquivo": enviado.filename,
                   "guardadas": len(resultado["guardadas"]),
                   "fora": len(resultado["fora"])})
            flash(f"{len(resultado['guardadas'])} imagem(ns) anexada(s) aos "
                  f"títulos.", "success")
            with db.connect() as con:
                sem_imagem = PIMG.titulos_sem_imagem(con, limite=50)

        return render_template("protesto_imagens.html", resultado=resultado,
                               sem_imagem=sem_imagem)

    @app.route("/protesto/imagens/<int:anexo_id>")
    @login_required
    def protesto_imagem(anexo_id: int):
        """Abre a imagem do título. SÓ LÊ.

        O CAMINHO VEM DO BANCO, e o arquivo é lido de lá — mas só depois de a
        linha dizer que ele é anexo de TÍTULO. Sem essa conferência, esta rota
        serviria qualquer arquivo da casa a quem trocasse o número no endereço.
        """
        with db.connect() as con:
            linha = banco(con).um(
                "SELECT * FROM attachments WHERE id=%s AND entity_type=%s",
                (anexo_id, PIMG.ENTIDADE))
        if not linha:
            abort(404)
        caminho = Path(linha["stored_path"])
        if not caminho.is_file():
            flash("O arquivo da imagem não está mais no disco. Baixe o pacote "
                  "da CRA de novo.", "danger")
            return redirect(url_for("protesto_imagens"))
        # EM LINHA SÓ O QUE O NAVEGADOR DESENHA SEM EXECUTAR, E COM OS
        # CABEÇALHOS DE QUEM MOSTRA (LS02 M11; LX12, 19/10/2026): `nosniff`,
        # `sandbox` e o tipo declarado pelo nome — a régua do `/arquivo/<id>/ver`.
        # Hoje só a lista de extensões do pacote da CRA segurava.
        nome = linha["original_name"]
        if not ARQVIS.abre_na_tela(nome):
            return send_file(caminho, as_attachment=True, download_name=nome)
        resposta = send_file(caminho, as_attachment=False, download_name=nome,
                             mimetype=ARQVIS.tipo_do_arquivo(nome))
        for chave, valor in ARQVIS.cabecalhos_para_mostrar().items():
            resposta.headers[chave] = valor
        return resposta

    # ------------------- a pagina principal do Protesto: o roteiro do dia

    @app.route("/protesto/roteiro")
    @login_required
    def protesto_painel():
        """O ROTEIRO DAS CENTRAIS, na primeira tela do Protesto. SÓ LÊ.

        Pedido do oficial em 01/09/2026: *«coloque o checklist na página
        principal do protesto no sistema, para amplo acesso dos escreventes»* —
        depois de juntar dois papéis, o **Roteiro das Centrais de Protesto** do
        TJMA e o **Ofício Circular IEPTB-MA/CRA-MA nº 015/2025**.

        **ISTO NÃO ESTÁ NO ACERVO, E NÃO SE DESCOBRE MEDINDO.** O acervo guarda
        o que foi lavrado; a ordem em que se faz, e a hora até a qual se pode
        fazer, são combinação com a Central. É a segunda vez que um papel do
        oficial ensina o que nenhuma medição daria — a primeira foi o «sempre
        que gerar retorno, gerar andamento».

        **`@login_required`, e não `@roles_required`**: o pedido é «amplo
        acesso dos escreventes», e esta tela **não faz nada** — lista o
        roteiro, aponta a tela de cada passo e conta o que já aconteceu hoje.
        Trancá-la por perfil seria trancar a instrução, e não o ato.

        E **ela conta, mas não julga**: um zero pode ser «ainda não fiz» ou
        «hoje não veio nada da Central», e o sistema não tem como saber qual.
        Dizer «atrasado» sobre um dia em que nada chegou é o alarme que soa
        sempre.
        """
        with db.connect() as con:
            dados = PROT.roteiro(con, hoje=hoje())
        return render_template("protesto_painel.html", r=dados,
                               cobertura=PROT.quantos_o_sistema_faz())

    # ------------------- a chave do CENPROT, que o XML devolve

    def _acervo_se_houver():
        """O acervo do E-Ofício em só leitura, ou None. É dele que vem o
        registro da CRA dos títulos que entraram antes da virada."""
        try:
            return AC.abrir_acervo(acervo_no_disco())
        except AC.CargaError:
            return None

    @app.route("/protesto/cenprot-xml")
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_cenprot_xml():
        """O XML diário que a casa sobe à CENPROT — P (protestos) e D (pagos,
        retirados e cancelados). Só LÊ.

        A casa NÃO manda apontamento: o título já tem a chave, que vem do XML
        que a Central devolve. O que entra é o que ESTE sistema lavrou e a
        Central ainda não recebeu; o que não pode entrar aparece com o motivo.
        """
        acervo = _acervo_se_houver()
        try:
            with db.connect() as con:
                listas = {letra: PCXML.pendentes(con, letra, acervo=acervo)
                          for letra in ("P", "D")}
                feitos = PCXML.arquivos(con)
                cadastro = PCXML.apresentantes(con)
        finally:
            if acervo is not None:
                acervo.close()
        return render_template(
            "protesto_cenprot_xml.html", listas=listas, feitos=feitos,
            cadastro=cadastro, tem_acervo=acervo is not None,
            ocorrencias={"PROTESTO": "2 — protestado", "PAGAMENTO": "1 — pago",
                         "DESISTENCIA": "3 — retirado",
                         "CANCELAMENTO": "A — cancelado"})

    @app.route("/protesto/cenprot-xml/gerar", methods=["POST"])
    # 21/10/2026: aberto às escreventes por ordem do oficial (era ("ADMIN")).
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_cenprot_xml_gerar():
        """Gera o arquivo do dia, guarda e marca os atos. ESCREVE.

        Cada ato vai a UM arquivo só: a marca é gravada na mesma transação do
        arquivo. O envio é pelo portal da CENPROT — a API dela não tem caminho
        para este arquivo.
        """
        letra = (request.form.get("letra") or "").strip().upper()
        config = db.get_settings()
        acervo = _acervo_se_houver()
        try:
            casa = PCEN.identidade_da_casa(config)
            with db.transaction() as con:
                feito = PCXML.gerar(
                    con, letra, uf=str(config.get("ri_uf") or "MA").strip(),
                    dia=hoje(), agora=agora(), usuario=usuario_nome(),
                    acervo=acervo, **casa)
        except (PCXML.CenprotXmlError, PCEN.CenprotError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_cenprot_xml"))
        finally:
            if acervo is not None:
                acervo.close()
        audit("PROTESTO_CENPROT_XML_GERADO", "pt_cenprot_xml", feito["id"],
              {"arquivo": feito["nome"], "titulos": feito["titulos"]})
        flash(f"Arquivo {feito['nome']} gerado com {feito['titulos']} "
              f"título(s). Baixe e suba no portal da CENPROT."
              + (f" {len(feito['fora'])} ficaram de fora — veja o motivo de "
                 f"cada um." if feito["fora"] else ""), "success")
        return redirect(url_for("protesto_cenprot_xml"))

    @app.route("/protesto/cenprot-xml/<int:xml_id>/baixar")
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_cenprot_xml_baixar(xml_id: int):
        """O arquivo como foi gerado, byte a byte (com o BOM). Só LÊ."""
        with db.connect() as con:
            arq = PCXML.arquivo(con, xml_id)
        if not arq:
            abort(404)
        return Response(
            bytes(arq["conteudo"]), mimetype="application/xml",
            headers={"Content-Disposition":
                     f'attachment; filename="{arq["nome_arquivo"]}"'})

    @app.route("/protesto/cenprot-xml/apresentantes", methods=["POST"])
    # 21/10/2026: aberto às escreventes por ordem do oficial (era ("ADMIN", "MANAGER")).
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_cenprot_xml_apresentante():
        """Cadastra ou corrige um apresentante (CNPJ, tipo e, desde o LD08, o
        endereço que o registro e o instrumento levam). ESCREVE."""
        codigo = (request.form.get("codigo") or "").strip()
        try:
            with db.transaction() as con:
                PCXML.gravar_apresentante(
                    con, codigo=codigo, nome=request.form.get("nome"),
                    documento=request.form.get("documento"),
                    tipo_apresentante=request.form.get("tipo_apresentante"),
                    endereco=request.form.get("endereco"),
                    agora=agora(), usuario=usuario_nome())
        except PCXML.CenprotXmlError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_cenprot_xml"))
        audit("PROTESTO_APRESENTANTE_GRAVADO", "pt_apresentantes", None,
              {"codigo": codigo})
        flash(f"Apresentante {codigo} gravado.", "success")
        return redirect(url_for("protesto_cenprot_xml"))

    @app.route("/protesto/cenprot-xml/apresentantes/acervo", methods=["POST"])
    # 21/10/2026: aberto às escreventes por ordem do oficial (era ("ADMIN", "MANAGER")).
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_cenprot_xml_apresentantes_do_acervo():
        """Traz os apresentantes do E-Ofício (`tbCobrador`). ESCREVE.

        O que alguém já corrigiu à mão não se sobrescreve.
        """
        acervo = _acervo_se_houver()
        if acervo is None:
            flash("O acervo do E-Ofício não está nesta máquina — cadastre os "
                  "apresentantes à mão, um por um.", "warning")
            return redirect(url_for("protesto_cenprot_xml"))
        try:
            with db.transaction() as con:
                r = PCXML.carregar_apresentantes(con, acervo, agora=agora())
        finally:
            acervo.close()
        audit("PROTESTO_APRESENTANTES_DO_ACERVO", "pt_apresentantes", None, r)
        flash(f"{r['entraram']} apresentante(s) trazido(s) do E-Ofício; "
              f"{r['mantidos']} já estavam no cadastro e ficaram como estavam.",
              "success")
        return redirect(url_for("protesto_cenprot_xml"))

    @app.route("/protesto/cenprot-xml/titulos-tab/acervo", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_cenprot_xml_titulos_tab_do_acervo():
        """Traz do E-Ofício o apresentante de cada título TAB (um por título:
        quem pediu na CENPROT). ESCREVE. Só preenche o que está vazio — a
        regra mora em `protesto_cenprot_xml.trazer_apresentantes_dos_titulos`.
        """
        acervo = _acervo_se_houver()
        if acervo is None:
            flash("O acervo do E-Ofício não está nesta máquina — informe o "
                  "apresentante de cada título TAB nesta tela.", "warning")
            return redirect(url_for("protesto_cenprot_xml"))
        try:
            with db.transaction() as con:
                r = PCXML.trazer_apresentantes_dos_titulos(con, acervo)
        except PCXML.CenprotXmlError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_cenprot_xml"))
        finally:
            acervo.close()
        audit("PROTESTO_APRESENTANTES_TAB_DO_ACERVO", "pt_titulos", None, r)
        flash(f"{r['completos']} título(s) TAB receberam nome, CNPJ/CPF e tipo "
              f"do E-Ofício ({r['nome_trocado']} com o nome trocado pelo que foi "
              f"à CENPROT); {r['so_o_tipo']} receberam só o tipo. "
              + (f"{len(r['divergentes'])} têm documento diferente do E-Ofício e "
                 f"ficaram como estavam (títulos {', '.join(map(str, r['divergentes']))}). "
                 if r["divergentes"] else "")
              + (f"{len(r['sem_fonte'])} não têm fonte no E-Ofício e esperam "
                 f"quem informe (títulos {', '.join(map(str, r['sem_fonte']))})."
                 if r["sem_fonte"] else ""),
              "warning" if (r["divergentes"] or r["sem_fonte"]) else "success")
        return redirect(url_for("protesto_cenprot_xml"))

    @app.route("/protesto/cenprot-xml/titulo/<int:titulo_id>/apresentante",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_cenprot_xml_apresentante_do_titulo(titulo_id: int):
        """Informa o apresentante de UM título TAB — nome, CNPJ/CPF e tipo.
        ESCREVE."""
        try:
            with db.transaction() as con:
                PCXML.gravar_apresentante_do_titulo(
                    con, titulo_id, nome=request.form.get("nome"),
                    documento=request.form.get("documento"),
                    tipo_apresentante=request.form.get("tipo_apresentante"))
        except PCXML.CenprotXmlError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_cenprot_xml"))
        audit("PROTESTO_APRESENTANTE_DO_TITULO_GRAVADO", "pt_titulos", titulo_id,
              {"tipo_apresentante": (request.form.get("tipo_apresentante") or "").strip()})
        flash(f"Apresentante do título {titulo_id} gravado.", "success")
        return redirect(url_for("protesto_cenprot_xml"))

    @app.route("/protesto/cenprot", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_cenprot():
        """Lê o XML do CENPROT e guarda a chave única de cada título.

        A CENTRAL CONHECE CADA TÍTULO POR UMA CHAVE DE 23 DÍGITOS, e esta casa
        não guardava nenhuma — `chave_cenprot` está vazia nos 1.366. Este
        projeto chegou a registrar que a chave tinha um «verificador que não se
        explica», e que por isso não dava para compô-la. **Não precisa
        compor**: o arquivo devolve a chave ao lado do NOSSO protocolo, em 175
        de 175 títulos do exemplar medido.

        UM PASSO SÓ, e a razão é a mesma das imagens: **nada aqui é lavrado**.
        Não toma número, não ocupa folha, não gasta selo e não muda situação —
        o que se escreve é uma coluna. O que protege contra o erro grave não é
        o clique de conferência, são **três guardas que o módulo aplica antes
        de gravar**:

          - o arquivo tem de ser **desta serventia** (comarca e cartório do
            cabeçalho contra as configurações do IBGE) — sem isso, o arquivo da
            casa vizinha escreveria aqui as chaves dos títulos dela;
          - o título se acha pelo protocolo **e** se confere pelo nosso número
            (ou, sem ele, pelo valor);
          - chave que já está lá **não se sobrescreve**.

        O que não casa **não derruba o arquivo**, e a tela diz de cada um por
        quê — é a regra do lote da remessa.
        """
        config = db.get_settings()
        resultado = None
        with db.connect() as con:
            quadro = PCEN.quantos_sem_chave(con)

        if request.method == "POST":
            enviado = request.files.get("arquivo")
            if not enviado or not enviado.filename:
                flash("Escolha o arquivo .xml que você baixou no CENPROT — o "
                      "do protesto tem a letra «P» no nome.", "warning")
                return redirect(url_for("protesto_cenprot"))
            bruto = enviado.read()
            # CONFERIR PRIMEIRO, MESMO SENDO UM PASSO SÓ — e isto foi correção
            # de 01/09/2026, apanhada pelo teste de TELA.
            #
            # Eu chamava `guardar` direto. Quando nada entra — arquivo já
            # trazido, ou nenhum título casando — ele **recusa**, que é certo
            # do lado do domínio: quem ignora o retorno não pode achar que
            # deu certo. Só que a rota respondia com `flash` e `redirect`, e o
            # redirecionamento **jogava fora a lista do que não casou e por
            # quê** — a informação mais útil, descartada justamente no caso em
            # que ela é a única coisa que há para ver.
            #
            # Agora a conferência sempre aparece; `guardar` só é chamado
            # quando há o que gravar, e continua recusando para quem o chamar
            # de outro lugar.
            try:
                casa = PCEN.identidade_da_casa(config)
                with db.connect() as con:
                    visto = PCEN.conferir(con, bruto, **casa)
                if visto["entram"]:
                    with db.transaction() as con:
                        resultado = PCEN.guardar(con, bruto, **casa)
                else:
                    resultado = {**visto, "gravadas": 0}
            except PCEN.CenprotError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("protesto_cenprot"))
            # `audit` abre transação própria: FORA do `with`.
            audit("PROTESTO_CENPROT", "pt_titulos", None,
                  {"arquivo": enviado.filename,
                   "versao": resultado["versao"],
                   "gravadas": resultado["gravadas"],
                   "ja_tinham": len(resultado["ja_tem"]),
                   "divergem": len(resultado["divergem"]),
                   "fora": len(resultado["fora"])})
            if resultado["gravadas"]:
                flash(f"{resultado['gravadas']} chave(s) do CENPROT "
                      f"guardada(s).", "success")
            else:
                # NÃO É ERRO, E NÃO É SUCESSO: nada mudou, e a tela abaixo diz
                # de cada título por quê. Dizer «pronto» aqui seria o carimbo
                # que mente.
                flash(f"Nenhuma chave nova: dos {resultado['total']} títulos "
                      f"do arquivo, {len(resultado['ja_tem'])} já tinham a "
                      f"mesma chave, {len(resultado['divergem'])} divergem e "
                      f"{len(resultado['fora'])} não casaram. Veja abaixo o "
                      f"motivo de cada um.", "warning")
            with db.connect() as con:
                quadro = PCEN.quantos_sem_chave(con)

        with db.connect() as con:
            do_arquivo = len(PCEN.titulos_do_arquivo(con))
            editais_hoje = len(AV.editais_do_dia(con, hoje()))
        return render_template("protesto_cenprot.html", resultado=resultado,
                               quadro=quadro, do_arquivo=do_arquivo,
                               editais_hoje=editais_hoje, hoje=hoje(),
                               versao_medida=PCEN.VERSAO_MEDIDA)

    @app.route("/protesto/cenprot/emolumentos", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_cenprot_emolumentos():
        """Gera o arquivo de emolumentos do CENPROT, para subir na Central.

        É O QUE O DEVEDOR PAGA PARA LIMPAR O NOME, publicado pela Central para
        ele saber antes de vir ao balcão: **retirada** (paga antes de o
        protesto ser lavrado) e **cancelamento** (paga depois).

        **A conta foi medida contra o arquivo de um ano inteiro** — 375
        títulos, dez/24 a dez/25 —, e bate no centavo em 166 dos 173 que deu
        para casar com o acervo. Sai em CRLF e sem BOM, como o real.

        SÓ LÊ: gerar não muda título nenhum, e por isso não abre transação de
        escrita. O que sai fica registrado na auditoria — o arquivo vai para a
        Central, e numa correição a pergunta é o que foi publicado e quando.
        """
        config = db.get_settings()
        try:
            casa = PCEN.identidade_da_casa(config)
            with db.connect() as con:
                arquivo = PCEN.gerar_emolumentos(
                    con, uf=str(config.get("ri_uf") or "MA").strip(),
                    data=hoje(), **casa)
        except PCEN.CenprotError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_cenprot"))
        if not arquivo["linhas"]:
            # ARQUIVO VAZIO NÃO SE MANDA. Um cabeçalho sozinho subiria na
            # Central dizendo «nenhum protesto tem preço», que é diferente de
            # «não há protesto vivo» — e é o balcão que paga a diferença.
            flash("Nenhum título entra no arquivo: ele leva os protestos "
                  "ainda vivos QUE JÁ TENHAM a chave do CENPROT, e a chave "
                  "vem do XML — traga-o na parte de cima desta tela.",
                  "warning")
            return redirect(url_for("protesto_cenprot"))
        audit("PROTESTO_CENPROT_EMOLUMENTOS", "pt_titulos", None,
              {"arquivo": arquivo["nome"], "linhas": arquivo["linhas"],
               "fora": len(arquivo["fora"]), "vigencia": arquivo["vigencia"]})
        return Response(
            arquivo["conteudo"].encode("utf-8"),
            mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition":
                     f'attachment; filename="{arquivo["nome"]}"'})

    @app.route("/protesto/cenprot/edital", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_cenprot_edital():
        """Gera o XML do edital eletrônico do dia, para subir na CENPROT.

        **O ATO VEM ANTES DO ARQUIVO.** A fonte são os editais que já foram
        **publicados** naquele dia — quem publica é a tela de avisos, que
        numera, congela o teor e o amarra ao aviso. Aqui só se escreve o que
        já foi lavrado: gerar o arquivo não publica edital nenhum.

        Art. 15, § 1º, da Lei 9.492/1997, e Resolução nº 8 do IEPTB-BR, na
        citação do Ofício Circular IEPTB-MA/CRA-MA nº 015/2025.

        SÓ LÊ. O dia vem do formulário — a Central aceita o arquivo de um dia
        anterior, e quem esqueceu ontem precisa poder mandar hoje.
        """
        dia = (_campo("dia") or hoje())[:10]
        # QUEM PEDIU DE «AVISOS E EDITAIS» VOLTA PARA LÁ (#142, 26/10/2026) —
        # é onde o edital se publica, e o botão passou a morar lá também.
        # Lista fechada: o destino não vem livre do formulário.
        volta = {"avisos": "protesto_avisos"}.get(_campo("voltar"),
                                                  "protesto_cenprot")
        config = db.get_settings()
        try:
            casa = PCEN.identidade_da_casa(config)
            with db.connect() as con:
                arquivo = PCEN.gerar_edital_eletronico(
                    con, dia=dia, comarca=casa["comarca"])
        except PCEN.CenprotError as erro:
            flash(str(erro), "danger")
            return redirect(url_for(volta))
        if not arquivo["editais"]:
            # ARQUIVO SEM UM EDITAL NÃO SE MANDA: ele diria à Central que a
            # casa publicou nada naquele dia, que é diferente de não ter
            # gerado o arquivo.
            flash(f"Nenhum edital foi publicado em {dia}. O arquivo sai do que "
                  f"já foi publicado — publique em Avisos e editais primeiro.",
                  "warning")
            return redirect(url_for(volta))
        audit("PROTESTO_CENPROT_EDITAL", "pt_editais", None,
              {"arquivo": arquivo["nome"], "dia": dia,
               "editais": arquivo["editais"], "fora": len(arquivo["fora"])})
        return Response(
            arquivo["conteudo"].encode("utf-8"),
            mimetype="application/xml; charset=utf-8",
            headers={"Content-Disposition":
                     f'attachment; filename="{arquivo["nome"]}"'})

    @app.route("/protesto/desistencias")
    @login_required
    def protesto_desistencias():
        """Os arquivos de desistência recebidos. Só LÊ.

        O ROTEIRO DO OFICIAL CONFERE DESISTÊNCIA NOS TRÊS TURNOS do dia — é a
        única coisa que aparece nos três. O motivo está na consequência:
        título de que o apresentante desistiu e a casa protestou é protesto que
        se cancela depois, com carta.
        """
        with db.connect() as con:
            recebidas = DS.listar(con)
        return render_template("protesto_desistencias.html",
                               recebidas=recebidas, hoje=hoje())

    @app.route("/protesto/desistencias/conferir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_desistencia_conferir():
        """Lê o arquivo e procura cada título nesta casa. NÃO GRAVA NADA."""
        enviado = request.files.get("arquivo")
        if not enviado or not enviado.filename:
            flash("Escolha o arquivo de desistência que baixou da CRA.",
                  "warning")
            return redirect(url_for("protesto_desistencias"))
        bruto = enviado.read()
        try:
            with db.connect() as con:
                visto = DS.conferir(con, bruto)
        except DS.DesistenciaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_desistencias"))
        return render_template("protesto_desistencia_conferir.html",
                               visto=visto, nome_arquivo=enviado.filename,
                               conteudo=DS.normalizar(bruto), hoje=hoje())

    @app.route("/protesto/desistencias/aplicar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_desistencia_aplicar():
        """Lança a desistência dos títulos ESCOLHIDOS. ESCREVE.

        CADA TÍTULO É UMA ESCOLHA, e o que não foi marcado não entra. O layout
        deste arquivo foi medido em quatro exemplares — ler errado continua
        sendo possível, e desistência lida errado é protesto lavrado contra
        quem o credor desistiu de protestar.
        """
        conteudo = request.form.get("conteudo") or ""
        if not conteudo.strip():
            flash("O arquivo não veio junto. Escolha-o de novo.", "warning")
            return redirect(url_for("protesto_desistencias"))
        escolhidos = [x for x in request.form.getlist("protocolo") if x.strip()]
        try:
            with db.transaction() as con:
                r = DS.aplicar(con, conteudo, protocolos=escolhidos,
                               agora=agora(),
                               nome_arquivo=_campo("nome_arquivo") or None,
                               usuario=usuario_nome())
        except (DS.DesistenciaError, PT.ProtestoError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_desistencias"))
        # `audit` abre transação própria: FORA do `with`.
        audit("PROTESTO_DESISTENCIA", "pt_desistencias", r["desistencia_id"],
              {"apresentante": r["apresentante_codigo"],
               "aplicados": len(r["aplicados"]),
               "recusados": len(r["recusados"])})
        recusa = ("" if not r["recusados"] else
                  f" {len(r['recusados'])} não entrou/entraram — o motivo está "
                  f"na lista.")
        flash(f"Desistência aplicada em {len(r['aplicados'])} título(s)."
              f"{recusa}", "success" if r["aplicados"] else "warning")
        return redirect(url_for("protesto_desistencia",
                                desistencia_id=r["desistencia_id"]))

    @app.route("/protesto/desistencias/<int:desistencia_id>")
    @login_required
    def protesto_desistencia(desistencia_id: int):
        """O arquivo recebido e os títulos que ele desistiu."""
        with db.connect() as con:
            linha = DS.desistencia(con, desistencia_id)
            if not linha:
                abort(404)
            atos = DS.atos_da_desistencia(con, desistencia_id)
        achados = []
        if linha["achados_json"]:
            try:
                achados = json.loads(linha["achados_json"])
            except ValueError:
                achados = []
        for a in atos:
            a["detalhe"] = json.loads(a.get("detalhe_json") or "{}")
        return render_template("protesto_desistencia.html",
                               desistencia=dict(linha), atos=atos,
                               achados=achados)

    @app.route("/protesto/desistencias/<int:desistencia_id>/arquivo")
    @login_required
    def protesto_desistencia_arquivo(desistencia_id: int):
        """O arquivo como CHEGOU. Sai em ISO-8859-1, que é como ele veio."""
        with db.connect() as con:
            linha = DS.desistencia(con, desistencia_id)
        if not linha:
            abort(404)
        nome = linha["nome_arquivo"] or f"desistencia-{desistencia_id}.txt"
        return Response(
            linha["conteudo"].encode("latin-1", errors="replace"),
            mimetype="text/plain; charset=ISO-8859-1",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    # ------------------------------------------------ o retorno à CRA

    @app.route("/protesto/retornos")
    @login_required
    def protesto_retornos():
        """O que a CRA ainda não sabe, e o que já foi mandado.

        93% DOS TÍTULOS ENTRAM PELA CRA. Sem o retorno eles entram e nunca
        voltam: a Central fica sem saber o que aconteceu com o título que
        mandou.
        """
        with db.connect() as con:
            grupos = PRE.apresentantes_pendentes(con)
            atos = PRE.pendentes(con)
            gerados = [dict(r) for r in PRE.listar(con, limite=60)]
            # Só AVISO: o que a CRA ouviu e o livro desfez (28/10/2026).
            desfeitos = [dict(r) for r in PRE.informados_e_desfeitos(con)]
        return render_template("protesto_retornos.html", grupos=grupos,
                               atos=atos, gerados=gerados, hoje=hoje(),
                               desfeitos=desfeitos)

    @app.route("/protesto/retornos/gerar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_retorno_gerar():
        """Gera o RETORNO e o ANDAMENTO, em par. ESCREVE.

        OS DOIS SAEM JUNTOS, e isso é regra desta casa: o roteiro do protesto
        que o oficial trouxe da serventia em que trabalhou diz, em maiúscula,
        «SEMPRE QUE GERAR RETORNO (FINAL), GERAR ANDAMENTO».
        """
        codigo = _campo("apresentante_codigo")
        try:
            with db.transaction() as con:
                r = PRE.gerar(con, apresentante_codigo=codigo,
                              dia=_campo("dia") or hoje(), agora=agora(),
                              marca=_campo("marca") or None,
                              numero_da_remessa=_inteiro(
                                  _campo("numero_da_remessa"), 1,
                                  maximo=MAIOR_INTEGER),
                              usuario=usuario_nome())
        except (PRE.RetornoError, PA.ArquivoError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_retornos"))
        # `audit` abre transação própria: FORA do `with`, como no resto da casa.
        audit("PROTESTO_RETORNO", "pt_retornos", r["retorno_id"],
              {"apresentante": codigo, "titulos": len(r["atos"]),
               "andamento_id": r["andamento_id"], "hash": r["hash"]})
        flash(f"Retorno e andamento gerados para {codigo}: "
              f"{len(r['atos'])} título(s). Envie o retorno pelo botão "
              f"«Enviar à CRA» em «Arquivos gerados» (até 11h30); o andamento "
              f"em par com retorno ainda sobe pelo portal da CRA — o código "
              f"dele na Central não foi medido.", "success")
        adiados = r.get("adiados") or []
        if adiados:
            flash(f"{len(adiados)} ato(s) ficaram para o próximo retorno: o "
                  f"mesmo protocolo já vai neste arquivo com outra ocorrência, "
                  f"e a CRA recusa o lote com protocolo repetido. Gere de novo "
                  f"depois de enviar este.", "warning")
        return redirect(url_for("protesto_retornos"))

    @app.route("/protesto/retornos/<int:retorno_id>/enviar", methods=["POST"])
    # 21/10/2026: aberto às escreventes por ordem do oficial (era ("ADMIN", "MANAGER")).
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_retorno_enviar(retorno_id: int):
        """Envia o arquivo gerado à CRA, em produção. ESCREVE (o resultado).

        A rede corre FORA da transação (`protesto_cra_envio.enviar_arquivo`).
        Enviar não é do balcão — a separação das Centrais: consultar abre,
        mandar é do oficial e do gerente.
        """
        import protesto_cra_envio as PCE_ENVIO
        forcar = _campo("forcar") == "1"
        try:
            r = PCE_ENVIO.enviar_arquivo(db.transaction, retorno_id,
                                         usuario=usuario_nome(), forcar=forcar)
        except (PCE_ENVIO.CraEnvioError, CENTCRED.CredencialError) as erro:
            audit("PROTESTO_ENVIO_CRA_FALHOU", "pt_retornos", retorno_id,
                  {"erro": str(erro)[:300]})
            flash(f"Não foi à CRA: {erro}", "danger")
            return redirect(url_for("protesto_retornos"))
        audit("PROTESTO_ENVIO_CRA", "pt_retornos", retorno_id,
              {"operacao": r.get("operacao"), "codigo": r.get("codigo"),
               "nome": r.get("nome_arquivo")})
        flash(f"«{r.get('nome_arquivo')}» entrou na CRA "
              f"(código {r.get('codigo') or 'sem código'}).", "success")
        return redirect(url_for("protesto_retornos"))

    @app.route("/protesto/retornos/<int:retorno_id>/arquivo")
    @login_required
    def protesto_retorno_arquivo(retorno_id: int):
        """O arquivo como saiu, para subir na CRA.

        Sai em ISO-8859-1, que é o que a Central lê — o arquivo de 600
        posições nunca foi UTF-8, e mandar acento em dois bytes empurraria
        todos os campos da linha para a direita.
        """
        with db.connect() as con:
            linha = PRE.retorno(con, retorno_id)
        if not linha:
            abort(404)
        audit("PROTESTO_RETORNO_BAIXADO", "pt_retornos", retorno_id,
              {"nome": linha["nome_arquivo"]})
        return Response(
            linha["conteudo"].encode("latin-1", errors="replace"),
            mimetype="text/plain; charset=ISO-8859-1",
            headers={"Content-Disposition":
                     f'attachment; filename="{linha["nome_arquivo"]}"'})

    # ------------------------- a certidão de inteiro teor das atribuições

    @app.route("/atribuicoes/certidoes/<atribuicao>/<int:registro_id>",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def atribuicoes_certidao_emitir(atribuicao: str, registro_id: int):
        """Emite a certidão de inteiro teor do registro. ESCREVE.

        SAI DA FICHA DO REGISTRO, e não de uma tela à parte: é ali que o
        escrevente está quando o cliente pede a certidão, e é ali que ele
        acabou de ver o que o livro diz.

        O TEOR NÃO SE DIGITA. A certidão reproduz o que está no livro; papel
        que a serventia assina não se redige no balcão. Quem recusa registro
        sem teor é o domínio, dizendo que a cópia se tira do livro físico.
        """
        try:
            volta = url_for(CE.painel(atribuicao)["rota_ficha"],
                            registro_id=registro_id)
        except CE.CertidaoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_titulos"))
        #  A CERTIDAO POR REPRODUCAO DA DIGITALIZACAO — 21/09/2026, «aplique
        #  o mesmo codigo do livro 2 adaptado».
        #
        #  **A RECUSA E AQUI, ANTES DE QUALQUER ESCRITA**: quem pedir a
        #  reproducao numa ficha sem varredura leva o motivo com o cliente
        #  ainda na frente, e nao uma certidao numerada que nao se imprime.
        #
        #  **E O PADRAO SEGUE A FICHA, E NAO UMA CONSTANTE** — e a licao que o
        #  Livro 2 pagou em 16/09/2026: com `DIGITALIZACAO` fixo, toda
        #  certidao de casa sem arquivo era recusada. Medido em 21/09: **0 dos
        #  16 registros** deste livro tem varredura, logo o padrao aqui e o
        #  TEXTO em todos eles — e passa a ser a reproducao ficha a ficha, a
        #  medida que o balcao varre.
        fonte_corpo = (request.form.get("fonte_corpo") or "").strip().upper()
        digitalizacao = None
        if fonte_corpo == "DIGITALIZACAO":
            try:
                with db.connect() as _c:
                    atual = RADIGI.atual(_c, registro_id)
                caminho = Path(str((atual or {}).get("digi_path") or ""))
                if not (atual and caminho.is_file()):
                    raise RADIGI.DigitalizacaoError(
                        "Não há digitalização da ficha deste registro. Envie "
                        "a varredura na ficha ou emita a certidão pelo teor.")
                digitalizacao = {
                    "path": str(caminho),
                    "sha256": str(atual.get("digi_sha256") or ""),
                    # QUANTAS FOLHAS A VIA TERA — contado do arquivo, e nao
                    # suposto: e este numero que o teor congelado afirma.
                    "paginas": len(RADIGI.paginas_png(caminho)),
                }
            except (RADIGI.DigitalizacaoError, ValueError) as erro:
                flash(str(erro), "danger")
                return redirect(volta)

        # A BUSCA — resposta do oficial, 15/10/2026: RTD/PJ e Livro 3 também
        # levam o selo de busca junto. A escolha se confere antes de numerar.
        chave_do_painel = CE.painel(atribuicao)["chave"]
        try:
            busca = _busca_do_form(chave_do_painel)
        except BU.BuscaError as _erro_busca:
            flash(str(_erro_busca), "danger")
            return redirect(volta)
        try:
            ato_ids_raw = request.form.getlist("ato_id")
            # o marcado que passa pelo `isdigit()` e não é id do banco é -1, o
            # id de ninguém — e não a lista vazia, que quer dizer «todos os
            # atos»: a certidão sairia de atos que ninguém pediu (LD13)
            ato_ids = [numero_digitado(x) or -1
                       for x in ato_ids_raw if str(x).isdigit()] or None
            with db.transaction() as con:
                r = CE.emitir(con, atribuicao, registro_id, hoje=hoje(),
                              agora=agora(),
                              requerente=_campo("requerente") or None,
                              # AS BALIZAS QUE O LIVRO 2 JA TINHA — 21/09/2026.
                              # O documento de quem pede (nome sozinho tem
                              # homonimo) e quem assina por extenso: o login
                              # «mario» nao responde «quem assinou isto?».
                              requerente_documento=(
                                  _campo("requerente_documento") or None),
                              finalidade=_campo("finalidade") or None,
                              usuario=usuario_nome(),
                              usuario_nome=usuario_nome(),
                              usuario_funcao=usuario_funcao(),
                              ato_ids=ato_ids,
                              fonte_corpo=fonte_corpo or "TEXTO",
                              digitalizacao=digitalizacao,
                              # a cidade e a UF do fecho de cada ato (LD05)
                              sv=sv(),
                              # no RCPJ, o breve relato (LD05; CN-MA 420, II)
                              forma=_campo("forma") or "INTEIRO_TEOR")
                aviso_selo = _selar_se_pedido(con, "at_certidoes",
                                              r["certidao_id"], atribuicao)
                aviso_cobranca = _cobrar_se_pedido(
                    con, "at_certidoes", r["certidao_id"], "CERTIDAO",
                    busca=busca)
        except (CE.CertidaoError, AS.AtoError) as erro:
            flash(str(erro), "danger")
            return redirect(volta)
        # **O SELO AUTOMÁTICO SAI AGORA, FORA DA TRANSAÇÃO** — achado do
        # oficial em 11/09/2026: emitir certidão nunca pedia selo sozinho,
        # só o digitado à mão. Só o RCPJ/RTD tem o caminho genérico
        # (`atos-em-geral`) medido para isso; o Livro 3 continua como
        # estava — sem regressão, porque nunca selou automático também.
        # `aviso_selo` (não `aviso_cobranca`) é o que diz «já saiu selo» —
        # misturar os dois faria uma cobrança sem selo nenhum passar como
        # se já tivesse selado.
        #  A COPIA CONGELADA — a certidao reproduz o arquivo COMO ELE ESTAVA.
        #
        #  Ela so pode ser feita agora, porque a pasta leva o id da certidao
        #  dentro. **Falhar aqui nao cancela a certidao**: ela existe, com
        #  numero e hash, e continua apontando para a varredura da ficha —
        #  derrubar um ato que ja existe por causa de uma copia seria pior. O
        #  balcao fica sabendo, porque quem varrer a ficha de novo mudaria o
        #  que esta certidao reproduz.
        if r.get("fonte") == "DIGITALIZACAO":
            try:
                copia = RADIGI.congelar_para_certidao(
                    db, certidao_id=r["certidao_id"],
                    origem=Path(digitalizacao["path"]))
                with db.transaction() as con:
                    CE.marcar_a_copia_congelada(
                        con, r["certidao_id"], path=copia["path"],
                        sha256=copia["sha256"])
            except (RADIGI.DigitalizacaoError, OSError) as erro:
                audit("ATRIB_CERTIDAO_SEM_COPIA_CONGELADA", "at_certidoes",
                      r["certidao_id"], {"motivo": str(erro)})
                flash(f"A certidão saiu, e a cópia congelada da digitalização "
                      f"NÃO foi guardada: {erro} Enquanto isso, ela reproduz o "
                      f"arquivo que está na ficha.", "warning")

        if CE.painel(atribuicao)["chave"] == "RCPJ_RTD":
            aviso_selo = _selar_a_certidao_rtdpj(
                r["certidao_id"], registro_id, atribuicao, aviso_selo,
                busca=busca)
        elif CE.painel(atribuicao)["chave"] == "LIVRO3":
            #  AS FOLHAS: na reprodução elas são contadas do arquivo; na
            #  certidão por texto vale uma, que é o que a casa manda quando
            #  não tem como contar.
            #  NA REPRODUÇÃO AS FOLHAS SÃO CONTADAS DO ARQUIVO; na certidão
            #  por texto elas são o que o balcão informou, e o padrão é uma.
            #  Deduzir o número de folhas do tamanho do teor seria inventar o
            #  que só se sabe depois de imprimir.
            #  E NUMERO QUE NAO E NUMERO NAO DERRUBA A CERTIDAO JA GRAVADA:
            #  vale uma folha, que e o padrao da casa. A caixa da tela e
            #  `type="number"`, e o que vem de fora nao se acredita — um
            #  `int()` solto aqui daria HTTP 500 depois de a certidao existir.
            # FOLHAS PELO SISTEMA - 22/09/2026: conta do arquivo na reproducao;
            # no texto, conta/estima o papel. Campo da tela so sobe o numero.
            try:
                _folhas_tela = int((_campo("folhas") or "").strip() or 0) or None
            except ValueError:
                _folhas_tela = None
            folhas_da_certidao = CFOLHAS.decidir_folhas_antes_de_emitir(
                fonte=("DIGITALIZACAO" if digitalizacao else "TEXTO"),
                caminho_digi=(digitalizacao or {}).get("path"),
                paginas_digi=(digitalizacao or {}).get("paginas"),
                corpo_html=(r.get("teor") if isinstance(r, dict) else None),
                folhas_informadas=_folhas_tela,
                get_setting=db.get_setting if hasattr(db, "get_setting") else None,
            )
            aviso_selo = _selar_a_certidao_do_livro3(
                r["certidao_id"], registro_id, folhas_da_certidao, aviso_selo,
                busca=busca)
        aviso = aviso_selo + aviso_cobranca
        motivo_selo = _motivo_da_falha_do_selo(aviso_selo)
        if motivo_selo:
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE at_certidoes
                          SET cancelada=1, motivo_cancelamento=%s,
                              cancelada_em=%s, cancelada_por=%s
                        WHERE id=%s""",
                    (f"Selo não emitido: {motivo_selo}", agora(),
                     usuario_nome(), r["certidao_id"]))
                _soltar_itens_da_certidao_cancelada(con, "at_certidoes",
                                                    r["certidao_id"])
            audit("ATRIB_CERTIDAO_NAO_EMITIDA_SELO_FALHOU",
                  "at_certidoes", r["certidao_id"],
                  {"atribuicao": r["atribuicao"], "numero": r["numero"],
                   "ano": r["ano"], "hash": r["hash"],
                   "motivo": motivo_selo})
            flash("Certidão NÃO emitida: o selo não saiu. "
                  f"Motivo: {motivo_selo}. Corrija o problema do "
                  "selo e tente de novo.",
                  "danger")
            return redirect(volta)
        # `audit` abre transação própria: FORA do `with`, como no resto da casa.
        audit("ATRIB_CERTIDAO", "at_certidoes", r["certidao_id"],
              {"atribuicao": r["atribuicao"], "numero": r["numero"],
               "ano": r["ano"], "hash": r["hash"],
               **({"busca": busca} if busca else {})})
        flash(f"Certidão n. {r['numero']}/{r['ano']} de {r['nome']} "
              f"emitida.{aviso}", "success")
        return redirect(url_for("atribuicoes_certidao",
                                certidao_id=r["certidao_id"]))

    # **OS ITENS DA CERTIDÃO NEGATIVA** (LD05): a certidão (15.10) e a busca
    # (15.11), os mesmos que o caixa lança para a certidão do registro.
    ITENS_DA_CERTIDAO_RTDPJ = ("15.10", "15.11")

    def _selar_a_certidao_negativa(certidao_id: int, sigla: str,
                                   pesquisado: dict) -> str:
        """O selo da certidão negativa, pelos itens do protocolo. FALA COM A REDE.

        **O ITEM SE LIGA À CERTIDÃO ANTES DO SELO, E VOLTA SE O SELO NÃO
        SAIR** (LD05, 21/10/2026). O escrevente escolhe o protocolo no
        formulário: a unidade do item é gasta para ESTA certidão
        (`consumir_item`, sob FOR UPDATE), e é por ela que a trava do selo pago
        acha o pagamento — sem depender de o protocolo estar em atendimento. O
        item que não pagar o selo volta ao protocolo (`devolver_item`) e o
        rastro sai: nada de item gasto por certidão que não existe.

        Quem vai nas partes do selo é a pessoa pesquisada — não há título, e
        é o que o Protesto faz com a certidão dele.
        """
        import caixa_protocolo as CXP
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return SR.recado_pendente_selo()
        versao = AS.versao_da_tabela_de_custas(
            AS.CAMINHO_RTDPJ_GERAL, db.get_setting("selo_tabela_custas_em", ""))
        if not versao:
            return AS.recado_de_falta(
                " A certidão saiu SEM SELO: falta dizer de que data é a "
                "tabela de custas em vigor, em Administrativo → Configurações.")
        # O NÚMERO QUE NÃO É NÚMERO (LD13): o protocolo é nenhum; o item
        # marcado que passa pelo `isdigit()` e não é id do banco é -1, o id de
        # ninguém — sem ele a lista ficaria vazia, e vazia aqui quer dizer
        # «os itens de certidão do protocolo», que ninguém marcou.
        protocolo = numero_digitado(_campo("protocolo_id"))
        marcados = {numero_digitado(x) or -1
                    for x in request.form.getlist("protocolo_item_id")
                    if str(x).strip().isdigit()}
        ligados: list[tuple[int, str, int]] = []
        with db.transaction() as con:
            bd = banco(con)
            for it in CXP.itens_disponiveis(bd, protocolo):
                codigo = str(it["codigo_ato"] or "").strip()
                if marcados and int(it["id"]) not in marcados:
                    continue
                if not marcados and not any(
                        codigo == c or codigo.startswith(c + ".")
                        for c in ITENS_DA_CERTIDAO_RTDPJ):
                    continue
                gastas = CXP.consumir_item(
                    bd, int(it["id"]), ato_id=int(certidao_id),
                    tabela="at_certidoes", agora=agora(),
                    quantas=int(it["saldo"]), origem=CXP.ORIGEM_CONSUMO,
                    quem=usuario_nome())
                if gastas:
                    ligados.append((int(it["id"]), codigo, gastas))
        if not ligados:
            return AS.recado_de_falta(
                " A certidão saiu SEM SELO: o protocolo escolhido não tem item "
                "de certidão (15.10) com saldo. Lance e quite o item no caixa e "
                "peça de novo.")
        saiu, faltou, recusou = [], [], False
        ocorrencias: dict[str, int] = {}
        for item_id, codigo, quantidade in ligados:
            ocorrencias[codigo] = ocorrencias.get(codigo, 0) + 1
            try:
                envelope = AS.envelope_do_rtdpj(
                    caminho=AS.CAMINHO_RTDPJ_GERAL, codigo_tj=codigo,
                    escrevente=usuario_nome(), versao_tabela=versao,
                    partes=[pesquisado], quantidade=quantidade)
                r = AS.selar_o_ato_lavrado(
                    db, Path(app.config["DATA_DIR"]), tabela="at_certidoes",
                    ato_id=certidao_id, tipo="CERTIDAO", atribuicao=sigla,
                    agora=agora(), cns=sv().get("ri_cns"), usuario=usuario_nome(),
                    dados=envelope, caminho=AS.CAMINHO_RTDPJ_GERAL,
                    referencia=(f"at_certidoes:{int(certidao_id)}:{codigo}:"
                                f"{ocorrencias[codigo]}"))
            except AS.AtoError as erro:
                r = {"selado": False, "motivo": str(erro)}
            if r["selado"]:
                saiu.append(r["numero"])
                continue
            recusou = True
            faltou.append(r["motivo"])
            with db.transaction() as con:
                CXP.devolver_item(con, item_id, quantas=quantidade)
                banco(con).escrever(
                    """DELETE FROM cx_item_do_ato
                        WHERE tabela = 'at_certidoes' AND ato_id = %s
                          AND item_id = %s AND origem = %s""",
                    (int(certidao_id), item_id, CXP.ORIGEM_CONSUMO))
        if not saiu:
            marcar = AS.recado_de_recusa if recusou else AS.recado_de_falta
            return marcar(f" A certidão saiu SEM SELO: {faltou[0] if faltou else ''}")
        recado = f" {len(saiu)} selo(s): {', '.join(saiu)}."
        if faltou:
            recado += f" ({len(faltou)} item(ns) sem selo: {faltou[0]})"
        return recado

    @app.route("/atribuicoes/certidoes/RCPJ_RTD/negativa", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def atribuicoes_certidao_negativa():
        """Emite a certidão negativa do RTD ou do RCPJ. ESCREVE e FALA COM A REDE.

        LRP arts. 16, 17 e 19; CN-MA art. 963, § 3º (certidão pelo nome das
        partes); serviços 314 e 315 da casa. Era o defeito que o LT05 achou: a
        casa só emitia certidão de um registro que existe (LD05, 21/10/2026).

        **NUNCA SEM SELO** (CN-MA art. 130, § 2º): a certidão é numerada na
        transação dela; se o selo não sai — item não pago, aparelho fora —, ela
        é cancelada com o motivo, o item volta ao protocolo e o balcão ouve
        por quê. Quem confere é o selo gravado na certidão, e não a frase do
        recado.
        """
        import caixa_protocolo as CXP
        volta = redirect(url_for("atribuicoes_certidoes", atribuicao="RCPJ_RTD"))
        protocolo = _campo("protocolo_id")
        if not protocolo.isdigit():
            flash("Escolha o protocolo do balcão em que a certidão foi paga — "
                  "é por ele que o selo sai.", "danger")
            return volta
        sigla = _campo("atribuicao_da_busca").upper()
        if not sigla:
            with db.connect() as con:
                # o «²» e os 5.000 dígitos passam pelo `isdigit()`: -1, o
                # protocolo de ninguém, como o de 30 dígitos já era (LD13)
                p = banco(con).um(
                    "SELECT atribuicao FROM cx_protocolos WHERE id=%s",
                    (numero_digitado(protocolo) or -1,))
            sigla = str((p or {}).get("atribuicao") or "").strip().upper()
        nome = _campo("nome_pesquisado")
        documento = _campo("documento_pesquisado")
        try:
            with db.transaction() as con:
                r = CE.emitir_negativa(
                    con, atribuicao=sigla, nome=nome, documento=documento,
                    hoje=hoje(), agora=agora(),
                    requerente=_campo("requerente") or None,
                    requerente_documento=_campo("requerente_documento") or None,
                    finalidade=_campo("finalidade") or None,
                    usuario=usuario_nome(), usuario_nome=usuario_nome(),
                    usuario_funcao=usuario_funcao())
        except (CE.CertidaoError, CXP.ProtocoloError) as erro:
            flash(str(erro), "danger")
            return volta
        aviso = _selar_a_certidao_negativa(
            r["certidao_id"], r["sigla"], {"nome": nome, "documento": documento})
        with db.connect() as con:
            selo = banco(con).valor(
                "SELECT selo FROM at_certidoes WHERE id=%s", (r["certidao_id"],))
        if not str(selo or "").strip():
            motivo = (_motivo_da_falha_do_selo(aviso) or str(aviso or "").strip()
                      or "o selo não saiu")
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE at_certidoes
                          SET cancelada=1, motivo_cancelamento=%s,
                              cancelada_em=%s, cancelada_por=%s
                        WHERE id=%s""",
                    (f"Selo não emitido: {motivo}", agora(), usuario_nome(),
                     r["certidao_id"]))
            audit("ATRIB_CERTIDAO_NAO_EMITIDA_SELO_FALHOU", "at_certidoes",
                  r["certidao_id"], {"negativa": True, "numero": r["numero"],
                                     "ano": r["ano"], "motivo": motivo})
            flash("Certidão negativa NÃO emitida: o selo não saiu. Motivo: "
                  f"{motivo}. Corrija o problema do selo e tente de novo.",
                  "danger")
            return volta
        audit("ATRIB_CERTIDAO_NEGATIVA", "at_certidoes", r["certidao_id"],
              {"numero": r["numero"], "ano": r["ano"], "hash": r["hash"],
               "atribuicao": r["sigla"]})
        flash(f"Certidão negativa n. {r['numero']}/{r['ano']} do {r['sigla']} "
              f"emitida.{aviso}", "success")
        return redirect(url_for("atribuicoes_certidao",
                                certidao_id=r["certidao_id"]))

    @app.route("/atribuicoes/certidoes")
    @login_required
    def atribuicoes_certidoes():
        """As certidões emitidas de RCPJ/RTD e do Livro 3."""
        atribuicao = (request.args.get("atribuicao") or "").strip() or None
        termo = (request.args.get("q") or "").strip()
        try:
            with db.connect() as con:
                linhas = [dict(r) for r in CE.listar(
                    con, atribuicao=atribuicao, termo=termo, limite=100)]
                protocolos = _protocolos_abertos(con)
        except CE.CertidaoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("atribuicoes_certidoes"))
        return render_template("atrib_certidoes.html", linhas=linhas,
                               paineis=CE.PAINEIS, atribuicao=atribuicao,
                               termo=termo, protocolos=protocolos)

    @app.route("/atribuicoes/certidoes/<int:certidao_id>")
    @login_required
    def atribuicoes_certidao(certidao_id: int):
        """A certidão como saiu — para conferir, imprimir e reimprimir."""
        with db.connect() as con:
            linha = CE.certidao(con, certidao_id)
            if not linha:
                flash("Certidão não encontrada.", "danger")
                return redirect(url_for("atribuicoes_certidoes"))
            certidao = dict(linha)
        p = CE.painel(certidao["atribuicao"])
        return render_template("atrib_certidao.html", certidao=certidao,
                               painel=p)

    @app.route("/atribuicoes/certidoes/<int:certidao_id>/imprimir")
    @login_required
    def atribuicoes_certidao_imprimir(certidao_id: int):
        """PDF da certidão emitida. RCPJ/RTD visual (capa+faixa) quando há
        imagens dos atos; senão cai no .odt convertido (fluxo antigo)."""
        with db.connect() as con:
            linha = CE.certidao(con, certidao_id)
            if not linha:
                abort(404)
            cert = dict(linha)
            if (cert["atribuicao"] != "RCPJ_RTD" or CE.eh_negativa(cert)
                    or str(cert.get("fonte_corpo") or "").upper() == "BREVE_RELATO"):
                # Livro 3 e demais: mesmo caminho do ODT→PDF. E a negativa e o
                # breve relato (LD05), que não reproduzem documento nenhum.
                return atribuicoes_certidao_odt(certidao_id)
            registro = banco(con).um(
                "SELECT * FROM rg_registros WHERE id=%s",
                (int(cert["registro_id"]),))
            if not registro:
                flash("Registro da certidão não encontrado.", "danger")
                return redirect(url_for("atribuicoes_certidao",
                                       certidao_id=certidao_id))
            atos_reg = banco(con).ler(
                "SELECT * FROM rg_atos WHERE registro_id=%s ORDER BY id",
                (int(cert["registro_id"]),))
            # AS FRASES DO OBJETO CERTIFICADO SÃO DA MOLDURA DOS PDFs desde o
            # LF06F (19/10/2026) — «a(s) averbação(ões) nº …», «Averbações nº
            # …» eram literais aqui. A regra de qual frase entra fica abaixo.
            try:
                moldura = RGTEOR.moldura(con, erro=RGCERT.CertidaoPdfError)
            except RGCERT.CertidaoPdfError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("atribuicoes_certidao",
                                        certidao_id=certidao_id))
        import json as _json
        ato_ids = None
        raw_ids = cert.get("atos_ids")
        if raw_ids:
            try:
                parsed = _json.loads(raw_ids)
                if isinstance(parsed, list) and parsed:
                    ato_ids = [int(x) for x in parsed]
            except (TypeError, ValueError):
                ato_ids = None
        atos_escolhidos = RGCERT.filtrar_atos_por_ids(atos_reg, ato_ids)
        anexos = [dict(x) for x in db.get_attachments(
            "RG_REGISTRO", int(cert["registro_id"]))]
        anexos_por_ato = {
            int(a["id"]): [dict(x) for x in db.get_attachments(
                "RG_ATO", int(a["id"]))]
            for a in atos_escolhidos
        }
        caminhos = RGCERT.imagens_dos_atos(
            atos_escolhidos,
            anexos_por_ato=anexos_por_ato,
            anexos_registro=anexos,
            anexo_ids_override=None,
        )
        if not caminhos:
            # Sem digitalização: PDF textual via ODT (como antes).
            return atribuicoes_certidao_odt(certidao_id)

        s = sv()
        ato_reg = next((a for a in atos_reg
                        if str(a.get("tipo") or "").upper() == "REGISTRO"), None)
        data_registro = ""
        if ato_reg and ato_reg.get("data_ato"):
            data_registro = str(ato_reg["data_ato"])[:10]
        # **O OBJETO CERTIFICADO, PARA O PDF VISUAL** — pedido do oficial em
        # 12/09/2026: «não está com os dados do serviço efetivo de certidão
        # de averbações e o cabeçalho que fica em cima de todas páginas
        # também precisa acompanhar isso». O texto congelado em
        # `at_certidoes.teor` (via `atrib_certidao.montar_teor`) já sabia
        # disso; este PDF visual (capa + faixa de cada folha) é um
        # renderizador SEPARADO, e nunca tinha essa informação — sempre
        # descrevia o registro original, mesmo quando a certidão era só de
        # averbação. `objeto_certificado` entra na frase de abertura da
        # capa E na faixa do topo de toda folha interna.
        objeto_certificado = ""
        # **A DATA DO CABEÇALHO DE TODA FOLHA** — achado do oficial em
        # 12/09/2026: «o cabeçalho de todas páginas ainda mostra o protocolo
        # do registro originário e data do originário». `contexto_certidao`
        # cai em `data_apresentacao or data_registro` quando ninguém manda
        # `data_apresentacao` — e esta rota nunca mandava, então a faixa
        # sempre mostrava a data do REGISTRO original, mesmo numa certidão
        # que é só das averbações. Aqui a data que importa é a da própria
        # averbação certificada.
        data_apresentacao_averbacao = ""
        # **A "NATUREZA" TAMBÉM FALAVA DO REGISTRO ORIGINÁRIO** — achado ao
        # conferir o PDF em 12/09/2026: a capa dizia «A presente certidão tem
        # por objeto a(s) averbação(ões)...» e, três linhas abaixo, sob o
        # rótulo "Natureza:", repetia a natureza do ATO DE REGISTRO (aqui,
        # "Ata de assembleia geral de constituição") — como se fosse isso que
        # a certidão certificasse. Quando a certidão é só de averbação, a
        # natureza que aparece na capa tem de ser a da(s) própria(s)
        # averbação(ões).
        natureza_certificada = registro["natureza"] or ""
        # **A CAIXA "Registro Nº.../data" DE TODA FOLHA** — mesmo achado,
        # relatado de novo em 12/09/2026: «segue o registro 148 na parte
        # esquerda superior do cabeçalho». `montar_folha_interna` desenha
        # essa caixinha à parte da faixa de texto, e ela sempre repetia
        # "Registro Nº {numero}" + a data do registro — sem o contexto da
        # frase ao lado, ela sozinha lia como se fosse a certidão do
        # registro. Quando a certidão é só de averbação, a caixa mostra o(s)
        # número(s) da(s) averbação(ões) e a data em que ela(s) foi(ram)
        # lavrada(s), não mais o registro original.
        identificacao_curta = ""
        # **O Nº DO PROTOCOLO DA(S) PRÓPRIA(S) AVERBAÇÃO(ÕES)** — pedido do
        # oficial em 12/09/2026: «colocar o número do protocolo das
        # averbações no texto de introdução». A frase de abertura já tem
        # `{protocolo}`, mas a rota nunca preenchia — ficava "protocolado
        # sob nº —". Cada averbação carrega o seu próprio `protocolo_id`
        # (`rg_atos.protocolo_id`); busca-se o número (`cx_protocolos.
        # numero`) de cada um e junta-se os distintos.
        protocolo_ids_av: list[int] = []
        if CE.eh_so_averbacoes("RCPJ_RTD", {"atos": atos_reg}, ato_ids):
            # O PROTOCOLO DE CADA AVERBAÇÃO É O DO ITEM QUE ELA GASTOU — LT05,
            # 20/10/2026. `rg_atos.protocolo_id` nenhuma tela grava; a ponte
            # que existe é `cx_protocolo_atos.usado_por_ato_id`, escrita quando
            # o ato consome o item (a mesma de `rg_titulo.titulo_do_ato`). Sem
            # ela a capa saía «protocolado sob nº —».
            with db.connect() as con_itens:
                protocolo_do_item = {
                    int(r["ato_id"]): int(r["protocolo_id"])
                    for r in banco(con_itens).ler(
                        """SELECT usado_por_ato_id AS ato_id,
                                  min(protocolo_id) AS protocolo_id
                             FROM cx_protocolo_atos
                            WHERE usado_por_tabela = 'rg_atos'
                              AND usado_por_ato_id = ANY(%s)
                            GROUP BY usado_por_ato_id
                            ORDER BY usado_por_ato_id""",
                        ([int(a["id"]) for a in atos_escolhidos],))}
            partes_obj = []
            naturezas_av = []
            ordens_av = []
            for a in atos_escolhidos:
                if str(a.get("tipo") or "").upper() != "AVERBACAO":
                    continue
                nat_av, _ = RGTEOR.parse_campos_do_teor(a.get("teor"))
                ordem = a.get("numero_ordem") or a.get("rotulo") or ""
                if ordem and nat_av:
                    partes_obj.append(RGTEOR.preencher_moldura(
                        moldura, "AVERBACAO_COM_NATUREZA",
                        {"ordem": ordem, "natureza": nat_av}))
                elif ordem:
                    partes_obj.append(RGTEOR.preencher_moldura(
                        moldura, "AVERBACAO_SEM_NATUREZA", {"ordem": ordem}))
                if ordem:
                    ordens_av.append(str(ordem))
                if nat_av:
                    naturezas_av.append(nat_av)
                data_av = a.get("data_ato")
                if data_av:
                    data_apresentacao_averbacao = str(data_av)[:10]
                pid = a.get("protocolo_id") or protocolo_do_item.get(int(a["id"]))
                if pid and int(pid) not in protocolo_ids_av:
                    protocolo_ids_av.append(int(pid))
            if partes_obj:
                objeto_certificado = RGTEOR.preencher_moldura(
                    moldura, "OBJETO_AVERBACOES",
                    {"averbacoes": ", ".join(partes_obj)})
            if naturezas_av:
                natureza_certificada = "; ".join(naturezas_av)
            if ordens_av:
                identificacao_curta = RGTEOR.preencher_moldura(
                    moldura, ("IDENTIFICACAO_AVERBACAO" if len(ordens_av) == 1
                              else "IDENTIFICACAO_AVERBACOES"),
                    {"ordens": ", ".join(ordens_av)})
        protocolo_da_averbacao = ""
        if protocolo_ids_av:
            with db.connect() as con_prot:
                numeros = [
                    r["numero"] for pid in protocolo_ids_av
                    for r in banco(con_prot).ler(
                        "SELECT numero FROM cx_protocolos WHERE id=%s", (pid,))
                    if r["numero"]
                ]
            protocolo_da_averbacao = ", ".join(dict.fromkeys(numeros))
        # O PROTOCOLO DO REGISTRO, QUANDO É ELE QUE SE CERTIFICA — LT05,
        # 20/10/2026. A capa diz «foi apresentado em …, protocolado sob nº …»,
        # e a rota só preenchia o protocolo na certidão de averbações: a do
        # registro saía «protocolado sob nº —» e com a data do registro no
        # lugar da apresentação, embora o título que o gerou tenha o número
        # e a data no Livro de Protocolo (`rg_registros.titulo_id`, a ponte
        # gravada ao registrar). Sem título (acervo), fica como estava.
        data_apresentacao_do_titulo = ""
        if not objeto_certificado and registro.get("titulo_id"):
            with db.connect() as con_tit:
                tit = banco(con_tit).um(
                    "SELECT numero, data_apresentacao FROM rg_titulos WHERE id=%s",
                    (int(registro["titulo_id"]),))
            if tit and tit["numero"] is not None:
                protocolo_da_averbacao = str(tit["numero"])
                data_apresentacao_do_titulo = str(tit["data_apresentacao"] or "")[:10]
        # A DATA DA CERTIDÃO É A DA EMISSÃO (LT05): sem `dia`, a capa e o fecho
        # saíam com a data da reimpressão, e a segunda via de amanhã diria que
        # a certidão foi expedida amanhã — o hash dela diz outra coisa.
        try:
            dia_da_emissao = date.fromisoformat(str(cert.get("emitida_em") or "")[:10])
        except ValueError:
            dia_da_emissao = None
        # **O SELO DE VERDADE, SE JÁ SAIU** — achado do oficial em
        # 12/09/2026: «segue sem selo a certidão que emiti». O selo estava
        # certo no banco (`at_certidoes.selo`); o PDF visual só nunca tinha
        # como recebê-lo, e desenhava sempre a moldura vazia.
        with db.connect() as con_selo:
            selo_da_certidao = _selo_para_teor(con_selo, cert.get("selo"))
            # O VOLUME DO LIVRO (LT05): o registro lavrado aqui não tem
            # `volume` (é da carga do E-Ofício), e o livro dele mora em
            # `nu_livros` — sem isto a capa dizia só «Livro … A».
            volume_do_livro = registro["volume"] or (banco(con_selo).valor(
                "SELECT numero FROM nu_livros WHERE id=%s",
                (int(ato_reg["livro_id"]),))
                if ato_reg and ato_reg.get("livro_id") else None)
        try:
            with db.connect() as con:
                pdf = RGCERT.gerar_pdf(
                    numero=registro["numero"],
                    imagens=caminhos,
                    # QUEM SUBSCREVE É QUEM EXPEDIU (LT05), como no Livro 3:
                    # a segunda via impressa por outra pessoa não pode dizer
                    # que foi ela quem a subscreveu. Certidão de antes da
                    # coluna cai em quem imprime, como sempre caiu.
                    lavrante_nome=(cert.get("emitida_por_nome")
                                   or usuario_nome()),
                    lavrante_funcao=(cert.get("emitida_por_funcao")
                                     or usuario_funcao()),
                    denominacao=registro["requerente_nome"] or "",
                    natureza=natureza_certificada,
                    objeto_certificado=objeto_certificado,
                    identificacao_curta=identificacao_curta,
                    identificacao_data=data_apresentacao_averbacao,
                    data_registro=data_registro,
                    protocolo=protocolo_da_averbacao,
                    data_apresentacao=(data_apresentacao_averbacao
                                       or data_apresentacao_do_titulo),
                    cns=s.get("ri_cns") or "",
                    unit_short=(s.get("unit_name")
                                or ""),
                    oficial=(s.get("serventia_titular")
                             or ""),
                    endereco=s.get("serventia_endereco") or "",
                    telefone=s.get("serventia_telefone") or "",
                    email=s.get("serventia_email") or "",
                    cidade=s.get("ri_cidade") or "",
                    uf=s.get("ri_uf") or "MA",
                    serie=registro["serie"],
                    atribuicao=registro["atribuicao"],
                    volume=volume_do_livro,
                    dia=dia_da_emissao,
                    certidao_numero=str(cert["numero"]),
                    certidao_ano=str(cert["ano"]),
                    con=con,
                    # **SEM QUADRO DE EMOLUMENTOS** — pedido do oficial em
                    # 12/09/2026: «retire a tabela». O quadro só saía com
                    # zeros mesmo (nenhuma chamada calcula valor real ainda:
                    # ver o "placeholder" citado no topo deste módulo), e as
                    # categorias que ele tinha (Estado/Secretaria da
                    # Fazenda/TJ, depois FERC/FADEP/FEMP/FERRFIS) não
                    # resolvem isso — o problema era mostrar uma tabela sem
                    # conteúdo nenhum. `com_emolumentos=False` desliga o
                    # desenho; a função continua existindo para quando
                    # houver valor de verdade a mostrar.
                    com_emolumentos=False,
                    selo=selo_da_certidao,
                )
        except RGCERT.CertidaoPdfError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("atribuicoes_certidao",
                                    certidao_id=certidao_id))
        audit("ATRIB_CERTIDAO_PDF", "at_certidoes", certidao_id,
              {"numero": cert["numero"], "ano": cert["ano"],
               "paginas": len(caminhos)})
        nome = (f"certidao-{cert['atribuicao'].lower()}-"
                f"{cert['numero']}-{cert['ano']}.pdf")
        return send_file(
            io.BytesIO(pdf),
            mimetype="application/pdf",
            as_attachment=False,
            download_name=nome,
        )

    def _papel_da_certidao_do_livro3(linha) -> bytes:
        """O papel da certidão do Livro 3 por TEXTO — **o mesmo do Livro 2**.

            «e falta o selo na averbação»
            «e falta cabeçalho do cartório na certidão. deixe igual a
             certidão equivalente do livro 2»      — o oficial, 23/09/2026

        Medido na certidão 1/2026 (registro 1.243): a AV-1 tem selo no razão —
        `AVESVD0000002KP37IM7S7892Y90`, item 16.22.2, de 22/09 às 19h15 — e o
        papel a imprimia **sem ele**; e o cabeçalho da casa não saía, porque
        esta rota o calava quando achava «REPÚBLICA FEDERATIVA» no teor — e no
        1.243 essa frase está **no meio**, dentro da página do E-Ofício que o
        registro reproduz, e não no alto.

        O QUE É DO LIVRO 2, PEÇA POR PEÇA:

          * o cabeçalho da casa **no cabeçalho da página**, repetido em cada
            folha — `cabecalho_certidao_completo_odf`, a mesma função
            (era a compacta até 23/09/2026, quando ele pediu o completo);
          * **o selo de cada ato logo abaixo do ato** — o miolo do Livro 2 é
            «o teor do ato e, em seguida, o selo do ato»;
          * o fecho «Era o que nela continha.», a finalidade, a validade do
            art. 553 e quem expediu.

        **TUDO NA IMPRESSÃO, e nada no teor.** O teor é congelado com sha256
        na emissão; desenhado aqui, a certidão que já saiu ganha o cabeçalho e
        o selo **sem uma letra do teor mudar** — o precedente é o das linhas
        entre os atos, que o Livro 2 desenha ao imprimir pelo mesmo motivo.

        **A DATA É A DA EMISSÃO, E NÃO A DE HOJE**: a segunda via impressa
        amanhã não pode dizer que a certidão foi emitida amanhã. E **quem
        expediu** é o gravado na emissão, e não quem está imprimindo.
        """
        from datetime import date as _date
        from html import escape as _esc

        import ri_frases

        s = sv()
        teor = str(linha["teor"] or "")
        with db.connect() as con:
            atos = banco(con).ler(
                "SELECT * FROM ra_atos WHERE registro_id=%s ORDER BY numero, id",
                (int(linha["registro_id"]),))
            try:
                ids = json.loads(dict(linha).get("atos_ids") or "null")
            except (TypeError, ValueError):
                ids = None
            blocos = CE.blocos_por_ato(teor, atos, ids)
            # O SELO DE CADA ATO, pela chave inteira — `tabela` mais `ato_id`:
            # por `ato_id` sozinho vêm selos de outra atribuição.
            etiquetas = {
                int(a["id"]): AS.etiqueta_do_ato(con, "ra_atos", a["id"],
                                                 a.get("selo") or "")
                for _seg, a in blocos if a}
            etiqueta_da_certidao = AS.etiqueta_do_ato(
                con, "at_certidoes", int(linha["id"]),
                dict(linha).get("selo") or "")
            # O TÍTULO E O FECHO MORAM NA BASE — LF06B (19/10/2026): lidos aqui,
            # com a conexão da casa (o ajuste vence o padrão). Quando cada
            # pedaço entra continua sendo decidido abaixo.
            _modelos = ri_frases.ler(con, "RI_LIVRO3_CERTIDAO_TITULO",
                                     "RI_LIVRO3_CERTIDAO_CANCELADA",
                                     "RI_LIVRO3_CERTIDAO_FECHO")

        imagens: dict = {}
        titulo = ri_frases.montar(_modelos["RI_LIVRO3_CERTIDAO_TITULO"],
                                  numero=linha["numero"], ano=linha["ano"])
        if int(linha["cancelada"] or 0):
            titulo += ri_frases.montar(
                _modelos["RI_LIVRO3_CERTIDAO_CANCELADA"],
                motivo=_esc(linha["motivo_cancelamento"] or ""))
        # TEXTO CORRIDO + SEPARADOR FULL-WIDTH — mesmo padrao do Livro 2 RI
        # (Beatriz 29/09/2026, certidao 3-Aux). `texto_para_odf` punha um
        # paragrafo por linha e o papel saia com espacamento excessivo; o RI
        # junta o miolo via `html_em_texto_corrido` e desenha `P-separa-ato`
        # entre atos (largura total). Layout so na impressao — teor congelado
        # nao muda; reimprimir ODT aplica o ajuste sem reemitir.
        # Sem linha de assinatura a mao: ja removida no teor na emissao
        # (`sem_linha_de_assinatura_a_mao`) e o fecho abaixo so traz nome/funcao.
        corpo_odf = html_para_odf(titulo)
        ja_houve_bloco = False
        for trecho, ato in blocos:
            html_trecho = RODT.texto_para_html(trecho)
            html_trecho = RODT.html_em_texto_corrido(html_trecho, None)
            odf_trecho = html_para_odf(html_trecho)
            if ja_houve_bloco and odf_trecho:
                corpo_odf += RODT.SEPARADOR_DE_ATO
            corpo_odf += odf_trecho
            ja_houve_bloco = True
            etiqueta = etiquetas.get(int(ato["id"])) if ato else ""
            if etiqueta:
                corpo_odf += RODT.carimbo_compacto_odf(
                    etiqueta, rotulo="SELO DIGITAL DO TJMA", imagens=imagens,
                    prefixo_qr=f"qr-ato-{int(ato['id'])}")

        emitida = str(linha["emitida_em"] or "")[:10]
        try:
            quando = data_por_extenso(_date.fromisoformat(emitida))
        except ValueError:
            quando = emitida
        validade = str(dict(linha).get("validade_ate") or "")
        valida_ate = (f"{validade[8:10]}/{validade[5:7]}/{validade[:4]}"
                      if len(validade) >= 10 else "")
        quem = (dict(linha).get("emitida_por_nome")
                or s.get("serventia_titular") or "")
        funcao = (dict(linha).get("emitida_por_funcao")
                  or s.get("serventia_titulo") or "")
        # O FECHO MORA NA BASE (`RI_LIVRO3_CERTIDAO_FECHO`). O que cada claro
        # vale é daqui: a data da EMISSÃO, quem expediu (o gravado, senão a
        # serventia), o texto já escapado; campo vazio não sai.
        fecho = ri_frases.montar(
            _modelos["RI_LIVRO3_CERTIDAO_FECHO"],
            finalidade=_esc(linha["finalidade"]) if linha["finalidade"] else "",
            valida_ate=valida_ate, quando=quando,
            cidade=_esc(s.get("ri_cidade", "")), uf=_esc(s.get("ri_uf", "")),
            quem=_esc(quem) if quem else "", funcao=_esc(funcao) if funcao else "",
            numero=linha["numero"], ano=linha["ano"],
            emitida_em=linha["emitida_em"], hash_certidao=linha["hash_certidao"])
        corpo_odf += html_para_odf(fecho)

        frag_do_selo, imagens_do_selo = RODT.carimbo_da_certidao_odf(
            etiqueta_da_certidao)
        corpo_odf += frag_do_selo

        # O COMPLETO, e não o compacto — pedido 23/09/2026 («o cabeçalho não
        # está completo»), aprovado em imagem, o mesmo do Livro 2.
        cab_odf, cab_imgs = RODT.cabecalho_certidao_completo_odf(s)
        # AS IMAGENS VÃO NUM PACOTE SÓ: o `.odt` é um zip, e uma segunda
        # chamada sobrescreveria a primeira — a mesma regra do Livro 2.
        todas = dict(cab_imgs or {})
        todas.update(imagens)
        todas.update(imagens_do_selo or {})
        return gerar_odt(corpo_odf, cabecalho_odf=cab_odf,
                         imagens=todas or None,
                         cabecalho_altura_min="2.0cm",
                         cabecalho_margem_baixo="0.25cm",
                         cabecalho_borda=False)

    def _assinatura_de_quem_expediu(c) -> str:
        """A linha em que quem expediu a certidão assina. Só monta o ODF.

        **É a mesma do Livro 2**, e existe pelo mesmo motivo: a certidão por
        reprodução é composta das folhas varridas, e sem esta linha o papel
        terminaria na última folha do livro, sem ninguém assinando embaixo.

        **O NOME SÓ SAI SE ESTIVER GRAVADO** — as certidões anteriores a
        21/09/2026 não têm `emitida_por_nome`, e saem com a linha e sem nome,
        que é a verdade. Escrever ali quem está imprimindo faria a segunda via
        afirmar que foi expedida por quem só a reimprimiu.

        **SEM O BRANCO DA CANETA, COMO O LIVRO 2 — 23/09/2026.** A ordem de
        22/09 tirou da certidão o espaço de assinatura à mão («só na ficha»),
        e em 23/09 o oficial decidiu que ela diz quem a expediu: o nome e o
        título, sem as duas linhas em branco (`ri_web._assinatura_de_quem_
        emitiu`). O traço já tinha saído daqui; as duas linhas em branco
        tinham ficado, e o Livro 3 é para ser igual ao Livro 2.
        """
        from html import escape

        def _coluna(nome: str) -> str:
            try:
                return str(dict(c).get(nome) or "").strip()
            except (KeyError, IndexError, TypeError):
                return ""

        quem = _coluna("emitida_por_nome")
        funcao = _coluna("emitida_por_funcao")
        linhas = []
        if quem:
            linhas.append('<text:p text:style-name="P-centro">'
                          f"{escape(quem)}</text:p>")
            if funcao:
                linhas.append('<text:p text:style-name="P-centro">'
                              f"{escape(funcao)}</text:p>")
        return "".join(linhas)

    @app.route("/atribuicoes/certidoes/<int:certidao_id>/odt")
    @login_required
    def atribuicoes_certidao_odt(certidao_id: int):
        """A certidão em .odt, para imprimir e assinar.

        O CABEÇALHO DA SERVENTIA SÓ SAI UMA VEZ. O teor que veio do acervo
        muitas vezes já traz o dele dentro — o E-Ofício guardava a página
        inteira, e não só o registro. Quando traz, este `.odt` não põe outro em
        cima; e não corta nada do teor: texto de certidão não se edita.
        """
        with db.connect() as con:
            linha = CE.certidao(con, certidao_id)
        if not linha:
            abort(404)

        #  QUANDO A CERTIDAO E POR REPRODUCAO, O PAPEL SAO AS FOLHAS.
        #
        #  O teor gravado e o resumo (quantas folhas, e o sha256); imprimi-lo
        #  como se fosse a certidao entregaria ao cliente um paragrafo em vez
        #  do livro. Quem monta o papel e `ri_digitalizacao.odt_da_digitalizacao`,
        #  o mesmo do Livro 2 — escrever um segundo montador daria duas versoes
        #  do papel que reproduz o livro, e elas divergiriam no primeiro
        #  conserto.
        if str(dict(linha).get("fonte_corpo") or "").upper() == "DIGITALIZACAO":
            caminho = Path(str(dict(linha).get("digi_path") or ""))
            if not caminho.is_file():
                flash("A digitalização desta certidão não está no disco. Não "
                      "dá para reimprimir a reprodução.", "danger")
                return redirect(url_for("atribuicoes_certidao",
                                        certidao_id=certidao_id))
            #  CERTIDAO CANCELADA NAO SE REIMPRIME POR REPRODUCAO.
            #
            #  A certidao por TEXTO sai com «CERTIDÃO CANCELADA» escrito no
            #  alto; esta e composta das folhas varridas, e nao ha onde
            #  carimbar sem escrever por cima do livro. Uma reproducao
            #  cancelada e indistinguivel de uma valida na mao de quem a
            #  recebe — e por isso ela para aqui, dizendo o motivo.
            if int(dict(linha).get("cancelada") or 0):
                flash("Esta certidão está CANCELADA "
                      f"({dict(linha).get('motivo_cancelamento') or 'sem motivo'})"
                      " e foi emitida por reprodução da digitalização: o papel "
                      "reproduz as folhas do livro e não teria onde dizer que "
                      "está cancelada. Emita uma certidão nova.", "danger")
                return redirect(url_for("atribuicoes_certidao",
                                        certidao_id=certidao_id))
            with db.connect() as con:
                etiqueta = AS.etiqueta_do_ato(
                    con, "at_certidoes", certidao_id,
                    dict(linha).get("selo") or "")
            try:
                # O MODELO DA CASA DA REPROGRAFICA (substituta, 20/10/2026;
                # LH02): o papel identifica o registro e o livro, a data e
                # quem assina, e o cabecalho le o cadastro da serventia.
                _l = dict(linha)
                _livro_repro = {
                    "LIVRO3": " do Livro nº 3 – Registro Auxiliar",
                    "RCPJ_RTD": " do Registro Civil das Pessoas Jurídicas e de "
                                "Títulos e Documentos",
                }.get(str(_l.get("atribuicao") or "").upper(), "")
                _ident_repro = (f'Registro nº {_l.get("registro_numero")}{_livro_repro}'
                                if _l.get("registro_numero") else "")
                # COM O `con`, O TEXTO SAI COM O AJUSTE DA CASA — LF06B: o
                # CERTIFICO e o fecho são os papéis `RI_REPROGRAFICA_*`.
                with db.connect() as con:
                    arquivo = RADIGI.odt_da_digitalizacao(
                        caminho, selo_texto=etiqueta,
                        nome=f'certidao-{linha["numero"]}-{linha["ano"]}',
                        rotulo_selo="SELO DA CERTIDÃO",
                        assinatura_odf=_assinatura_de_quem_expediu(linha),
                        identificacao=_ident_repro,
                        data_emissao=str(_l.get("emitida_em") or "")[:10],
                        signatario=(str(_l.get("emitida_por_nome") or "").strip(),
                                    str(_l.get("emitida_por_funcao") or "").strip()),
                        serventia=dados_serventia(db.get_settings),
                        con=con)
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("atribuicoes_certidao",
                                        certidao_id=certidao_id))
            audit("ATRIB_CERTIDAO_ODT", "at_certidoes", certidao_id,
                  {"numero": linha["numero"], "ano": linha["ano"],
                   "fonte": "DIGITALIZACAO"})
            return IMPW.resposta_do_papel(
                arquivo,
                nome=(f"certidao-{linha['atribuicao'].lower()}-"
                      f"{linha['numero']}-{linha['ano']}"),
                get_setting=db.get_setting,
                voltar_para=url_for("atribuicoes_certidao",
                                    certidao_id=certidao_id))

        #  O LIVRO 3 POR TEXTO TEM PAPEL PRÓPRIO, IGUAL AO DO LIVRO 2 —
        #  23/09/2026. O RCPJ/RTD continua como estava: o teor dele traz a
        #  página inteira do E-Ofício, com o cabeçalho de lá, e é para ele
        #  que a regra de não repetir cabeçalho existe.
        if str(linha["atribuicao"] or "").upper() == "LIVRO3":
            arquivo = _papel_da_certidao_do_livro3(linha)
            audit("ATRIB_CERTIDAO_ODT", "at_certidoes", certidao_id,
                  {"numero": linha["numero"], "ano": linha["ano"]})
            return IMPW.resposta_do_papel(
                arquivo,
                nome=(f"certidao-livro3-{linha['numero']}-{linha['ano']}"),
                get_setting=db.get_setting,
                voltar_para=url_for("atribuicoes_certidao",
                                    certidao_id=certidao_id))

        # O PAPEL É O RCPJ_RTD_CERTIDAO_ODT DO CATÁLOGO desde o LF06F
        # (19/10/2026) — era uma f-string aqui. A regra (cabeçalho só se o teor
        # não trouxer o dele, a marca de cancelada) foi junto para
        # `atrib_certidao.papel_por_texto`; o teor continua o congelado.
        with db.connect() as con:
            html = CE.papel_por_texto(con, dict(linha), sv=sv(),
                                      hoje=hoje_extenso())
            # **O CARIMBO DO SELO — 17/09/2026, e ele nao existia aqui.** Como
            # no Protesto: a rota montava o teor e parava. Medido: **38 selos**
            # em `/selo/rtdpj/pessoa-juridica/certidao` no razao desta casa.
            etiqueta = AS.etiqueta_do_ato(
                con, "at_certidoes", certidao_id,
                dict(linha).get("selo") or "")
        frag_do_selo, imagens_do_selo = RODT.carimbo_da_certidao_odf(etiqueta)
        arquivo = gerar_odt(html_para_odf(html) + frag_do_selo,
                            titulo=f"Certidão {linha['numero']}/{linha['ano']}",
                            imagens=imagens_do_selo or None)
        audit("ATRIB_CERTIDAO_ODT", "at_certidoes", certidao_id,
              {"numero": linha["numero"], "ano": linha["ano"]})
        nome = (f"certidao-{linha['atribuicao'].lower()}-"
                f"{linha['numero']}-{linha['ano']}")
        return IMPW.resposta_do_papel(
            arquivo, nome=nome, get_setting=db.get_setting,
            voltar_para=url_for("atribuicoes_certidao", certidao_id=certidao_id))

    @app.route("/atribuicoes/certidoes/<int:certidao_id>/cancelar",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def atribuicoes_certidao_cancelar(certidao_id: int):
        """Cancela a certidão emitida. ESCREVE. O teor fica."""
        try:
            with db.transaction() as con:
                resultado = CE.cancelar(
                    con, certidao_id, motivo=_campo("motivo"),
                    agora=agora(), usuario=usuario_nome(),
                    selo_cancelado_tjma=_campo("selo_cancelado_tjma"))
        except CE.CertidaoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("atribuicoes_certidao",
                                    certidao_id=certidao_id))
        audit("ATRIB_CERTIDAO_CANCELADA", "at_certidoes", certidao_id,
              {"motivo": _campo("motivo"), "declaracao_selo_tjma": True,
               **resultado})
        folhas = resultado.get("folhas_recuperadas") or []
        recado = (f" Folha(s) {', '.join(folhas)} devolvida(s) ao estoque."
                  if folhas else "")
        flash("Certidão cancelada. O teor fica gravado, como saiu." + recado,
              "success")
        return redirect(url_for("atribuicoes_certidao",
                                certidao_id=certidao_id))

    # --------------------------------------------------------------- carga

    # ------------------------------------------- importar de OUTRO sistema

    @app.route("/importar-padrao", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")   # aberta ao USER por ordem dele (11/10/2026)
    def importar_padrao_tela():
        """O padrão de importação da casa — relato #31.

        **CONFERIR E IMPORTAR SÃO DOIS BOTÕES**, e não um: aqui não há como
        desfazer, porque acervo importado vira o livro. O primeiro não grava
        nada e mostra o que entraria; o segundo grava o que passou.
        """
        especie = request.values.get("especie", "") or next(iter(IMPP.MODELOS))
        if _papel_atual() == "USER" and especie not in (
                "RI_MATRICULA", "RCPN_ASSENTO"):
            flash("Seu perfil pode importar matrículas do Registro de Imóveis "
                  "e assentos do Registro Civil pelo padrão da casa. Outras "
                  "espécies continuam com administrador ou gerente.", "warning")
            return redirect(url_for("importar_padrao_tela",
                                    especie="RI_MATRICULA"))
        texto = request.form.get("texto", "")
        erro = ""
        token = ""
        # **O ARQUIVO GANHA DO TEXTAREA** — relato do oficial em 13/09/2026:
        # "não achei ponto para importar o arquivo, só digitando ele na
        # tela". Um lote de acervo tem milhares de registros; ninguém cola
        # isso à mão, e o textarea nunca teve `input type="file"` ao lado.
        arquivo = request.files.get("arquivo")
        if arquivo and arquivo.filename:
            try:
                texto = arquivo.read().decode("utf-8")
            except UnicodeDecodeError:
                erro = ("O arquivo não está em UTF-8 — salve-o de novo "
                        "nesse formato antes de enviar.")
        elif not texto.strip():
            # **O CLIQUE EM "IMPORTAR" NÃO TRAZ O ARQUIVO DE VOLTA** — relato
            # do oficial em 13/09/2026: conferiu um arquivo grande, clicou em
            # "Importar" e a tela voltou em branco. O navegador nunca reenvia
            # um `<input type="file">` sozinho, e o textarea fica vazio de
            # propósito quando o texto é grande (abaixo, `texto_no_textarea`)
            # — as duas fontes desapareciam no segundo clique, e o `if` que
            # decide se há o que processar ficava com o texto vazio, calado.
            # O "Conferir" guarda o texto num arquivo à parte desta máquina
            # (`_pasta_importacoes_pendentes`), e o "Importar" o busca pelo
            # token — que é a única coisa que precisa sobreviver ao clique.
            token = re.sub(r"[^0-9a-f]", "", request.form.get(
                "token_arquivo", ""))[:32]
            caminho_guardado = (_pasta_importacoes_pendentes() /
                                f"{token}.json") if token else None
            if caminho_guardado and caminho_guardado.is_file():
                texto = caminho_guardado.read_text(encoding="utf-8")
            elif request.method == "POST":
                erro = ("O arquivo conferido não foi encontrado — pode ter "
                        "expirado. Envie-o de novo e clique em Conferir "
                        "antes de Importar.")
        quadro = None
        if especie not in IMPP.MODELOS:
            flash(f"Não sei importar «{especie}».", "danger")
            return redirect(url_for("importar_padrao_tela"))

        if request.method == "POST" and not erro and texto.strip():
            o_que = request.form.get("o_que", "conferir")
            try:
                if o_que == "rascunhos":
                    # A FILA DE PRÉ-CADASTROS (11/10/2026): cada assento do
                    # arquivo vira um rascunho conferido; o termo do arquivo
                    # é descartado e sai do modelo da casa na lavratura.
                    with db.transaction() as con:
                        fila = IMPP.para_rascunhos(con, texto, agora=agora(),
                                                   por=usuario_nome())
                    audit("IMPORTACAO_PADRAO_RASCUNHOS", "rascunhos_de_tela", None,
                          {"criados": len(fila["criados"]),
                           "recusados": len(fila["recusados"]),
                           "de_onde_veio": fila["de_onde_veio"]})
                    com_trava = sum(1 for c in fila["criados"] if c["travas"])
                    flash(f"{len(fila['criados'])} rascunho(s) na fila de "
                          f"Rascunhos, prontos para conferir e lavrar"
                          + (f"; {com_trava} com dado a arrumar antes"
                             if com_trava else "")
                          + (f"; {len(fila['ja_na_fila'])} já estavam na fila"
                             if fila["ja_na_fila"] else "")
                          + (f"; {len(fila['recusados'])} recusado(s) — veja "
                             "o motivo abaixo" if fila["recusados"] else "")
                          + ". O termo de cada um será escrito pelo modelo da "
                          "casa ao lavrar.", "success")
                    fora = sorted({x for c in fila["criados"] for x in c["ficou_de_fora"]})
                    if fora:
                        flash("O arquivo trazia o que a fila não leva à tela: "
                              + "; ".join(fora) + ".", "warning")
                    if not fila["recusados"]:
                        return redirect(url_for("rascunhos"))
                    # Com recusados, fica nesta tela: o quadro mostra cada um
                    # com o motivo, para corrigir o arquivo e mandar de novo.
                    with db.connect() as con:
                        quadro = IMPP.conferir(con, texto)
                elif o_que == "importar":
                    with db.transaction() as con:
                        quadro = IMPP.importar(con, texto, agora=agora(),
                                               por=usuario_nome())
                    # `audit` abre transacao propria: FORA do `with`.
                    audit("IMPORTACAO_PADRAO", quadro["tabela"], None,
                          {"entraram": quadro["entraram"],
                           "recusados": len(quadro["recusados"]),
                           "de_onde_veio": quadro["de_onde_veio"]})
                    flash(f"Entraram {quadro['entraram']} registro(s). "
                          f"O que foi recusado está abaixo, com o motivo — "
                          f"corrija o arquivo e mande de novo: o que já entrou "
                          f"não entra duas vezes.", "success")
                    if token:
                        (_pasta_importacoes_pendentes() /
                         f"{token}.json").unlink(missing_ok=True)
                    token = ""
                else:
                    with db.connect() as con:
                        quadro = IMPP.conferir(con, texto)
                    # **GUARDA O TEXTO CONFERIDO**, para o botão "Importar" —
                    # que só aparece depois deste passo — ter o que enviar.
                    pasta = _pasta_importacoes_pendentes()
                    token = uuid.uuid4().hex
                    (pasta / f"{token}.json").write_text(
                        texto, encoding="utf-8")
                    _limpar_importacoes_pendentes_antigas(pasta)
            except IMPP.ImportacaoError as e:
                erro = str(e)
            except sqlite3.Error as e:
                erro = SEGWEB.recado_de_erro(
                    e, "importacoes", "O banco recusou o registro; o detalhe "
                    "ficou no registro do servidor.")

        with db.connect() as con:
            lista_de_campos = IMPP.campos(con, especie)
            modelo = IMPP.modelo_em_branco(con, especie)
        # **NÃO DEVOLVE UM ARQUIVO GRANDE PARA DENTRO DO `<textarea>`.** Um
        # lote de acervo tem megabytes; ecoar isso de volta na página faria
        # o HTML da resposta pesar o mesmo tanto, só para reaparecer numa
        # caixa que ninguém vai editar. O textarea só mostra o que a pessoa
        # pode ter digitado — pequeno, por definição.
        texto_no_textarea = texto if len(texto) <= 200_000 else ""
        return render_template(
            "importar_padrao.html", especie=especie, modelos=IMPP.MODELOS,
            campos=lista_de_campos, modelo=modelo, quadro=quadro, erro=erro,
            texto=texto_no_textarea, formato=IMPP.FORMATO, versao=IMPP.VERSAO,
            campo_da_chave=IMPP.CAMPO_DA_CHAVE, token_arquivo=token)

    def _pasta_importacoes_pendentes() -> Path:
        """Onde o texto conferido espera o clique em "Importar". Só nesta
        máquina, e não é anexo de ninguém — não entra no `archive_root`."""
        pasta = Path(app.config["DATA_DIR"]) / "importacoes_pendentes"
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    def _pasta_crc_selecoes() -> Path:
        """Onde a lista de assentos escolhidos em `/rcpn/crc` espera os
        cliques seguintes (baixar, marcar como enviado, enviar).

        **RELATO DO OFICIAL EM 13/09/2026: "monto o arquivo com todos, mas
        não acontece nada depois, não gera o xml".** Com o acervo importado
        (6700+ assentos), a tela repetia a lista inteira de IDs como
        `<input type="hidden">` em QUATRO formulários diferentes — o de
        montar mais os três de baixo — e ainda embutia o XML inteiro (9 MB
        medidos) num `<pre>`. A página passou de 15 MB, e o navegador
        parecia travado nela. Aqui fica só o TOKEN; a lista de IDs mora
        neste arquivo, uma vez, como no `_pasta_importacoes_pendentes` do
        `/importar-padrao`."""
        pasta = Path(app.config["DATA_DIR"]) / "crc_selecoes"
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    def _guardar_crc_selecao(escolhidos: list[int]) -> str:
        token = uuid.uuid4().hex
        pasta = _pasta_crc_selecoes()
        (pasta / f"{token}.json").write_text(
            json.dumps(escolhidos), encoding="utf-8")
        _limpar_importacoes_pendentes_antigas(pasta)
        return token

    def _escolhidos_do_token_crc() -> list[int]:
        """Lê a lista de IDs pelo `token_escolhidos` do formulário. Sem
        token (ou token vencido/inválido), cai para o `assento` de sempre —
        que continua servindo quem monta o POST à mão ou com poucos
        registros."""
        token = re.sub(r"[^0-9a-f]", "", request.form.get(
            "token_escolhidos", ""))[:32]
        if token:
            caminho = _pasta_crc_selecoes() / f"{token}.json"
            if caminho.is_file():
                try:
                    return [int(x) for x in json.loads(
                        caminho.read_text(encoding="utf-8"))]
                except (ValueError, TypeError):
                    pass
        # o que não é número não foi marcado; o id que passa do `integer` não
        # é de assento nenhum, e estourava a marca de enviado (LD13)
        return [n for n in (numero_digitado(x, maximo=MAIOR_INTEGER)
                            for x in request.form.getlist("assento"))
                if n is not None]

    def _limpar_importacoes_pendentes_antigas(pasta: Path) -> None:
        """O que ninguém importou em 1 dia não vai ficar acumulando —
        conferência abandonada é a regra, não a exceção, e o texto guardado
        pode ser um lote inteiro do acervo."""
        limite = time.time() - 86400
        for item in pasta.glob("*.json"):
            try:
                if item.stat().st_mtime < limite:
                    item.unlink(missing_ok=True)
            except OSError:
                continue

    @app.route("/importar-padrao/preencher", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def importar_padrao_preencher():
        """Leva o registro do arquivo para o FORMULÁRIO do ato novo. NÃO grava.

        Segunda metade do relato #31, na opção que o oficial escolheu em
        30/08/2026: o mesmo padrão, jogando os dados na tela em vez de gravar
        direto.

        **AQUI O ATO NASCE NOVO** — vai tomar número, ocupar folha, selar e
        cobrar. O arquivo adianta a digitação e não decide nada: quem lavra
        confere e assina. Por isso ele **não passa pelo caminho da importação**,
        que grava acervo direto no livro.

        **O valor vai pela SESSÃO, e não pelo endereço.** Nome, data de
        nascimento e endereço de cliente numa `query string` ficam no histórico
        do navegador do balcão e no registro do servidor — e dado de pessoa não
        viaja em endereço.
        """
        texto = request.form.get("texto", "")
        try:
            with db.connect() as con:
                pronto = IMPP.para_formulario(con, texto)
        except IMPP.ImportacaoError as e:
            flash(str(e), "danger")
            return redirect(url_for("importar_padrao_tela"))

        session[IMPP.NA_SESSAO] = pronto
        aviso = (f"Formulário preenchido a partir do arquivo "
                 f"(registro «{pronto['chave']}»). **Confira antes de lavrar** — "
                 f"quem assina é você, e o ato nasce novo aqui.")
        if pronto["sem_campo_na_tela"]:
            aviso += (" O arquivo trazia campos que esta tela não pergunta, e "
                      "eles NÃO foram preenchidos: "
                      + ", ".join(pronto["sem_campo_na_tela"]) + ".")
        flash(aviso, "warning")
        return redirect(url_for(pronto["formulario"]))

    @app.route("/importar-padrao/manual")
    @roles_required("ADMIN", "MANAGER", "USER")
    def importar_padrao_manual():
        """O manual para baixar e entregar a quem vai gerar o arquivo.

        **Ele leva a lista de campos junto**, que o documento em disco nao tem:
        quem o recebe esta fora da serventia e nao tem a tela onde ela mora.
        """
        try:
            with db.connect() as con:
                texto = IMPP.manual(con)
        except IMPP.ImportacaoError as e:
            flash(str(e), "danger")
            return redirect(url_for("importar_padrao_tela"))
        nome = f"padrao-de-importacao-{db.now()[:10]}.md"
        return Response(
            texto.encode("utf-8"), mimetype="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    # -------------------------- importar PRÉ-CADASTROS do Registro Civil
    #
    # «precisamos de uma forma mais intuitiva de importar esse documento e
    #  precisamos uma forma facil de baixar o manual de preenchimento desse
    #  arquivo, principalmente relativo a dados das partes» — 11/10/2026.
    #
    # A tela geral de importação serve seis espécies e dois caminhos (acervo e
    # ato novo); esta serve UM: o arquivo de assentos novos do Registro Civil,
    # em três passos — baixar o manual/modelo, enviar o arquivo e ver a prévia,
    # pôr na fila. A prévia não grava nada; a fila grava só rascunhos.

    @app.route("/rcpn/importar", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")   # aberta ao USER por ordem dele (11/10/2026)
    def rcpn_importar():
        previa, erro, token = None, "", ""
        if request.method == "POST":
            o_que = request.form.get("o_que", "conferir")
            texto = ""
            arquivo = request.files.get("arquivo")
            if arquivo and arquivo.filename:
                try:
                    texto = arquivo.read().decode("utf-8-sig")
                except UnicodeDecodeError:
                    erro = ("O arquivo não está em UTF-8 — salve-o de novo "
                            "nesse formato antes de enviar.")
            else:
                token = re.sub(r"[^0-9a-f]", "",
                               request.form.get("token_arquivo", ""))[:32]
                guardado = (_pasta_importacoes_pendentes() / f"{token}.json"
                            if token else None)
                if guardado and guardado.is_file():
                    texto = guardado.read_text(encoding="utf-8")
                else:
                    texto = request.form.get("texto", "")
            if not erro and not texto.strip():
                erro = "Escolha o arquivo .json antes de clicar."
            if not erro:
                try:
                    if o_que == "fila":
                        with db.transaction() as con:
                            fila = IMPP.para_rascunhos(
                                con, texto, agora=agora(), por=usuario_nome())
                        audit("RCPN_IMPORTAR_PRE_CADASTROS", "rascunhos_de_tela",
                              None, {"criados": len(fila["criados"]),
                                     "recusados": len(fila["recusados"]),
                                     "de_onde_veio": fila["de_onde_veio"]})
                        if token:
                            (_pasta_importacoes_pendentes()
                             / f"{token}.json").unlink(missing_ok=True)
                        com_trava = sum(1 for c in fila["criados"] if c["travas"])
                        flash(f"{len(fila['criados'])} pré-cadastro(s) na fila de "
                              f"rascunhos"
                              + (f"; {com_trava} com dado a arrumar antes de "
                                 f"lavrar" if com_trava else "")
                              + (f"; {len(fila['ja_na_fila'])} já estavam lá"
                                 if fila["ja_na_fila"] else "")
                              + ". Abra cada um, confira com o declarante e "
                                "lavre.", "success")
                        return redirect(url_for("rascunhos"))
                    with db.connect() as con:
                        previa = IMPP.previa_da_fila(con, texto, agora=agora())
                    pasta = _pasta_importacoes_pendentes()
                    token = uuid.uuid4().hex
                    (pasta / f"{token}.json").write_text(texto, encoding="utf-8")
                    _limpar_importacoes_pendentes_antigas(pasta)
                except IMPP.ImportacaoError as e:
                    erro = str(e)
        import rc_assento as RC_I
        return render_template(
            "rcpn_importar.html", previa=previa, erro=erro, token=token,
            especies=[(e, RC_I.NOME_DA_ESPECIE.get(e, e))
                      for e in RC_I.PAPEIS_DA_ESPECIE])

    @app.route("/rcpn/importar/manual-das-partes")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_importar_manual():
        with db.connect() as con:
            texto = IMPP.manual_das_partes(con)
        nome = f"manual-registro-civil-partes-{db.now()[:10]}.md"
        return Response(
            texto.encode("utf-8"), mimetype="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    @app.route("/rcpn/importar/modelo/<especie>")
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_importar_modelo(especie):
        try:
            with db.connect() as con:
                texto = IMPP.modelo_rcpn(con, especie)
        except IMPP.ImportacaoError as e:
            flash(str(e), "danger")
            return redirect(url_for("rcpn_importar"))
        nome = f"modelo-{especie.lower()}.json"
        return Response(
            texto.encode("utf-8"), mimetype="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'})



    # ---------------------- instrumento de protesto (art. 20 / art. 22)

    @app.route("/protesto/instrumentos")
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_instrumentos():
        """Fila dos protestos lavrados sem instrumento. Só LÊ."""
        with db.connect() as con:
            fila = PI.a_entregar(con)
            quadro = PI.contagens(con)
            emitidos = banco(con).ler(
                """SELECT i.id, i.numero, i.ano, i.emitido_em, i.titulo_id,
                          t.protocolo, d.assinado_em, d.assinado_por_nome
                     FROM pt_instrumentos i
                     LEFT JOIN pt_titulos t ON t.id = i.titulo_id
                     LEFT JOIN as_documentos d
                            ON d.entidade = 'pt_instrumentos'
                           AND d.entidade_id = i.id
                    ORDER BY i.id DESC LIMIT 30""")
        return render_template(
            "protesto_instrumentos.html", fila=fila, quadro=quadro,
            emitidos=emitidos)

    @app.route("/protesto/<int:titulo_id>/instrumento", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_instrumento_emitir(titulo_id: int):
        """Emite o instrumento do título. ESCREVE — sem upload à Central."""
        s = sv()
        serventia = (s.get("unit_name") or "").strip() or "Serventia"
        try:
            with db.transaction() as con:
                try:
                    import modelos_da_casa as MODELOS
                    modelo = MODELOS.corpo_de(con, "PT_INSTRUMENTO_PROTESTO") or None
                except Exception:                    # noqa: BLE001 — padrão
                    modelo = None
                r = PI.emitir(
                    con, titulo_id, serventia=serventia, agora=agora(),
                    modelo=modelo, usuario=usuario_nome())
        except PI.InstrumentoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_instrumentos"))
        audit("PROTESTO_INSTRUMENTO", "pt_instrumentos", r.get("id"),
              {"titulo_id": titulo_id, "numero": r.get("numero"),
               "ano": r.get("ano")})
        flash(
            f"Instrumento {r.get('numero')}/{r.get('ano')} emitido. "
            f"Ele entrou na fila de assinatura da casa.", "success")
        # O PAPEL SAI LOGO: emitir e não ter o que imprimir era o defeito.
        return redirect(url_for("protesto_instrumento_odt",
                                instrumento_id=r["id"]))

    @app.route("/protesto/instrumentos/<int:instrumento_id>/odt")
    @login_required
    def protesto_instrumento_odt(instrumento_id: int):
        """O INSTRUMENTO DE PROTESTO EM PAPEL — que até 14/10/2026 não existia.

        Cabeçalho da casa, o teor congelado na emissão, o selo do ato de
        protesto, a data do protesto, a linha de assinatura do tabelião e o
        sha256 de conferência. O teor não se remonta: é o que foi para a fila
        de assinatura.
        """
        ins, arquivo = _odt_do_instrumento(instrumento_id)
        audit("PROTESTO_INSTRUMENTO_ODT", "pt_instrumentos", instrumento_id,
              {"numero": ins["numero"], "ano": ins["ano"]})
        return IMPW.resposta_do_papel(
            arquivo, nome=f"instrumento-{ins['numero']}-{ins['ano']}",
            get_setting=db.get_setting,
            voltar_para=url_for("protesto_titulo", titulo_id=ins["titulo_id"]))

    @app.route("/protesto/instrumentos/<int:instrumento_id>/assinar",
               methods=["POST"])
    # 21/10/2026: «assinar instrumento de protesto pode permitir escreventes
    # autorizadas» — era ("ADMIN"). A auxiliar fica de fora pela função
    # (`modulos_ligados.FUNCOES_DE_FORA`), antes desta guarda.
    @roles_required("ADMIN", "MANAGER", "USER")
    def protesto_instrumento_assinar(instrumento_id: int):
        """Assina o instrumento com o A3 do oficial. ESCREVE.

        O papel é o MESMO da impressão (`_odt_do_instrumento`), virado PDF; o
        serviço local de assinatura (porta 8766, aberto pelo oficial na sessão
        dele) assina PELO REPOSITÓRIO DO WINDOWS — o caminho dos sites, medido
        em 15/10/2026 — e devolve o PKCS#7 com o PDF dentro, o formato dos
        instrumentos que esta casa mandou à CENPROT. **O PIN não passa pelo
        sistema**: a janela do próprio token o pede ao oficial.
        """
        import assinar_com_a3 as A3
        import impressao_pdf as IMPPDF
        volta = destino_interno(request.form.get("voltar"), url_for("protesto_instrumentos"))
        try:
            ins, odt = _odt_do_instrumento(instrumento_id)
            pdf = IMPPDF.pdf_de_odt(
                odt, nome=f"instrumento-{ins['numero']}-{ins['ano']}",
                get_setting=db.get_setting)
            resposta = A3.assinar_pdf_pelo_windows(pdf)
            cms = resposta.get("cms_b64")
            if not cms:
                raise PI.InstrumentoError(
                    "O serviço de assinatura não devolveu o arquivo assinado.")
            import base64 as _b64
            with db.transaction() as con:
                r = PI.guardar_assinatura(
                    con, instrumento_id, pdf=pdf, p7s=_b64.b64decode(cms),
                    pasta_de_arquivos=pasta_dos_arquivos(), agora=agora(),
                    usuario=usuario_nome())
        except (A3.AssinarComA3Error, IMPPDF.PdfError,
                PI.InstrumentoError) as erro:
            flash(str(erro), "danger")
            return redirect(volta)
        except OSError:
            flash("O serviço de assinatura A3 não respondeu. Abra o serviço "
                  "(a3_servico_local) nesta máquina, com o token plugado, e "
                  "tente de novo.", "danger")
            return redirect(volta)
        audit("PROTESTO_INSTRUMENTO_ASSINADO", "pt_instrumentos",
              instrumento_id, {"assinado_por": r["assinado_por"]})
        flash(f"Instrumento {r['numero']}/{r['ano']} assinado por "
              f"{r['assinado_por'] or 'certificado sem nome legível'}.",
              "success")
        return redirect(volta)

    def _odt_do_instrumento(instrumento_id: int):
        """O `.odt` do instrumento — UM papel só, para imprimir e para
        assinar (15/10/2026: dois papéis divergiriam, e a assinatura valeria
        sobre um documento diferente do que se imprime)."""
        import protesto_pecas as PECAS
        with db.connect() as con:
            ins = PI.instrumento(con, instrumento_id)
            if not ins:
                abort(404)
            ato_id = ins.get("ato_id")
            etiqueta = (AS.etiqueta_do_ato(con, "pt_atos", int(ato_id), "")
                        if ato_id else "")
            m = PECAS.rotulos(con, "PT_MOLDURAS")
        s = sv()
        from datetime import date as _date
        corpo = ins.get("corpo") or {}
        data_ato = str(((corpo.get("protesto") or {}).get("data_ato")) or "")[:10]
        try:
            quando = data_por_extenso(_date.fromisoformat(data_ato))
        except (TypeError, ValueError):
            quando = data_ato
        from html import escape as _esc
        html = (f'<p align="center"><b>{m("instrumento_titulo")}</b></p>'
                f'<p align="center">'
                f'{m("instrumento_numero", numero=ins["numero"], ano=ins["ano"])}</p><p></p>'
                f'<p>{_esc(ins["teor"])}</p><p></p>'
                f'<p>{m("local_e_data", cidade=s.get("ri_cidade", ""), uf=s.get("ri_uf", ""), data=quando)}</p>'
                f'<p></p><p></p>'
                f'<p align="center">_________________________________</p>'
                f'<p align="center">{s["serventia_titular"]}</p>'
                f'<p align="center">{s["serventia_titulo"]}</p><p></p>'
                f'<p><font size="8">'
                f'{m("instrumento_autenticidade", numero=ins["numero"], ano=ins["ano"], emitido_em=ins.get("emitido_em") or "", hash=ins.get("hash_instrumento") or "")}'
                f'</font></p>')
        frag_do_selo, imagens_do_selo = RODT.carimbo_da_certidao_odf(etiqueta)
        cab_odf, cab_imgs = RODT.cabecalho_certidao_completo_odf(s)
        todas = dict(cab_imgs or {})
        todas.update(imagens_do_selo or {})
        arquivo = gerar_odt(html_para_odf(html) + frag_do_selo,
                            titulo=f"Instrumento {ins['numero']}/{ins['ano']}",
                            cabecalho_odf=cab_odf, imagens=todas or None,
                            cabecalho_altura_min="2.0cm",
                            cabecalho_margem_baixo="0.25cm",
                            cabecalho_borda=False)
        return ins, arquivo

    # ------------- trazer o protesto do E-Oficio (carga + atalhos)
    #
    # Espelho focado da carga de atribuicoes, no menu do Protesto: a chave
    # CENPROT do acervo (`strChaveUnicaCENPROT`) passa a entrar junto, e os
    # leitores que ja existem (XML, remessa, desistencia, imagens) ficam a
    # um clique — sem inventar layout.

    @app.route("/protesto/importar-eoficio", methods=["GET", "POST"])
    @roles_required("ADMIN")
    def protesto_importar_eoficio():
        """Trazer do E-Ofício ao vivo o Protesto, com a chave CENPROT.

        Sempre puxa `tbAvisoProtesto` + `tbPessoa` do MSSQL `bdCartorio`
        (instância SERVER) para o acervo sqlite e só então roda a carga.
        O snapshot velho sozinho não basta — título novo (ex.: 141352) só
        existe ao vivo.
        """
        resultado = None
        sync_ao_vivo = None
        if request.method == "POST":
            quais = request.form.getlist("quais") or ["protesto"]
            # AO VIVO ANTES DA CARGA — sem fallback silencioso para o snapshot.
            try:
                sync_ao_vivo = EO_VIVO.atualizar_protesto_ao_vivo(
                    acervo_no_disco())
            except EO_VIVO.EoVivoError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("protesto_importar_eoficio"))
            try:
                acervo = AC.abrir_acervo(acervo_no_disco())
            except AC.CargaError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("protesto_importar_eoficio"))
            try:
                with db.transaction() as con:
                    resultado = AC.carregar_tudo(
                        con, acervo, agora=agora(), quais=quais)
            except AC.CargaError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("protesto_importar_eoficio"))
            finally:
                acervo.close()
            audit("PROTESTO_CARGA_EOFICIO", "ACERVO", None, {
                "carga": resultado, "ao_vivo": sync_ao_vivo,
            })
            entraram = sum(
                r.get("inseridos", 0) for r in resultado.values()
                if isinstance(r, dict))
            avisos_vivos = (sync_ao_vivo or {}).get(
                "tabelas_aplicadas", {}).get("tbAvisoProtesto")
            flash(
                f"Carga ao vivo concluída: {entraram} registro(s) novo(s)"
                + (f" (E-Ofício ao vivo trouxe {avisos_vivos} aviso(s))."
                   if avisos_vivos is not None else ".")
                + " Confira o quadro abaixo — o que foi rejeitado está com o "
                + "motivo.", "success")

        with db.connect() as con:
            bd = banco(con)
            total = int(bd.valor(
                "SELECT COUNT(*) n FROM pt_titulos"))
            com_chave = int(bd.valor(
                """SELECT COUNT(*) n FROM pt_titulos
                    WHERE TRIM(COALESCE(chave_cenprot,'')) <> ''"""
            ))
            chaves = [
                r["chave_cenprot"] for r in bd.ler(
                    """SELECT chave_cenprot FROM pt_titulos
                        WHERE TRIM(COALESCE(chave_cenprot,'')) <> ''
                        ORDER BY id""")
            ]
        ipdigital = PCEN.casar_ipdigital_por_chave(chaves, pastas=PCEN.pastas_ipdigital(
            banco=db.db_path, archive_root=db.get_setting("archive_root", "")))
        pastas = {
            "cra": str(PDC.do_eoficio("CRA", banco=db.db_path,
                                      archive_root=db.get_setting("archive_root", ""))),
            "cra_remessa": str(PDC.do_eoficio("CRA", "Remessa", banco=db.db_path,
                                              archive_root=db.get_setting("archive_root", ""))),
            "ipdigital": [str(x) for x in PCEN.pastas_ipdigital(
                banco=db.db_path, archive_root=db.get_setting("archive_root", ""))],
        }
        return render_template(
            "protesto_importar_eoficio.html",
            resultado=resultado,
            sync_ao_vivo=sync_ao_vivo,
            contagens={
                "titulos": total,
                "com_chave": com_chave,
                "sem_chave": total - com_chave,
            },
            cargas=AC.TITULO_DA_CARGA,
            tem_acervo=acervo_no_disco().exists(),
            caminho_acervo=str(acervo_no_disco()),
            pastas=pastas,
            ipdigital=ipdigital,
        )

    @app.route("/atribuicoes/importar", methods=["GET", "POST"])
    @roles_required("ADMIN")
    def atribuicoes_importar():
        """Trazer do E-Ofício o acervo das quatro atribuições novas."""
        resultado = None
        if request.method == "POST":
            quais = request.form.getlist("quais") or None
            # Protesto nesta tela tambem vem ao vivo: titulo novo so existe
            # no MSSQL. As demais atribuicoes seguem o snapshot do acervo.
            if quais is None or "protesto" in quais:
                try:
                    EO_VIVO.atualizar_protesto_ao_vivo(acervo_no_disco())
                except EO_VIVO.EoVivoError as erro:
                    flash(str(erro), "danger")
                    return redirect(url_for("atribuicoes_importar"))
            try:
                acervo = AC.abrir_acervo(acervo_no_disco())
            except AC.CargaError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("atribuicoes_importar"))
            try:
                with db.transaction() as con:
                    resultado = AC.carregar_tudo(con, acervo, agora=agora(),
                                                 quais=quais)
            except AC.CargaError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("atribuicoes_importar"))
            finally:
                acervo.close()
            # `audit` abre transacao propria: FORA do `with`, como no resto
            # da casa.
            audit("ATRIBUICOES_CARGA", "ACERVO", None, resultado)
            entraram = sum(r.get("inseridos", 0) for r in resultado.values())
            flash(f"Carga concluída: {entraram} registro(s) novo(s). "
                  f"Confira o quadro abaixo — o que foi rejeitado está com o "
                  f"motivo.", "success")

        with db.connect() as con:
            contagens = {
                nome: int(banco(con).valor(
                    f"SELECT COUNT(*) n FROM {p['tabela']}"))
                for nome, p in PAINEIS.items()}
        # AS CAIXINHAS SAEM DA LISTA DE CARGAS, e nao da lista de telas.
        # Ate 27/08/2026 saiam de `PAINEIS`, e o Livro 3, que ali se chama
        # `livro3` e na carga se chama `registro_auxiliar`, derrubava a carga
        # inteira. As duas cargas novas — papel e selos — nao tinham caixinha.
        return render_template("atrib_importar.html", resultado=resultado,
                               contagens=contagens, paineis=PAINEIS,
                               cargas=AC.TITULO_DA_CARGA,
                               tem_acervo=acervo_no_disco().exists(),
                               caminho_acervo=str(acervo_no_disco()))
