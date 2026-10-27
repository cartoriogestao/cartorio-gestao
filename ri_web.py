"""
Registro de Imoveis - rotas do modulo.

Registrado a partir de create_app(), recebendo os decoradores e utilitarios
que ja existem no sistema, para nao duplicar autenticacao nem auditoria.
"""
from __future__ import annotations
from certidao_texto import sem_linha_de_assinatura_a_mao

import hashlib
import base64
import json
import math
import mimetypes
import re
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from storage import nome_simples, save_upload
import html_sem_script as HSS

import importar_padrao as IMPP
import impressao_web as IMPW
from flask import (Response, abort, flash, redirect, render_template,
                   request, session, url_for)

import ato_selado as AS
from bd_nativo import ERROS_DO_BANCO, banco
# O SELO DE BUSCA QUE VAI JUNTO COM A CERTIDÃO — pedido do oficial, 15/10/2026.
import buscas as BU
import certidao_folhas as CFOLHAS
import selador_config as SELCFG
import cancelamento_certidao as CANC
import fraude as FR
import papel_seguranca as PP

from ri_modelos_atos import (pendencias as pendencias_modelo,
                             MODELOS as MODELOS_ATOS, abas_do_modelo, campos_do_modelo,
                             por_codigo as modelo_por_codigo, preencher as preencher_modelo,
                             por_preencher as por_preencher_do_modelo)
import caixa_depositos as DEP
from caixa_schema import centavos, reais
import notas_doi as NDOI
import ri_doi as RDOI
import onr_carga as OCG
import ri_fichas_do_disco as RFD
import ri_imagens as RIMG
import ri_digitalizacao as RDIGI
import ri_indicador_lancamentos as RILANC
from ri_ctp import (codigo_ibge_da_casa,
                    FORMA_PAGAMENTO, MOTIVO_SEM_NI,
                    TIPO_IMOVEL as TIPO_IMOVEL_CTP, TIPO_OPERACAO,
                    TIPO_PARTE_TRANSACIONADA, conferir, gerar_carga, montar_registro,
                    nome_arquivo as nome_ctp, operacao_sugerida)
from ri_doc import (conferir as conferir_doc, resumo as resumo_doc,
                    teor_html as teor_html_doc)
from ri_doc_extrair import extrair as extrair_doc
from ri_naturezas import nomes as nomes_natureza
from serventia import (dados as dados_serventia, mascarar_documento,
                       mascarar_email, mascarar_telefone, mascarar_texto)
from ri_onr import (TIPO_IMOVEL_ONR, gerar_indicador_pessoal, gerar_indicador_real,
                    nome_arquivo)
from ri_odt import (MIOLO_DA_CERTIDAO,
                    bloco_selo_html, bloco_selo_odf,
                    carimbo_da_certidao_odf, png_do_qr_do_selo,
                    carimbo_compacto_html, carimbo_compacto_odf,
                    carimbos_do_html_para_odf,
                    sem_espaco_de_assinatura_da_ficha,
                    carimbo_do_selo_odf, carimbos_do_ato,
                    gerar_odt, html_para_odf, rotulo_ato, teor_sem_cabecalho_do_ato, natureza_titulo_sem_rotulo,
                    separar_atos, texto_para_html, texto_para_odf,
                    html_em_texto_corrido, SEPARADOR_DE_ATO_HTML,
                    html_com_destaque_rotulo_ato,
                    ato_sem_espaco_antes_do_fecho, anexar_fecho_ao_ato)
import ri_cnib as CNIB
# O VOCABULARIO DAS LEITURAS MORA NO ATUALIZADOR, e se le de la em vez de
# repetir os textos aqui: situacao que existe em dois lugares vira duas
# situacoes no dia em que uma das duas mudar.
import cnib_atualizador as CNIBATZ
import modelos_da_casa as MODELOS
import ri_documentos as RDOC
import notas_selo as NSELO
import caixa_protocolo as CXPROT
import pastas_da_casa as PDC
import contato_do_cliente as CONTATO
import emolumentos as EMOL
import ri_minuta as RIMIN
import ri_lavrar_teor as RITEOR
import ri_numeros_do_teor as NUMT
import ri_revisao as RV
import ri_onus as RIONUS
import ri_onus_ia as RONIA
import revisao_transcricao as RTRANS
# A CADEIA DOMINIAL E A VINTENÁRIA — a régua de quais atos entram mora em
# `ri_dominial` (a mesma família de `ri_onus`). Reconstituída em 14/10/2026: o
# que a 3.6.233/234 ligou aqui em 28/09 se perdeu nos pacotes seguintes.
import ri_dominial as RIDOM
import ri_certidao_negativa as RINEG
import ri_prenotacao_prazo as PRAZO
import onr_acompanhamento as ACOMP  # o andamento no ONR (26/10/2026)
import ri_pedidos as PED
import ri_busca_acervo as BUSCA  # busca em texto livre no teor (26/10/2026)
import ri_situacao_juridica as SITJ  # o resumo da situacao juridica (26/10/2026)
import ri_nota_devolutiva as RND
import ri_rascunho as RASC
import ri_cnm as CNM
import ri_correcoes as RC
import ri_expurgo as EXP
import ra_registro as RA3
from seguranca_web import PRATICA  # M2 (LX11): o AUDITOR vê e não grava
# O número que a tela mandou (LD10; mora em `seguranca_web` desde o LD13).
from seguranca_web import (DIGITOS_DE_UM_NUMERO,  # noqa: F401 — `ri_web.` nos testes
                           PAGINA_MAIS_ALTA, numero_digitado)
import seguranca_web as SEGWEB  # B2 (LX11): exceção inesperada não vai para a tela
from ri_schema import (
    PRAZO_PRENOTACAO,
    TIPOS_CERTIDAO,
    ROTULOS_CERTIDAO_RI,
    VALIDADE_CERTIDAO_DIAS,
    hash_certidao,
    PRAZO_PRENOTACAO_REURB,
    ROTULO_TIPO_FICHA,
    TIPO_FICHA as RI_TIPO_FICHA,
    SITUACOES as RI_SITUACOES,
    matricula_de_acervo,
    consultar_cnib,
    normalizar_busca,
    dias_uteis_entre,
    ler_feriados_locais,
    soma_dias_uteis,
    hash_ato,
    norm_livro,
    so_digitos,
    valida_cpf_cnpj,
    verifica_cadeia,
)

QUALIF_RESUMO = ("nome completo, nacionalidade, estado civil e regime de bens, "
                 "profissao, domicilio e CPF/CNPJ")

POR_PAGINA = 50


class MoldeSemMarcador(MODELOS.ModeloError):
    """O molde da certidão salvo sem o marcador do miolo (relato #75).

    É a ÚNICA recusa de modelo que vai inteira à tela da certidão: a frase é
    de `conferir_marcadores`, escrita para o balcão, e diz o que repor. O
    resto do `ModeloError` que `corpo_certidao` pode levantar — o padrão que
    não está na base, a base que precisa do PostgreSQL — leva o nome do
    schema, o caminho do arquivo e a variável de ambiente: é da casa, e vai
    ao log com a frase genérica (regra B2 do LX11; LX22B2 #1). Subclasse, e
    não `ModeloError` puro, para o `except` da rota separar as duas.
    """


class CancelamentoNaoSeDesfaz(ValueError):
    """A averbação de cancelamento sem selo não pôde ser desfeita (LD03).

    Tem selo, não é a última da ficha ou tem dinheiro no caixa — as três
    recusas de `ri_minuta.voltar_do_ato`. A rota diz as duas coisas: o selo
    não saiu E o cancelamento ficou de pé.
    """


# `_qr_colado` FOI APAGADA EM 14/09/2026, e não desligada.
#
#   Ela validava a imagem que o escrevente colava com Ctrl+V no campo do selo.
#   Com o selador automático no ato, os dois campos que a chamavam saíram da
#   tela — e função pronta sem chamador é, neste projeto, a arma que alguém
#   religa depois sem saber por que existia: já aconteceu cinco vezes.
#
#   O QUE ELA GUARDAVA NÃO SE PERDEU: as colunas `selo_qr*` continuam no
#   esquema e a ficha continua desenhando o que houver nelas — hoje, nada, em
#   1.245 atos e 1.701 matrículas.

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")


UF_EXTENSO = {
    "MA": "Maranhão", "PA": "Pará", "TO": "Tocantins", "PI": "Piauí", "CE": "Ceará",
    "BA": "Bahia", "GO": "Goiás", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
    "SP": "São Paulo", "RJ": "Rio de Janeiro", "MG": "Minas Gerais", "DF": "Distrito Federal",
}


def _imovel_e_rural(valor) -> bool:
    return str(valor or "").strip().upper() in ("R", "RURAL")


def _cib_normalizado(valor) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _cib_valido(valor) -> bool:
    return len(_cib_normalizado(valor)) == 8


def _exige_cib(rural_urbano, *, tipo_ficha=None) -> bool:
    if str(tipo_ficha or "").upper() == "ACERVO":
        return False
    return _imovel_e_rural(rural_urbano)


def _cib_dispensado(numero, lista) -> bool:
    """HOTFIX-2026-10-13-05 (escrevente, 13/10/2026, mat. 4022 vinda do
    encerramento da 1196): imóvel sem CIB. `settings.cib_dispensado_matriculas`
    lista os números («4022» ou JSON ["4022"]) em que o CIB fica opcional; as
    demais continuam exigindo."""
    nums = set(re.findall(r"\d+", str(lista or "")))
    alvo = re.sub(r"\D", "", str(numero or ""))
    return bool(alvo) and alvo in nums


def _mensagem_cib_obrigatorio() -> str:
    return (
        "Matricula de imovel rural exige o CIB (Cadastro Imobiliario "
        "Brasileiro) — oito digitos. Informe na ficha antes de gravar."
    )


def data_por_extenso(d) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def fecho_de_quem_praticou(cidade: str, uf: str, data_iso: str | None,
                           teor: str | None, nome: str | None = None,
                           titulo: str | None = None,
                           tratamento: str | None = None, *,
                           lido: dict | None = None) -> str:
    """Monta o "Cidade Exemplo/MA, data. Dou fe. ..." de um ato. Só monta.

    O TEXTO SAIU DAQUI — LF06B (19/10/2026). A frase mora na base dos
    padroes (`RI_FECHO_DO_ATO`, e `RI_FECHO_DO_ATO_SEM_TITULO` quando o
    cadastro nao traz a funcao), e a casa a edita na tela de Modelos. A
    REGRA continua aqui: sem data ou sem nome nao ha fecho, e teor que ja
    diz «dou fe» nao o repete. `lido` e o que a ficha leu UMA vez
    (`ri_frases.ler`, ajuste da casa → padrao); sem ele sai o padrao.

    UMA REGRA PARA OS DOIS LIVROS — LH13, 21/10/2026. Morava dentro das rotas
    (`registrar_rotas.fecho_do_ato`, que continua chamando esta). Saiu para
    cá porque a ficha do Livro 3 (`ra_ficha_odt`) passou a fechar cada ato
    como o Livro 2 — o oficial, «15 a»: CN-MA art. 458, «todo
    registro/averbação deve ser datado e subscrito».

    DE ONDE VEM O NOME
        Do proprio ato, gravado na hora da lavratura. Nao se deduz por
        periodo. A serventia teve, ao longo dos anos, delegatarios,
        substitutos, interinos e escreventes que se alternaram e se
        misturaram no mesmo intervalo — deduzir pela data acertaria as
        vezes e erraria as outras, sem avisar qual foi qual.

    E O ACERVO?
        Nao precisa: em 1.197 dos 1.239 atos herdados, e em 1.450 das
        1.507 matriculas, o fecho com o nome de quem praticou ja esta
        escrito dentro do proprio teor. Ele sai na impressao porque o teor
        sai. Nos 3% restantes o ato sai sem fecho, que e o certo: melhor
        faltar o nome do que atribuir o ato a quem nao o praticou.
    """
    import ri_frases
    if not data_iso or not nome:
        return ""
    if teor and re.search(r"dou\s+f[ée]", teor[:20000], re.I):
        return ""
    try:
        extenso = data_por_extenso(date.fromisoformat(data_iso))
    except (TypeError, ValueError):
        return ""
    artigo = "A" if (tratamento or "O").upper().startswith("A") else "O"
    chave = "RI_FECHO_DO_ATO" if titulo else "RI_FECHO_DO_ATO_SEM_TITULO"
    modelo = (lido or {}).get(chave) or ri_frases.texto(chave)
    return ri_frases.montar(modelo, cidade=cidade, uf=uf, data_extenso=extenso,
                            artigo=artigo, titulo=titulo, nome=nome)


# NAO RESSELAR O ACERVO — HOTFIX-2026-10-09-08 (09/10/2026). Depois que o
#   «Selar este ato» passou a aparecer em todo ato sem `selo_texto` (09-07),
#   os atos do acervo — selados no sistema anterior, com o selo no razão
#   (sd_selos, inclusive o texto gravado da CONSULTA PÚBLICA TJMA) ou só
#   citado no teor — apareciam como pendência de selo. Selar de novo é selo
#   em duplicidade. Devolve (codigo, etiqueta) ou None.
_RE_SELO_NO_TEOR = re.compile(r"[A-Z]{6}\s?\d{6}\s?[A-Z0-9]{14,18}")
_RE_SELO_GERAL = re.compile(r"SELO\s+GERAL", re.I)


def motivo_ja_selado(ato, n_selos_no_razao: int = 0):
    def _v(k):
        try:
            return ato[k]
        except (KeyError, IndexError):
            return None
    if n_selos_no_razao:
        return ("RAZAO", "Já selado (acervo)")
    teor = re.sub(r"<[^>]+>", "", str(_v("teor") or ""))
    if _RE_SELO_NO_TEOR.search(teor.upper()) or _RE_SELO_GERAL.search(teor):
        return ("TEOR", "Selo citado no teor")
    if int(_v("acervo") or 0) == 1 or str(_v("origem") or "MANUAL").upper() != "MANUAL":
        return ("ACERVO", "Já selado (acervo)")
    return None


# O MODELO DO ENCERRAMENTO — HOTFIX-2026-10-08-08 (Beatriz, 08/10/2026).
#
#   «Encerrar matrícula» lavrava sozinho um teor de duas linhas
#   («ENCERRAMENTO DESTA MATRÍCULA. MOTIVO: …»), sem deixar ver, conferir nem
#   escrever o ato, sem item de selo e sem gratuidade — e nem todo encerramento
#   é igual. O botão agora abre o PRÓPRIO formulário de lavrar, com «Este ato
#   encerra a matrícula? = Sim» e um destes modelos no texto, que é só
#   sugestão: tudo se edita, e o trecho «PREENCHER…» que sobrar recusa a
#   lavratura (no livro sairia literalmente assim).

# HOTFIX-2026-10-09-06 — O ROTULO DO CARIMBO VEM DO PROPRIO SELO (Beatriz,
# 09/10/2026, mat. 1196). Os selos antigos do acervo, conferidos um a um na
# consulta publica do TJMA, entraram no razao vinculados ao ato que os cita:
# o R-2/1.196 tem o selo de PRENOTACAO e o de REGISTRO. Rotulando so pelo tipo
# do ato, a prenotacao sairia «SELO DE REGISTRO 1/2». O prefixo do codigo
# (PRENOT, ARQUIV, MATRIC) diz o que o selo e; os demais seguem o tipo do ato,
# numerados entre si como antes. A prenotacao vem primeiro, como no papel.
_ROTULO_POR_PREFIXO = {"PRENOT": "SELO DE PRENOTAÇÃO",
                       "ARQUIV": "SELO DE ARQUIVAMENTO",
                       "MATRIC": "SELO DE ABERTURA"}
_RE_PREFIXO_DO_SELO = re.compile(r"\b([A-Z]{6})\d{6}[A-Z0-9]{16}\b")


def selos_do_ato_rotulados(tipo, etiquetas) -> list:
    """[(etiqueta, rotulo)] na ordem do papel. So calcula."""
    base = "SELO DE REGISTRO" if tipo == "R" else "SELO DE AVERBAÇÃO"
    lista = []
    for et in etiquetas or []:
        m = _RE_PREFIXO_DO_SELO.search(str(et or "").upper())
        lista.append((et, _ROTULO_POR_PREFIXO.get(m.group(1)) if m else None))
    lista.sort(key=lambda x: 0 if x[1] == "SELO DE PRENOTAÇÃO" else 1)
    comuns = [i for i, (_, r) in enumerate(lista) if r is None]
    fora = []
    for i, (et, r) in enumerate(lista):
        if r is None:
            r = base if len(comuns) == 1 else f"{base} {comuns.index(i) + 1}/{len(comuns)}"
        fora.append((et, r))
    return fora


MARCA_A_PREENCHER = "«PREENCHER"


_MARCA_DO_ENVIO = re.compile(r"[0-9a-f]{32}")


def _marca_do_envio(veio) -> str:
    """A marca da tela «Preencher o modelo»: a que veio no formulário, ou uma
    nova quando a tela abre. Só calcula.

    Ela entra na `origem_chave` da minuta (`_guardar_a_minuta_do_modelo`), e
    por isso só se aceita no formato que se sorteia aqui — texto livre do
    formulário não vira chave de minuta nenhuma.
    """
    marca = str(veio or "").strip().lower()
    return marca if _MARCA_DO_ENVIO.fullmatch(marca) else secrets.token_hex(16)


def _numero_da_matricula_por_extenso_de_pontos(numero) -> str:
    s = str(numero or "").strip()
    return f"{int(s):,}".replace(",", ".") if s.isdigit() else s


def _livro_da_matricula(m) -> str:
    livro = str(m.get("livro") or "").strip()
    if (m.get("livro_norm") or "") == "2" or livro in ("", "2"):
        return "2 – Registro Geral"
    return livro.replace("-", " – ", 1) if "-" in livro else livro


def modelos_de_encerramento(m, numero_ato: int, data_iso: str, quem,
                            cidade: str = "", uf: str = "MA", *,
                            con=None) -> list[dict]:
    """Os modelos de teor do encerramento. Só monta texto; não grava nada.

    O TEXTO SAIU DAQUI — LF06B (19/10/2026): os cinco teores e os três fechos
    são papéis do catálogo (`modelos_padrao/ri/RI_ENCERRAMENTO_*.txt`), e a
    casa os edita na tela de Modelos. A REGRA ficou aqui: qual fecho entra
    (com título, sem título, sem quem assina), o número do ato e da matrícula
    e os rótulos da tela. O «PREENCHER» vai literal no texto; `MARCA_A_PREENCHER`
    continua aqui porque é ela que recusa a lavratura do trecho que sobrou.
    Sem `con`, sai o padrão da base.
    """
    import ri_frases as FRASES

    num = _numero_da_matricula_por_extenso_de_pontos(m.get("numero"))
    livro = _livro_da_matricula(m)
    ato = f"AV-{int(numero_ato):02d}/{num}"
    try:
        d = date.fromisoformat(str(data_iso)[:10])
    except (TypeError, ValueError):
        d = date.today()
    quando = f"{d.day:02d} de {MESES[d.month - 1]} de {d.year}"
    nome, titulo, artigo = (list(quem or ()) + [None, None, None])[:3]
    lugar = {"cidade": cidade, "uf": uf, "data": quando}
    if nome and titulo:
        fecho = FRASES.frase("RI_ENCERRAMENTO_FECHO", con, artigo=(artigo or "O"),
                             titulo=titulo, nome=nome, **lugar)
    elif nome:
        fecho = FRASES.frase("RI_ENCERRAMENTO_FECHO_SEM_TITULO", con, nome=nome,
                             **lugar)
    else:
        fecho = FRASES.frase("RI_ENCERRAMENTO_FECHO_SEM_NOME", con, **lugar)
    claros = {"ato": ato, "numero": num, "livro": livro, "fecho": fecho}
    return [
        {"codigo": "TECNICA",
         "natureza": "Encerramento da matrícula por mudança da técnica de escrituração e remissão à nova matrícula",
         "rotulo": "Mudança da técnica de escrituração (remissão à nova matrícula)",
         "motivo": "Mudança da técnica de escrituração, com remissão à nova matrícula",
         "teor": FRASES.frase("RI_ENCERRAMENTO_TECNICA", con, **claros)},
        {"codigo": "DESMEMBRAMENTO",
         "natureza": "Encerramento da matrícula por desmembramento",
         "rotulo": "Desmembramento total (áreas em novas matrículas)",
         "motivo": "Desmembramento total do imóvel em novas matrículas",
         "teor": FRASES.frase("RI_ENCERRAMENTO_DESMEMBRAMENTO", con, **claros)},
        {"codigo": "UNIFICACAO",
         "natureza": "Encerramento da matrícula por unificação",
         "rotulo": "Unificação / fusão com outro(s) imóvel(is)",
         "motivo": "Unificação do imóvel com outro(s), em nova matrícula",
         "teor": FRASES.frase("RI_ENCERRAMENTO_UNIFICACAO", con, **claros)},
        {"codigo": "CIRCUNSCRICAO",
         "natureza": "Encerramento da matrícula por transferência de circunscrição",
         "rotulo": "Transferência para outra circunscrição / serventia",
         "motivo": "Imóvel passou a pertencer a outra circunscrição imobiliária",
         "teor": FRASES.frase("RI_ENCERRAMENTO_CIRCUNSCRICAO", con, **claros)},
        {"codigo": "LIVRE",
         "natureza": "Encerramento de matrícula",
         "rotulo": "Outro motivo (texto livre)",
         "motivo": "",
         "teor": FRASES.frase("RI_ENCERRAMENTO_LIVRE", con, **claros)},
    ]


# ------------------------------------------------------------- a busca
#
# DUAS REGUAS, E QUEM DECIDE QUAL VALE E O QUE SE DIGITOU — decisao do oficial
# em 15/09/2026, sobre o relato #55 do balcao («pesquisando a matricula 3110
# encontrou a 3602»). Medido na producao antes da correcao:
#
#   · NUMERO (da matricula e o CNM) e DOCUMENTO: EXATOS. Numero nao tem
#     «parecido», e o «contem» de antes devolvia 1.198 fichas para uma busca
#     por «1» — 782 por dentro do numero, 877 por dentro do CNM e 460 por
#     dentro de um CPF. E a 3602 aparecia na busca por 3110 porque quatro
#     daqueles digitos estao no CPF de uma parte dela.
#   · ENDERECO e NOME: por TRECHO, que e como se procura um imovel e uma
#     pessoa. O nome pelo NORMALIZADO, e nao pelo texto cru: esta tela
#     comparava `p.nome` enquanto a tela vizinha (Indicador Pessoal) ja
#     comparava `p.nome_norm` — duas reguas na mesma familia de telas.
#     «rubens dantas machado», em minusculas, achava ZERO; passa a achar 2.
#     Das 3.992 partes, 557 tem acento no nome e 71% nao tem documento — o
#     nome e, para a maior parte delas, o unico caminho ate a ficha.
#
# A PONTUACAO NAO DECIDE NADA, e ela nunca decide: «3.110» e «3110» sao o
# mesmo numero, e o CNM se grava com mascara (`000000.2.0003236-22`). Quem
# digita cola da tela ou do papel, e exigir dele a mesma pontuacao que o banco
# usa seria esconder a ficha. O que NAO se tolera e o pedaco: «314» nao acha a
# 3140, e «3110» nao acha o CPF de ninguem.


def _numero_digitado(busca: str) -> str | None:
    """A forma numerica do que se digitou — ou None quando nao e numero.

    «2Q» NAO e numero, e por isso devolve None: tirar as letras daria «2», e
    quem procura o livro 2 acharia a ficha 2.
    """
    digitos = so_digitos(busca)
    if not digitos:
        return None
    # So e numero se o que sobra, tirando a pontuacao que se digita (ponto de
    # milhar, traco de CPF, barra e espaco), sao os proprios digitos.
    return digitos if re.sub(r"[.\-/\s]", "", busca).isdigit() else None


def _cnm_da_casa(digitos: str) -> str:
    """O CNM como esta casa o grava: `000000.2.0003236-22`.

    Medido em 15/09/2026: os 1.659 CNMs do acervo tem todos esta forma
    (6+1+7+2). Quem cola o numero do sistema ou do ONR, com ou sem mascara,
    chega ao mesmo lugar; o que nao chega e o pedaco dele.
    """
    if len(digitos) == 16:
        return f"{digitos[:6]}.{digitos[6]}.{digitos[7:14]}-{digitos[14:]}"
    return digitos


def _condicao_de_busca_da_matricula(busca: str) -> tuple[str, list]:
    """O SQL da caixa de busca da lista de matriculas, e os parametros dele."""
    digitos = _numero_digitado(busca)
    dentro_da_parte = ["p.nome_norm ILIKE %s"]
    params = [f"%{busca}%", f"%{normalizar_busca(busca)}%"]
    if digitos:
        dentro_da_parte.append("p.documento_numero = %s")
        params.append(digitos)
    condicoes = ["m.logradouro ILIKE %s",
                 "EXISTS (SELECT 1 FROM ri_partes p WHERE p.matricula_id = m.id"
                 " AND (" + " OR ".join(dentro_da_parte) + "))"]
    if digitos:
        condicoes += ["m.numero = %s", "m.cnm = %s"]
        params += [digitos, _cnm_da_casa(digitos)]
    return "(" + " OR ".join(condicoes) + ")", params


# O teor vem do TX Text Control como XHTML. Renderizamos o corpo, mas nunca
# script/style/eventos: e conteudo herdado de outro sistema.
_BLOCOS = re.compile(r"(?is)<(script|style|iframe|object|embed)[^>]*>.*?</\1\s*>")
_TAGS_SOLTAS = re.compile(r"(?is)</?(script|style|iframe|object|embed|link|meta)[^>]*>")
_EVENTOS = re.compile(r"(?is)\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)")
_JS_URL = re.compile(r"(?is)(href|src)\s*=\s*([\"'])\s*javascript:[^\"']*\2")
_CORPO = re.compile(r"(?is)<body[^>]*>(.*)</body>")


def teor_seguro(teor: str | None, formato: str | None) -> str:
    """Devolve o teor pronto para exibir, sem executar nada.

    Texto corrido na tela (Beatriz 24/09/2026, mat. 4001): teor OCR
    com um <p> por linha deixava a ficha ilegível. Sem número da
    matrícula aqui, só se colapsa o excesso de parágrafos.
    """
    if not teor:
        return ""
    if (formato or "texto") != "html":
        from markupsafe import escape
        return f"<pre class='teor-texto'>{escape(teor)}</pre>"
    corpo = _CORPO.search(teor)
    html = corpo.group(1) if corpo else teor
    html = _BLOCOS.sub(" ", html)
    html = _TAGS_SOLTAS.sub(" ", html)
    html = _EVENTOS.sub(" ", html)
    html = _JS_URL.sub(r"\1=\2#\2", html)
    # Colapsa chuva de <p> do OCR na tela da ficha.
    if html.lower().count("<p") >= 4:
        from ri_odt import html_em_texto_corrido
        html = html_em_texto_corrido(html, None)
    # AS EXPRESSÕES DE CIMA NÃO BASTAVAM (LS02, 19/10/2026): `<svg/onload=…>`
    # e `<img src=x/onerror=…>` passavam, porque o `_EVENTOS` procura espaço
    # antes do `on`; `href=javascript:` sem aspas também. O teor do acervo
    # entra pela importação, que o balcão dispara com a pasta que quiser.
    # A última palavra é do filtro que lê o HTML de verdade.
    return HSS.limpar(html)


def procurar_exportacoes(limite: int = 8) -> list[dict]:
    """Localiza pastas de exportacao nas contas da maquina.

    O servidor roda como SYSTEM, cuja pasta pessoal e
    C:\\Windows\\system32\\config\\systemprofile - onde nunca havera exportacao.
    Por isso a busca varre os perfis de usuario em vez de partir de Path.home().
    """
    achadas: list[dict] = []
    raizes: list[Path] = []
    for base in (Path("C:/Users"), Path("D:/Users")):
        if base.is_dir():
            try:
                raizes += [p for p in base.iterdir() if p.is_dir()]
            except OSError:
                continue
    for perfil in raizes:
        for sub in ("Downloads", "Desktop", "Documents", "Documentos"):
            pasta = perfil / sub
            if not pasta.is_dir():
                continue
            try:
                for cand in pasta.iterdir():
                    if not cand.is_dir():
                        continue
                    marcador = cand / "matriculas.jsonl"
                    if marcador.exists():
                        achadas.append({
                            "caminho": str(cand),
                            "arquivos": sum(1 for _ in cand.glob("*.jsonl")),
                            "quando": datetime.fromtimestamp(
                                marcador.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
                        })
                        if len(achadas) >= limite:
                            return achadas
            except OSError:
                continue
    return achadas


def procurar_arquivos(nome: str, limite: int = 8) -> list[Path]:
    """Procura um arquivo pelas pastas de trabalho das contas da maquina.

    POR QUE ESTA FUNCAO EXISTE
        `procurar_exportacoes` devolve DICIONARIOS (caminho, arquivos, quando)
        para alimentar a tela de escolha, e so enxerga subpastas que tenham
        `matriculas.jsonl`. Eu a reaproveitei em tres lugares como se
        devolvesse caminhos, e os tres quebravam com
        "expected str, bytes or os.PathLike object, not dict".

        Aqui a busca e outra: procura UM arquivo pelo nome, tanto solto na
        pasta de trabalho quanto dentro de uma subpasta. E o que serve para o
        matriculas_doc.jsonl, que fica solto no Downloads, e para o
        dom_servico.jsonl, que fica dentro de EXPORT_CAIXA_EOFICIO.

    POR QUE DESCE MAIS DE UM NIVEL
        A primeira versao olhava a pasta de trabalho e UMA subpasta. Funcionou
        enquanto as exportacoes ficavam soltas em `Downloads\\EXPORT_NOTAS_EOFICIO`.

        Quando a pasta Downloads foi organizada e elas passaram para
        `Downloads\\CartorioGestao\\MIGRACAO\\EXPORT_NOTAS_EOFICIO`, ficaram a
        dois niveis — e a tela de importacao parou de achar sozinha, sem dizer
        por que. Arrumar a casa quebrou a busca, que e o tipo de estrago que
        so aparece na proxima vez que alguem precisa da funcao.

        Agora desce ate quatro niveis, pulando o que nao interessa. Quatro
        chega para `CartorioGestao\\MIGRACAO\\EXPORT_X\\arquivo.jsonl` e nao
        varre a maquina inteira.
    """
    IGNORAR = {"__pycache__", ".git", "node_modules", "AppData", ".venv",
               "runtime", "backups"}

    def _nuvem(nome: str) -> bool:
        # Pasta de serviço de nuvem (sincronizada, às vezes «sob demanda»):
        # varrê-la baixaria os arquivos. Reconhecida pelo nome, de qualquer
        # serviço, sem o código saber qual a serventia usa.
        n = nome.lower()
        return "drive" in n or "dropbox" in n

    def procurar(pasta: Path, fundo: int) -> list[Path]:
        saida: list[Path] = []
        try:
            alvo = pasta / nome
            if alvo.exists():
                saida.append(alvo)
                if len(saida) >= limite:
                    return saida
            if fundo <= 0:
                return saida
            for cand in pasta.iterdir():
                if not cand.is_dir() or cand.name in IGNORAR or _nuvem(cand.name) or cand.name.startswith("."):
                    continue
                saida += procurar(cand, fundo - 1)
                if len(saida) >= limite:
                    return saida[:limite]
        except OSError:
            pass
        return saida

    achados: list[Path] = []
    perfis: list[Path] = []
    for base in (Path("C:/Users"), Path("D:/Users")):
        if base.is_dir():
            try:
                perfis += [p for p in base.iterdir() if p.is_dir()]
            except OSError:
                continue
    for perfil in perfis:
        for sub in ("Downloads", "Desktop", "Documents", "Documentos"):
            pasta = perfil / sub
            if not pasta.is_dir():
                continue
            achados += procurar(pasta, 4)
            if len(achados) >= limite:
                return achados[:limite]
    return achados


# A SERIE DAS MATRICULAS. Uma so — o Livro 2 do Registro de Imoveis.
#
#   Os `2-A`, `2-C`, `2-S` do acervo sao VOLUMES de papel, e nao series: os
#   numeros se entrelacam entre eles porque a sequencia e da serventia. Ver o
#   comentario em `ri_nova_matricula`.
SERIE_DA_MATRICULA = "2"

# `MODELO_PRENOTACAO` — o texto de fábrica do papel RI_PRENOTACAO — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/ri/RI_PRENOTACAO.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.



def prenotacoes_abertas_da_matricula(
        con, matricula_id: int, matricula_numero: str | None) -> list[dict]:
    """Prenotações com situacao ABERTO ligadas à matrícula. Só lê.

    Liga por três caminhos (sem inventar vínculo):
      1. `ri_protocolos.matricula_id`
      2. `ri_protocolos.matricula_numero` (texto igual ao número da ficha)
      3. número de protocolo que aparece em `ri_atos.protocolo` desta
         matrícula — caso medido na 4.019/protocolo 11.546: o ato traz o
         número e `ri_protocolos.matricula_id` aponta para outra ficha do
         mesmo título.

    Deduplica por id do protocolo. Ordena por data_prenotacao, numero.
    """
    mid = int(matricula_id)
    num = str(matricula_numero or "").strip()
    por_id: dict[int, dict] = {}

    def _guardar(row) -> None:
        if not row:
            return
        d = dict(row)
        pid = int(d["id"])
        por_id.setdefault(pid, d)

    bd = banco(con)
    rows = bd.ler(
        """SELECT id, numero, data_prenotacao, data_limite, situacao,
                  natureza_titulo, objeto, matricula_id, matricula_numero
             FROM ri_protocolos
            WHERE situacao='ABERTO'
              AND (matricula_id=%s
                   OR (%s != '' AND CAST(matricula_numero AS TEXT)=%s))
            ORDER BY data_prenotacao, numero""",
        (mid, num, num),
    )
    for r in rows:
        _guardar(r)

    # Protocolos citados nos atos desta matrícula (ainda ABERTO).
    atos_proto = bd.ler(
        """SELECT DISTINCT protocolo FROM ri_atos
            WHERE matricula_id=%s
              AND protocolo IS NOT NULL
              AND TRIM(CAST(protocolo AS TEXT)) != ''
            ORDER BY protocolo""",
        (mid,),
    )
    digitos: list[str] = []
    textos: list[str] = []
    for a in atos_proto:
        bruto = str(a["protocolo"] or "").strip()
        if not bruto:
            continue
        textos.append(bruto)
        dig = "".join(ch for ch in bruto if ch.isdigit())
        if dig:
            digitos.append(dig)
    if textos or digitos:
        # Monta OR por igualdade textual / só-dígitos.
        partes = []
        params: list = []
        for t in textos:
            partes.append("CAST(numero AS TEXT)=%s")
            params.append(t)
        for d in digitos:
            partes.append("REPLACE(CAST(numero AS TEXT), '.', '')=%s")
            params.append(d)
        sql = (
            """SELECT id, numero, data_prenotacao, data_limite, situacao,
                      natureza_titulo, objeto, matricula_id, matricula_numero
                 FROM ri_protocolos
                WHERE situacao='ABERTO' AND ("""
            + " OR ".join(partes)
            + ") ORDER BY data_prenotacao, numero"
        )
        for r in bd.ler(sql, params):
            _guardar(r)

    lista = list(por_id.values())
    lista.sort(key=lambda p: (
        str(p.get("data_prenotacao") or ""),
        str(p.get("numero") or ""),
    ))
    return lista


def clausula_html_prenotacoes_abertas(
        prenotacoes: list[dict], *, fmt_date=str, con=None) -> str:
    """HTML do fecho sobre protocolo/prenotação em aberto. Só calcula.

    Redação no padrão da casa («CERTIFICO ainda que…»), espelhando
    Protesto/RCPN/RCPJ. Afirma existência OU inexistência — nunca omite.
    Lei 6.015/1973 (prenotação / prioridade) e Provimento CNJ 149/2023
    (Código Nacional de Normas do Foro Extrajudicial).

    O TEXTO SAIU DAQUI — LF06B (19/10/2026): cada frase é papel do catálogo
    (`modelos_padrao/ri/RI_PRENOTACOES_ABERTAS_*.txt`), e a casa a edita na
    tela de Modelos. A REGRA ficou aqui: há ou não há, um ou vários, e qual
    dado do protocolo entra na lista. Os dados entram já escapados para HTML.
    Sem `con`, sai o padrão da base.
    """
    from xml.sax.saxutils import escape

    import ri_frases as FRASES

    if not prenotacoes:
        return FRASES.frase("RI_PRENOTACOES_ABERTAS_NAO_HA", con)
    itens = []
    for p in prenotacoes:
        numero = escape(str(p.get("numero") or "").strip())
        data = fmt_date(p.get("data_prenotacao")) if p.get("data_prenotacao") else ""
        pedacos = [FRASES.frase("RI_PRENOTACOES_ABERTAS_ITEM_PROTOCOLO", con,
                                numero=numero)]
        if data:
            pedacos.append(FRASES.frase("RI_PRENOTACOES_ABERTAS_ITEM_DATA", con,
                                        data=escape(str(data))))
        nat = str(p.get("natureza_titulo") or "").strip()
        if nat:
            pedacos.append(FRASES.frase("RI_PRENOTACOES_ABERTAS_ITEM_NATUREZA", con,
                                        natureza=escape(nat)))
        obj = str(p.get("objeto") or "").strip()
        if obj:
            pedacos.append(FRASES.frase("RI_PRENOTACOES_ABERTAS_ITEM_OBJETO", con,
                                        objeto=escape(obj)))
        itens.append(", ".join(pedacos))
    lista = "; ".join(itens)
    if len(prenotacoes) == 1:
        return FRASES.frase("RI_PRENOTACOES_ABERTAS_HA_UMA", con, lista=lista)
    return FRASES.frase("RI_PRENOTACOES_ABERTAS_HA_VARIAS", con, lista=lista)



def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    """Pendura as rotas do RI no app ja construido."""

    # Vocabulario do SAUIN disponivel em qualquer tela: e o mesmo nome que o
    # selo eletronico reconhece, e nao adianta uma tela oferecer e outra nao.
    app.jinja_env.globals["NATUREZAS_SAUIN"] = nomes_natureza()
    # O campo da busca da certidão (15/10/2026) se monta na tela — a mesma
    # função que `atribuicoes_web` registra, para o RI não depender da ordem
    # em que os dois módulos sobem.
    app.jinja_env.globals["busca_da_certidao"] = BU.para_a_tela

    def _busca_da_certidao_do_ri(form) -> str | None:
        """O item de busca que a tela da certidão do RI mandou. Só LÊ.

        Sem `busca_formulario` é chamada de antes do campo existir, e não há
        busca — a forma de `onus_formulario`. Com ele, vazio se recusa.

        **O PROTOCOLO VEM PRIMEIRO** — resposta do oficial, 15/10/2026: «se o
        protocolo do pedido já traz um item de busca, vale ele». O protocolo
        da certidão do RI é o número digitado ou escolhido na lista.
        """
        with db.connect() as con:
            do_protocolo = BU.busca_do_protocolo(
                con, form.get("protocolo"), "IMOVEL")
        if do_protocolo:
            return do_protocolo
        if (form.get("busca_formulario") or "").strip() != "1":
            return None
        return BU.escolher("IMOVEL", form.get("busca_item"))

    def _selar_a_busca_da_certidao_do_ri(*, certidao_id: int,
                                          busca: str | None,
                                          nome: str | None,
                                          documento: str | None,
                                          matricula: str | None,
                                          isento: bool,
                                          motivo_isencao: str | None) -> str:
        """O selo da BUSCA da certidão do RI. FALA COM A REDE.

        Pedido do oficial, 15/10/2026. **SELO PRÓPRIO, por
        `/selo/imovel/atos-em-geral`**, que é o caminho dos 27 selos de busca
        do RI no acervo de 2022 a 2025 (os 5 de 2020 saíram pelo da
        certidão). Vai DEPOIS da certidão, no mesmo protocolo, como lá foi;
        a gratuidade é a da certidão.

        A BUSCA QUE NÃO SAI NÃO DESFAZ A CERTIDÃO — a regra do item da folha
        acrescida, logo acima: a certidão tem o seu selo, e a tela diz o que
        faltou.
        """
        if not busca or not BU.vira_selo(busca):
            return ""
        caminho = BU.CAMINHO_DO_SELO_DA_BUSCA["IMOVEL"]
        nome_parte = str(nome or "").strip() or (
            f"MATRICULA {str(matricula or '').strip()}".strip())
        try:
            envelope = BU.envelope_da_busca(
                codigo=busca, escrevente=app.extensions["usuario_nome"](),
                versao_tabela=AS.versao_da_tabela_de_custas(
                    caminho, db.get_setting("selo_tabela_custas_em", "")),
                nome=nome_parte, documento=documento,
                isento=isento, motivo_isencao=motivo_isencao)
        except BU.BuscaError as erro:
            return f" A busca {busca} ficou SEM SELO: {erro}"
        r = AS.selar_o_ato_lavrado(
            db, Path(app.config["DATA_DIR"]), tabela="ri_certidoes",
            ato_id=certidao_id, tipo="BUSCA", atribuicao="IMOVEL",
            agora=datetime.now().isoformat(timespec="seconds"),
            cns=db.get_setting("ri_cns", ""),
            usuario=app.extensions["usuario_nome"](),
            dados=envelope, caminho=caminho,
            referencia=f"ri_certidoes:{int(certidao_id)}:{busca}")
        if r["selado"]:
            return f" Busca {busca}: selo {r['numero']}."
        return f" A busca {busca} ficou SEM SELO: {r['motivo']}"

    def _pedir_os_selos_da_certidao_do_ri(*, certidao_id: int, tipo: str,
                                          folhas, requerente,
                                          requerente_documento,
                                          matricula: str, isento: bool,
                                          motivo_isencao) -> dict:
        """Os selos da certidão do RI, item por item. FALA COM A REDE.

        UM LUGAR SÓ PARA A EMISSÃO, A NEGATIVA E O «SELAR DE NOVO» — 22/10/2026.
        A 3.7.0 trouxe a trava do selo pago, e a certidão passou a poder ficar
        «aguardando cobertura» (protocolo e pagamento). Quem pede o selo de novo
        tem de mandar **as mesmas referências** da emissão — `ri_certidoes:ID`
        no item base e `ri_certidoes:ID:código` na folha acrescida —, senão o
        SID muda e o aparelho vende um segundo selo para a mesma certidão. Três
        cópias deste laço divergiriam justamente nisso.

        **O ITEM BASE QUE NÃO SAI PARA O LAÇO.** Antes, a folha acrescida era
        pedida mesmo com o item base recusado, e uma certidão podia ficar só
        com o selo da folha — que não existe sozinho.

        Devolve `saiu` (números), `faltou` (motivos) e `aguardando` — True
        quando o item base não saiu só por falta de protocolo ou pagamento, e
        não por recusa do aparelho.
        """
        versao = AS.versao_da_tabela_de_custas(
            "/selo/imovel/certidao",
            db.get_setting("selo_tabela_custas_em", ""))
        if not versao:
            raise AS.AtoError(
                "falta a versão da tabela de custas, em Administrativo → "
                "Configurações (data da tabela em vigor).")
        saiu, faltou, aguardando = [], [], False
        for indice, (codigo_do_item, quantidade) in enumerate(
                AS.itens_da_certidao_do_ri(tipo, folhas)):
            envelope = AS.envelope_da_certidao_do_ri(
                tipo=tipo,
                escrevente=app.extensions["usuario_nome"](),
                versao_tabela=versao,
                quantidade=quantidade,
                codigo_do_item=codigo_do_item,
                requerente=requerente,
                requerente_documento=requerente_documento,
                matricula=matricula,
                isento=isento,
                motivo_isencao=motivo_isencao)
            # **A REFERENCIA DO PRIMEIRO ITEM NAO MUDA**, e e dela que sai o
            # SID: trocar a forma faria o aparelho vender selo novo onde antes
            # devolvia o mesmo. O item da folha acrescida, que e novo, leva a
            # sua propria — uma referencia so para dois itens traria o mesmo
            # selo duas vezes.
            referencia = (f"ri_certidoes:{certidao_id}" if indice == 0
                          else f"ri_certidoes:{certidao_id}:{codigo_do_item}")
            r = AS.selar_o_ato_lavrado(
                db, Path(app.config["DATA_DIR"]),
                tabela="ri_certidoes",
                ato_id=certidao_id, tipo=tipo, atribuicao="IMOVEL",
                agora=datetime.now().isoformat(timespec="seconds"),
                cns=db.get_setting("ri_cns", ""),
                usuario=app.extensions["usuario_nome"](),
                dados=envelope, referencia=referencia)
            if r["selado"]:
                saiu.append(r["numero"])
                continue
            faltou.append(r["motivo"])
            if indice == 0:
                aguardando = bool(r.get("aguardando_cobertura"))
                break
        return {"saiu": saiu, "faltou": faltou, "aguardando": aguardando}

    def _recado_dos_selos_da_certidao(pedido: dict) -> str:
        """A frase da tela sobre os selos pedidos. Só monta texto."""
        saiu, faltou = pedido["saiu"], pedido["faltou"]
        if saiu:
            recado = f" Selo {', '.join(saiu)}."
            if faltou:
                recado += f" ({len(faltou)} item(ns) sem selo: {faltou[0]})"
            return recado
        return f" SEM SELO: {faltou[0] if faltou else ''}"

    def _busca_pedida_na_emissao(certidao_id: int) -> str | None:
        """O código da busca escolhida quando a certidão foi emitida. Só LÊ.

        `ri_certidoes` não tem coluna para a busca: a escolha só ficou na
        auditoria da emissão (`busca` na certidão da ficha, `item_busca` na
        negativa). O «selar de novo» precisa dela para pedir o selo da busca
        com a mesma referência — sem ela, a busca ficaria sem selo calada.
        """
        linha = q1("""SELECT details FROM audit_logs
                       WHERE entity_type='RI_CERTIDAO' AND entity_id=%s
                         AND action IN ('RI_CERTIDAO_EMITIDA',
                                        'RI_CERTIDAO_NEGATIVA_EMITIDA',
                                        'RI_CERTIDAO_POSITIVA_EMITIDA')
                       ORDER BY id DESC LIMIT 1""", (int(certidao_id),))
        if not linha or not linha["details"]:
            return None
        try:
            detalhes = json.loads(linha["details"])
        except (TypeError, ValueError):
            return None
        return (detalhes.get("busca") or detalhes.get("item_busca") or None)

    def _certidoes_aguardando_selo(ids) -> set[int]:
        """Quais destas certidões estão «aguardando cobertura». Só LÊ.

        A lista é da trava do selo pago (`cx_selo_aguardando`, 3.7.0). Sem a
        tabela — instalação sem a trava — nenhuma está esperando.
        """
        ids = [int(i) for i in ids if i is not None]
        if not ids:
            return set()
        with db.connect() as con:
            bd = banco(con)
            if not bd.tem_tabela("cx_selo_aguardando"):
                return set()
            marcas = ",".join(["%s"] * len(ids))
            return {int(r["ato_id"]) for r in bd.ler(
                f"""SELECT ato_id FROM cx_selo_aguardando
                     WHERE tabela='ri_certidoes' AND ato_id IN ({marcas})""",
                ids)}

    def _codigo_base_da_certidao() -> dict:
        """O item base de cada tipo de certidão do RI, a negativa inclusive. Só calcula."""
        return {**AS.CODIGO_DA_CERTIDAO_DO_RI,
                RINEG.TIPO: AS.CODIGO_DA_CERTIDAO_NEGATIVA_DE_IMOVEL,
                RINEG.TIPO_POSITIVA: AS.CODIGO_DA_CERTIDAO_NEGATIVA_DE_IMOVEL}

    def _candidatos_da_certidao_do_ri(con, pedidos=None) -> list[dict]:
        """Os protocolos pagos que a escrevente pode escolher para a certidão. Só LÊ.

        Com `pedidos` (o «Selar» de uma certidão já gravada, folhas contadas),
        a lista é a deles. Sem eles (a ficha, antes de escolher o tipo), são
        os protocolos com o item BASE das duas famílias — 16.24.4 (inteiro
        teor, ônus, cadeia) e 16.24.1 (propriedade, negativa) —, sem repetir.
        """
        if pedidos:
            return AS.candidatos_do_ato(con, tabela="ri_certidoes",
                                        pedidos=pedidos)
        vistos, saida = set(), []
        for base in sorted(set(AS.CODIGO_DA_CERTIDAO_DO_RI.values())):
            for c in AS.candidatos_do_ato(con, tabela="ri_certidoes",
                                          pedidos=[(base, 1)]):
                if c["protocolo_id"] not in vistos:
                    vistos.add(c["protocolo_id"])
                    saida.append(c)
        return saida

    def _atender_o_protocolo_escolhido(form) -> str | None:
        """O protocolo marcado na tela vira o «em atendimento». ESCREVE.

        Devolve a recusa para o balcão, ou None. Vazio não mexe em nada (o
        atendimento que já havia continua). A auditoria vai FORA da transação
        — regra da casa —, com o que `escolher_protocolo_do_selo` devolveu.
        """
        try:
            with db.transaction() as con:
                feito = AS.escolher_protocolo_do_selo(
                    con, usuario=app.extensions["usuario_nome"](),
                    protocolo=form.get("protocolo_selo"), agora=db.now())
        except CXPROT.ProtocoloError as erro:
            return str(erro)
        if feito:
            audit("SELO_PROTOCOLO_EM_ATENDIMENTO", "CX_PROTOCOLO",
                  feito["protocolo_id"], {"numero": feito["numero"]})
        return None

    def _protocolos_do_selo_ri(tabela: str, codigo: str, ri_protocolo_id=None) -> dict:
        """Os protocolos pagos que podem pagar este selo do RI, para a tela. Só LÊ.

        Serve as telas que selam além da certidão — a prenotação (16.1), a
        abertura (16.2), o arquivamento (16.39) e a negativa (16.24.1) —, que
        a desenham com a macro `_protocolo_do_selo.html`. Na prenotação, o
        protocolo de caixa dela (`cx_protocolos.ri_protocolo_id`) vem
        pré-marcado; marcado não é escolhido: a escrevente confirma.
        """
        pedidos = [(codigo, 1)]
        with db.connect() as con:
            bd = banco(con)
            pre = None
            if ri_protocolo_id:
                linha = bd.um("""SELECT id FROM cx_protocolos WHERE ri_protocolo_id=%s
                                  ORDER BY id DESC LIMIT 1""", (int(ri_protocolo_id),))
                pre = linha["id"] if linha else None
            return {"candidatos": AS.candidatos_do_ato(
                        con, tabela=tabela, pedidos=pedidos,
                        pre_marcar_protocolo_id=pre),
                    "atendendo": CXPROT.em_atendimento(
                        bd, app.extensions["usuario_nome"]()),
                    "pedidos": pedidos}

    app.jinja_env.globals["protocolos_do_selo_ri"] = _protocolos_do_selo_ri

    def q(sql, params=()):
        with db.connect() as con:
            return banco(con).ler(sql, params)

    def q1(sql, params=()):
        linhas = q(sql, params)
        return linhas[0] if linhas else None

    def _motivo_da_falha_do_selo(recado: str) -> str | None:
        """Extrai o motivo humano de uma mensagem «SEM SELO». Só LÊ."""
        texto = str(recado or "").strip()
        if not texto:
            return None
        if "SEM SELO:" in texto:
            return texto.split("SEM SELO:", 1)[1].strip() or "falha sem detalhe"
        baixo = texto.lower()
        if "sem selo:" in baixo:
            return texto.split(":", 1)[1].strip() or "falha sem detalhe"
        if "sem selo" in baixo:
            return texto or "falha sem detalhe"
        return None

    # ------------------------------------------------- delegatarios

    def delegatarios(so_ativos: bool = False) -> list[dict]:
        linhas = [dict(r) for r in
                  q("""SELECT * FROM ri_delegatarios
                       ORDER BY CASE cargo WHEN 'TITULAR' THEN 0 WHEN 'SUBSTITUTO' THEN 1
                                           WHEN 'INTERINO' THEN 2 ELSE 3 END,
                                COALESCE(inicio,''), nome""")]
        if so_ativos:
            hoje = date.today().isoformat()
            linhas = [d for d in linhas if not d["fim"] or d["fim"] >= hoje]
        return linhas

    def quem_pode_abrir_matricula() -> list[dict]:
        """Quem pode constar como responsavel por abrir a matricula.

        ORDEM DO OFICIAL EM 16/09/2026: «e preciso que seja possivel escolher
        um escrevente para constar como responsavel por abrir a matricula».
        Ate aqui a lista era so `ri_delegatarios` — tres pessoas —, e quem
        abre ficha no balcao todo dia sao os escreventes.

        SAO DUAS FONTES, E CADA UMA GUARDA O QUE SABE. O delegatario tem
        cargo, titulo e tratamento em `ri_delegatarios`; o escrevente tem
        `users.full_name` e `users.funcao`, que e a funcao na forma da Lei
        8.935/94 e ja e o que sai embaixo da assinatura no resto da casa
        (`usuario_funcao`). **Nao se inventa titulo para ninguem**: o que vai
        ao papel e o que a casa cadastrou.

        O NOME SAI COMO ESTA GRAVADO, e nao em maiusculas. `usuario_nome`
        devolve `full_name` tal e qual — medido — e e ele que ja sai no selo e
        no escrevente do ato; uniformizar aqui faria a ficha discordar do
        resto dos papeis da casa.

        A MESMA PESSOA PODE APARECER NAS DUAS LISTAS, E ISSO FICA A VISTA —
        correcao minha, no mesmo dia, depois de medir contra a producao. Eu
        havia escrito aqui que a deduplicacao resolvia; **nao resolve**, e o
        motivo interessa ao oficial:

            delegatario  MARIO EXEMPLO DOS SANTOS
            usuario      Mario Exemplo dos Santos      <- uma letra de diferenca
            delegatario  BEATRIZ EXEMPLO DE SOUZA
            usuario      Beatriz Santos Araujo Correa <- «de» e acentos

        SO SE COLAPSA O QUE E IGUAL, e nao o que e parecido. Juntar por
        primeiro-e-ultimo nome colapsaria homonimos, e **homonimo e a regra e
        nao a excecao** nesta casa — e a lista aqui decide QUEM ASSINA a
        abertura de um registro. Quem e a mesma pessoa e quem lê; o que o
        sistema faz e dizer de qual cadastro veio cada linha.

        O DELEGATARIO VEM PRIMEIRO na lista, porque e o cadastro do oficio, e
        e dele que sai o titulo registral.
        """
        def chave(nome):
            return " ".join(str(nome or "").split()).upper()

        lista = [{"nome": d["nome"], "titulo": d["titulo"],
                  "tratamento": d["tratamento"], "grupo": "Delegatários"}
                 for d in delegatarios()]
        vistos = {chave(x["nome"]) for x in lista}
        for u in q("""SELECT full_name, funcao FROM users
                       WHERE active=1 AND TRIM(COALESCE(full_name,'')) <> ''
                       ORDER BY full_name"""):
            if chave(u["full_name"]) in vistos:
                continue
            vistos.add(chave(u["full_name"]))
            lista.append({"nome": u["full_name"].strip(),
                          "titulo": (u["funcao"] or "").strip() or None,
                          # O escrevente nao tem tratamento cadastrado, e ele
                          # nao sai no papel desde 16/09 — a assinatura e
                          # «linha NOME, funcao.». Fica `None` em vez de um
                          # «O» ou «A» deduzido da ultima letra do nome.
                          "tratamento": None,
                          "grupo": "Escreventes e auxiliares"})
        return lista

    def fecho_do_ato(cidade: str, uf: str, data_iso: str | None, teor: str | None,
                     nome: str | None = None, titulo: str | None = None,
                     tratamento: str | None = None, *,
                     lido: dict | None = None) -> str:
        """O fecho de um ato da ficha e da certidão do Livro 2. Só monta.

        A REGRA MORA FORA DAS ROTAS desde o LH13 (21/10/2026), em
        `fecho_de_quem_praticou`: a ficha do Livro 3 passou a fechar cada ato
        como o Livro 2 («15 a»), e uma regra escrita duas vezes diverge no
        primeiro conserto. Este nome fica porque é o que a ficha e a certidão
        chamam, e o que o ouro do LF06B (parte D) alcança pelo objeto de código.
        """
        return fecho_de_quem_praticou(cidade, uf, data_iso, teor, nome, titulo,
                                      tratamento, lido=lido)

    def fecho_da_abertura(cidade: str, uf: str, data_iso: str | None,
                          teor: str | None, nome: str | None = None,
                          titulo: str | None = None,
                          tratamento: str | None = None,
                          tipo_ficha: str | None = None, *,
                          lido: dict | None = None) -> dict:
        """O fecho da ABERTURA da matricula, com espaco para assinar.

        A FRASE SAIU DAQUI — LF06B (19/10/2026): «… O referido e verdade e dou
        fe.» mora na base (`RI_FECHO_DA_ABERTURA`) e se edita na tela de
        Modelos. Quando ela entra, e a linha de assinar com o nome e a funcao,
        continuam sendo decididos aqui — a ordem da assinatura e do oficial.
        `lido`: ver `fecho_do_ato`.

        PEDIDO DO OFICIAL EM 16/09/2026: «precisa ter espaco pra quem abriu a
        matricula assinar».

        POR QUE NAO SERVE O `fecho_do_ato`. Ele devolve `""` quando nao sabe o
        nome — e a regra e certa para ATO («melhor faltar o nome do que
        atribuir o ato a quem nao o praticou»). Aqui ela apagaria justamente o
        que ele pediu: **o espaco existe mesmo sem o nome**, porque e nele que
        a pessoa assina e escreve quem e.

            Medido em 16/09: `abertura_fecho` chamava `fecho_do_ato` com
            quatro argumentos — **sem `nome`** —, logo devolvia `""` em toda
            ficha da casa. A linha existia no molde e nunca imprimiu nada.

        A FORMA E A DO DOCUMENTO DA CASA, e nao escolhida por mim. A ficha de
        abertura da 4.016 que o oficial redigiu fecha assim:

            «O referido e verdade e dou fe. A Tabelia/Registradora
             Substituta, ____________________ BEATRIZ EXEMPLO DE SOUZA
             CORREA.»

        — o titulo, a virgula, a linha, o nome. O tratamento («A»/«O») vem de
        `ri_delegatarios.tratamento`, que ja o guarda: deduzi-lo da ultima
        letra da funcao acertaria «Substituta» e erraria «Auxiliar», sem
        avisar qual foi qual.

        DEVOLVE DUAS PARTES, E ELAS CORREM NA MESMA LINHA — 16/09/2026:

            «o cidade exemplo na ficha deve começar logo depois da parte do
             registro anterior, sem espaços desnecessários, e precisa constar
             o usuário que está abrindo a matrícula logo depois, sem pular
             linha. e espaço pra ele assinar na sequência da linha»

          ATE AQUI ERAM TRES PARAGRAFOS: a descricao do imovel, o fecho, uma
          linha em branco, e a assinatura. No papel isso abria quatro linhas
          de vao entre «REGISTRO ANTERIOR» e quem assina — e a ficha da
          serventia corre tudo seguido, como o livro de papel sempre correu.

          **A LINHA EM BRANCO DO `<p></p>` SAIU DAQUI, E NAO DA CASA.** Ela
          nasceu em 31/08 de «mais espaco livre para desenvolver a
          assinatura», que era o pedido do relato #27 sobre a ficha do CARTAO
          DE AUTOGRAFO — outro papel, em que a firma se desenvolve em campo
          proprio. Aqui a assinatura vai sobre a linha de 32 sublinhados, e o
          vao acima dela nao servia a ninguem. **Continuam sendo duas partes**
          porque a frase pode existir sem a assinatura (teor que ja diz «dou
          fe») e a assinatura sem a frase; o molde e que as junta com um
          espaco, em vez de com um paragrafo.

        **O RELATO #79 NAO MUDOU NADA AQUI, E ISSO TAMBEM FOI MEDIDO** —
        17/09/2026. A certidao passou a imprimir o teor das ESTRUTURADAS, e eu
        escrevi, na primeira versao deste conserto, que ela sairia com a
        assinatura em dobro. Fui ler `MODELO_CERTIDAO_PADRAO`: **ele nao
        imprime nem `abertura_fecho` nem `abertura_assinatura`** — fecha com
        «Era o que nela continha.», com o «Dou fe.» da validade e com o bloco
        de quem assina a certidao. Quem as imprime e o molde da FICHA, e so
        ele. O receio era de um papel que nao existe, e deduzi-lo da coluna —
        em vez de ler o molde — foi «dado cru nao e resposta».
        """
        import ri_frases
        # ACERVO ANTERIOR A 4.015 SEGUE O DOCUMENTO IMPORTADO — decisao da
        # serventia em 17/09/2026. Nao se acrescenta selo, fecho, linha de
        # assinatura nem nome de quem abriu: qualquer texto gerado hoje
        # atribuiria uma abertura historica a uma pessoa que nao a praticou.
        if str(tipo_ficha or "").strip().upper() == "ACERVO":
            return {"frase": "", "assinatura": ""}

        # SAO DUAS PERGUNTAS, E EU AS TRATEI COMO UMA — corrigido em
        # 16/09/2026, depois de o oficial dizer «segue sem espasso para quem
        # abriu a matricula assinar».
        #
        #   A primeira versao suprimia **as duas partes** quando o teor ja
        #   dizia «dou fe». Medido na producao no minuto do relato, nas 1.551
        #   fichas com teor:
        #
        #     | dizem «dou fe»                  | 631 |
        #     | tem linha de assinatura         | 333 |
        #     | **dizem «dou fe» e NAO tem linha** | **328** |
        #
        #   Aquelas **328** perdiam o espaco por causa da minha guarda — e a
        #   3.110 e uma delas: o teor dela termina em «Dou fe. Ana Gracia
        #   Almeida Rizzo Fontanela - Oficiala.», sem uma linha para assinar.
        #
        #   «Ja diz dou fe» e «ja tem onde assinar» sao coisas diferentes:
        #   a primeira evita repetir a FRASE, a segunda evita repetir a LINHA.
        #   A 4.016 tem as duas (o documento dela traz a linha e o nome) e por
        #   isso nao ganha nada; a 3.110 tem so a primeira, e ganha a linha.
        # E A GUARDA SO VALE SE O TEOR FOR AO PAPEL — segunda correcao do
        # mesmo relato, em 16/09/2026, e quem me pegou foi o meu proprio
        # teste.
        #
        #   O MOLDE DA FICHA — e so ele — imprime o teor quando a ficha e
        #   ACERVO: `{% if m.tipo_ficha == "ACERVO" and teor_odf %}`
        #   (`MODELO_FICHA_PADRAO`). Medido: **434** fichas sao ESTRUTURADA, e
        #   no papel da FICHA o teor delas nao sai.
        #
        #   A CERTIDAO NAO ENTRA NESTA CONTA, E ISSO FOI CONFERIDO EM
        #   17/09/2026. Ela imprime estes dois pedacos? **NAO.** Fui ler o
        #   molde por causa do relato #79 — o teor das ESTRUTURADAS passou a
        #   sair na certidao, e eu escrevi que ela ganharia a assinatura em
        #   dobro: `MODELO_CERTIDAO_PADRAO` fecha com «Era o que nela
        #   continha.», com o «Dou fe.» da validade e com o bloco de quem
        #   assina a certidao, e nunca chama nem `abertura_fecho` nem
        #   `abertura_assinatura`. A via da digitalizacao monta outro corpo,
        #   `corpo_resumo_digitalizacao`, e tambem nao. Quem as imprime e o
        #   molde da FICHA, e so ele — que e o que a linha de cima ja dizia.
        #
        # EU DISSE AO OFICIAL QUE «A 4.016 JA TEM O ESPACO» E ESTAVA
        #   ERRADO. Ela e ESTRUTURADA: a linha de assinatura que veio no
        #   documento dela esta dentro do teor, e no papel da FICHA o teor
        #   daquela ficha nao chega (`MODELO_FICHA_PADRAO`) — quem o imprime e
        #   a certidao, desde o relato #79. Eu li a coluna e supus que ela
        #   imprimia — «dado cru nao e resposta; a resposta e o que a funcao
        #   devolve».
        # O TEOR SO VAI AO PAPEL DA FICHA QUANDO A FICHA E ACERVO — e a de
        # acervo sai daqui sem fecho nenhum (a saida acima). Logo, hoje, isto
        # e sempre falso, e as duas guardas logo abaixo nao disparam em papel
        # nenhum. Fica escrito assim porque a pergunta que as criou continua
        # valendo se o teor voltar a ser impresso junto com o fecho: quem o
        # fizer, meca de novo antes de contar com elas.
        teor_vai_ao_papel = str(tipo_ficha or "").strip().upper() == "ACERVO"
        ja_diz_dou_fe = bool(
            teor_vai_ao_papel and teor
            and re.search(r"dou\s+f[ée]", teor[:20000], re.I))
        ja_tem_linha = bool(teor_vai_ao_papel and teor
                            and re.search(r"_{8,}", teor))
        frase = ""
        if data_iso and not ja_diz_dou_fe:
            try:
                extenso = data_por_extenso(date.fromisoformat(data_iso))
            except (TypeError, ValueError):
                extenso = None
            if extenso:
                modelo = ((lido or {}).get("RI_FECHO_DA_ABERTURA")
                          or ri_frases.texto("RI_FECHO_DA_ABERTURA"))
                frase = ri_frases.montar(modelo, cidade=cidade, uf=uf,
                                         data_extenso=extenso)
        # A LINHA TEM O TAMANHO DA DO DOCUMENTO DELE — 32 sublinhados,
        # contados no `MATRICULA_4016_FICHA_ABERTURA.docx`.
        if ja_tem_linha:
            # O TEOR JA TRAZ ONDE ASSINAR. Repetir daria duas linhas no mesmo
            # papel, e quem o lesse nao saberia em qual assinar.
            return {"frase": frase, "assinatura": ""}
        linha = "_" * 32
        if nome:
            # A ORDEM E ELE QUEM DECIDE — 16/09/2026: «falta o nome e funcao
            # de quem abriu a matricula logo depois do espaco pra assinar».
            #
            #   ANTES A FUNCAO VINHA NA FRENTE, com artigo — «A Tabeliã
            #   Registradora Substituta, ____ BEATRIZ…» —, que e a forma do
            #   documento da 4.016 que ele mesmo redigiu. Ele pediu o
            #   contrario: primeiro o espaco de assinar, **e logo depois** o
            #   nome e a funcao de quem assina.
            #
            #   E O ARTIGO SAI JUNTO, porque nesta ordem ele nao cabe: «A
            #   Tabelia» antecede a funcao, e a funcao agora vem depois do
            #   nome, entre virgulas. `tratamento` continua sendo lido do
            #   cadastro e nao deduzido da ultima letra da palavra — a regra
            #   nao mudou, mudou onde a funcao aparece.
            atras = f", {titulo}" if titulo else ""
            assinatura = f"{linha} {nome}{atras}."
        else:
            # SEM NOME, SO A LINHA. Quem abriu assina e escreve quem e — e o
            # papel nao afirma que foi quem esta logado hoje.
            assinatura = linha
        return {"frase": frase, "assinatura": assinatura}

    def cnib_referencia():
        """Ate quando a copia local responde, e com quantas ordens.

        **DEIXOU DE SER `MAX(data_pedido)` EM 19/09/2026**, quando o
        atualizador passou a trazer ordem da Central — e a troca e medida, nao
        preferencia:

          a janela da Central filtra pela data da ATIVIDADE, e nao pela do
          pedido. Uma janela de junho/2026 devolveu ordem com `datapedido` de
          2012, porque o que se moveu foi o cancelamento. Pela data do pedido,
          uma leitura de hoje poderia ENVELHECER a base mostrada na ficha — e
          o alerta de copia velha diria o contrario do que aconteceu.

        Quem responde «ate quando» e a ultima leitura que a Central respondeu
        e este sistema entendeu. Enquanto nao houver leitura nenhuma, vale o
        retrato do acervo, que e o que a casa tem.
        """
        linha = q1("SELECT MAX(data_pedido) d, COUNT(*) n FROM ri_cnib_ordens WHERE ativa=1")
        base = linha["d"] if linha else None
        quantas = linha["n"] if linha else 0
        marcas = ",".join(["%s"] * len(CNIBATZ.SITUACOES_QUE_ANDAM))
        leitura = q1(f"""SELECT ate FROM ri_cnib_leituras
                          WHERE situacao IN ({marcas}) AND terminada_em IS NOT NULL
                          ORDER BY ate DESC, id DESC LIMIT 1""",
                     tuple(sorted(CNIBATZ.SITUACOES_QUE_ANDAM)))
        if leitura and leitura["ate"]:
            base = leitura["ate"]
        return base, quantas

    # Quantos dias de atraso a copia local pode ter antes de a tela mudar de
    # tom. Nao ha numero oficial: a CNIB e atualizada continuamente, e por isso
    # QUALQUER copia responde so ate a data dela. Trinta dias e o ponto em que
    # «recente» deixa de ser uma palavra honesta.
    CNIB_DIAS_PARA_AVISAR = 30

    def cnib_idade(base_data) -> int | None:
        """Quantos dias tem a copia local da CNIB. So calcula."""
        try:
            return (date.today() - date.fromisoformat(str(base_data)[:10])).days
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------ lista

    # AS ORDENACOES DA LISTA — relato #64, 15/09/2026.
    #
    # "permitir ordenar por ultimas modificadas ou por ordem numerica (do
    #  numero maior ao menor)" / "permitir organizar e ver ultimos atos
    #  praticados e ultimas matriculas abertas".
    #
    # A FRASE TEM TRES PERGUNTAS DENTRO, e cada uma pede a sua ordem: o que a
    # casa acabou de escrever (`atos`), o que ela abriu por ultimo (`abertura`)
    # e o numero grande (`numero`). A ordem de hoje — a do livro — FICA, e
    # continua sendo a de quem chega sem escolher: e a ordem em que a ficha
    # esta na estante, e quem procura um numero conhecido conta com ela.
    #
    # A ORDEM POR ULTIMO ATO NAO USA `ri_atos.lavrado_em`, e a medicao diz por
    # que: 1.241 dos 1.246 atos tem `lavrado_em` no dia 2026-08-13 — o dia da
    # CARGA. Ordenar por ele poria o acervo inteiro na frente de tudo o que
    # esta casa escreveu depois, que e o contrario do pedido. A data que
    # responde "o que foi praticado por ultimo" e `data_ato`, que e a data do
    # ato — conferida: 1.246 de 1.246 em `AAAA-MM-DD`, e por isso ordena como
    # texto, sem conversao nenhuma.
    #
    # `COALESCE(...,'')` NAO E ENFEITE: ficha sem ato (1.551 das 1.982) e ficha
    # sem data de abertura (277) tem de ir para o FIM da lista, e nao para o
    # comeco. No SQLite o DESC ja as manda para o fim; no Postgres, que e para
    # onde este sistema pode ir um dia, o DESC as traria para a PRIMEIRA linha.
    # Com a string vazia as duas concordam, e a consulta deixa de depender de
    # quem a executa. Na ordem do livro, o `NULLS FIRST` faz o mesmo pela ficha
    # sem livro: o SQLite a punha no comeco, e o PostgreSQL a poria no fim.
    ORDENS_DA_LISTA = {
        "livro": "Ordem do livro",
        "atos": "Últimos atos praticados",
        "abertura": "Últimas matrículas abertas",
        "numero": "Número — do maior ao menor",
    }

    ORDEM_SQL = {
        "livro": ("m.livro_norm NULLS FIRST,"
                  " coalesce(substring(m.numero FROM '^[0-9]+')::bigint, 0),"
                  " m.numero, m.id"),
        "atos": ("COALESCE((SELECT MAX(a.data_ato) FROM ri_atos a"
                 " WHERE a.matricula_id=m.id), '') DESC,"
                 " coalesce(substring(m.numero FROM '^[0-9]+')::bigint, 0) DESC,"
                 " m.numero DESC, m.id DESC"),
        "abertura": ("COALESCE(m.data_abertura, '') DESC,"
                     " coalesce(substring(m.numero FROM '^[0-9]+')::bigint, 0) DESC,"
                     " m.numero DESC, m.id DESC"),
        "numero": ("coalesce(substring(m.numero FROM '^[0-9]+')::bigint, 0) DESC,"
                   " m.numero DESC, m.id DESC"),
    }

    @app.route("/registro-imoveis")
    @login_required
    def ri_matriculas():
        busca = (request.args.get("busca") or "").strip()
        tipo = (request.args.get("tipo") or "").strip()
        livro = (request.args.get("livro") or "").strip()
        ordem = (request.args.get("ordem") or "").strip()
        if ordem not in ORDEM_SQL:
            ordem = "livro"
        # LD13: «abc» no endereço era 500, e a página de 18 dígitos estoura o OFFSET.
        pagina = max(1, numero_digitado(request.args.get("pagina"),
                                        maximo=PAGINA_MAIS_ALTA) or 1)

        onde, params = ["1=1"], []
        if busca:
            condicao, params = _condicao_de_busca_da_matricula(busca)
            onde.append(condicao)
        if tipo in ROTULO_TIPO_FICHA:
            onde.append("m.tipo_ficha = %s")
            params.append(tipo)
        if livro:
            onde.append("m.livro_norm = %s")
            params.append(livro)
        filtro = " AND ".join(onde)

        total = q1(f"SELECT COUNT(*) c FROM ri_matriculas m WHERE {filtro}", params)["c"]
        # ORDENA E PAGINA PELO `id`, E SO DEPOIS BUSCA AS 50 FICHAS INTEIRAS —
        # 15/09/2026, relato do oficial: «atualizei e esta lento».
        #
        #   `CAST(m.numero AS INTEGER)` NAO USA INDICE, entao o SQLite tem de
        #   ordenar a tabela inteira antes de saber quais 50 ficam. Com
        #   `SELECT m.*` ele carrega **todas as colunas de todas as 1.982
        #   fichas** para fazer isso — e `ri_matriculas.teor` guarda **31,8 MB
        #   de texto**. A tela lia 32 MB do disco para mostrar cinquenta linhas.
        #
        #   A subconsulta interna toca so `id`, `livro_norm` e `numero`, que sao
        #   curtos; a de fora busca as 50 linhas cheias. **Medido contra a
        #   producao: 2,37 s a 3,55 s antes, 0,14 s a 0,16 s depois** — e as
        #   duas devolvem as MESMAS fichas, na MESMA ordem, com as mesmas
        #   colunas e contagens (conferido linha a linha).
        #
        #   A ordenacao se escreve duas vezes de proposito: a de dentro decide
        #   quais entram, a de fora garante que elas saiam na ordem certa —
        #   `IN (...)` nao conserva ordem nenhuma. As duas saem do MESMO
        #   dicionario (`ORDEM_SQL`), senao a de dentro e a de fora divergiriam
        #   no dia em que alguem mexesse numa so.
        #
        #   `ultimo_ato` entra no SELECT para a lista PODER SER CONFERIDA: uma
        #   lista ordenada por «ultimos atos praticados» que nao mostra a data
        #   do ultimo ato pede que quem a le acredite. Custa uma consulta por
        #   linha mostrada — cinquenta, nao mil novecentas.
        ordenacao = ORDEM_SQL[ordem]
        rows = q(
            f"""SELECT m.*,
                   (SELECT COUNT(*) FROM ri_atos a WHERE a.matricula_id=m.id) n_atos,
                   (SELECT COUNT(*) FROM ri_partes p WHERE p.matricula_id=m.id) n_partes,
                   (SELECT MAX(a.data_ato) FROM ri_atos a
                     WHERE a.matricula_id=m.id) ultimo_ato,
                   -- HOTFIX-2026-10-09-07: ato lavrado aqui e ainda sem selo
                   -- (o encerramento, quase sempre) -> atalho «Selar» na lista.
                   (SELECT a.id FROM ri_atos a
                     WHERE a.matricula_id=m.id AND a.origem='MANUAL'
                       AND COALESCE(a.selo_texto,'')='' AND COALESCE(a.cancelado,0)=0
                       -- HOTFIX-2026-10-09-08: nao e pendencia se ja tem selo
                       AND COALESCE(a.acervo,0)=0
                       AND NOT EXISTS (SELECT 1 FROM sd_selos s WHERE s.tabela='ri_atos'
                                        AND s.ato_id=a.id AND s.cancelado_em IS NULL)
                       AND UPPER(COALESCE(a.teor,'')) !~ '[A-Z][A-Z][A-Z][A-Z][A-Z][A-Z][0-9][0-9][0-9][0-9][0-9][0-9]'
                       AND UPPER(COALESCE(a.teor,'')) NOT ILIKE '%%SELO GERAL%%'
                     ORDER BY a.id DESC LIMIT 1) ato_sem_selo
                FROM ri_matriculas m
                WHERE m.id IN (
                    SELECT id FROM ri_matriculas m WHERE {filtro}
                     ORDER BY {ordenacao}
                     LIMIT %s OFFSET %s)
                ORDER BY {ordenacao}""",
            params + [POR_PAGINA, (pagina - 1) * POR_PAGINA],
        )
        # O RÓTULO DO ATO SEM SELO («AV-02») se junta em Python — 12/10/2026.
        # Era uma segunda subconsulta com `||` e `printf`, que o teto de
        # portabilidade de ri_web não comporta; o id já vem na primeira.
        ids_sem_selo = [r["ato_sem_selo"] for r in rows if r["ato_sem_selo"]]
        rotulos_sem_selo: dict = {}
        if ids_sem_selo:
            for a in q(f"SELECT id, tipo, numero FROM ri_atos WHERE id IN ({','.join(['%s'] * len(ids_sem_selo))}) ORDER BY id",
                       ids_sem_selo):
                num = a["numero"]
                rotulos_sem_selo[a["id"]] = f"{a['tipo']}-{num:02d}" if isinstance(num, int) else f"{a['tipo']}-{num}"
        livros = q("SELECT livro_norm, COUNT(*) c FROM ri_matriculas GROUP BY livro_norm "
                   "ORDER BY livro_norm NULLS FIRST")
        # COALESCE obrigatorio: em tabela vazia o SUM do SQLite devolve NULL,
        # nao zero, e o template quebraria ao comparar None com inteiro.
        resumo = q1("""SELECT COUNT(*) total,
                          COALESCE(SUM(CASE WHEN tipo_ficha='ACERVO' THEN 1 ELSE 0 END),0)::bigint acervo,
                          COALESCE(SUM(CASE WHEN tipo_ficha='ESTRUTURADA' THEN 1 ELSE 0 END),0)::bigint estruturada,
                          COALESCE(SUM(CASE WHEN conferido=1 THEN 1 ELSE 0 END),0)::bigint conferidas
                       FROM ri_matriculas""")
        return render_template(
            "ri_matriculas.html", rows=rows, total=total, pagina=pagina,
            paginas=max(1, math.ceil(total / POR_PAGINA)), busca=busca, tipo=tipo,
            livro=livro, ordem=ordem, ORDENS=ORDENS_DA_LISTA,
            livros=livros, resumo=resumo, ROTULO=ROTULO_TIPO_FICHA, rotulos_sem_selo=rotulos_sem_selo,
        )

    # ------------------------------------------------------------ ficha

    # O FORMULÁRIO DE LAVRAR, ABERTO PARA ENCERRAR — HOTFIX-2026-10-08-08.
    # «Encerrar matrícula» deixou de ter formulário próprio: abre o de lavrar
    # (texto com prévia, número, selo com item, gratuidade, arquivamento e
    # revisão com IA) já com «encerra = Sim» e o modelo no texto. Só monta a
    # sugestão; quem lavra é a rota de sempre, que encerra no mesmo passo.
    def _pre_encerramento(m, piso, atos):
        if request.args.get("encerrar") != "1" or m.get("encerrada"):
            return None
        if app.extensions["usuario_papel"]() not in ("ADMIN", "MANAGER"):
            return None
        try:
            numero = int((piso or {}).get("proximo") or 0)
        except (TypeError, ValueError, AttributeError):
            numero = 0
        if numero < 1:
            numero = max([int(a["numero"] or 0) for a in atos] or [0]) + 1
        hoje_iso = date.today().isoformat()
        # O TEXTO DOS MODELOS MORA NA BASE (LF06B): com `con`, o ajuste que a
        # casa gravou na tela de Modelos vence o padrao.
        with db.connect() as _c_frases:
            modelos = modelos_de_encerramento(
                m, numero, hoje_iso, quem_pratica_o_ato(),
                cidade=(db.get_setting("ri_cidade", "") or ""),
                uf=(db.get_setting("ri_uf", "") or "MA"), con=_c_frases)
        escolhido = "TECNICA" if m.get("tipo_ficha") == "ACERVO" else "LIVRE"
        mo = next(x for x in modelos if x["codigo"] == escolhido)
        return {"numero": numero, "modelos": modelos, "escolhido": escolhido,
                "teor": mo["teor"], "motivo": mo["motivo"],
                "natureza": mo["natureza"]}


    @app.route("/registro-imoveis/<int:matricula_id>")
    @login_required
    def ri_ficha(matricula_id):
        m = q1("SELECT * FROM ri_matriculas WHERE id=%s", (matricula_id,))
        if not m:
            abort(404)
        m = dict(m)
        # A fronteira numerica prevalece sobre classificacao antiga gravada
        # no banco. Assim uma ficha anterior a 4.015 nunca volta a oferecer
        # selo/responsavel por causa de uma importacao antiga que a marcou
        # como estruturada.
        #
        #   **E ELA E ORDEM DELE, E NAO GUARDA DE PROGRAMADOR** — «regra
        #   informada pela serventia em 17/09/2026: numeros menores que 4.015
        #   sao acervo». Eu a condicionei a existir acervo na casa, em
        #   17/09/2026, e desfiz a ordem sem saber; voltou inteira no mesmo
        #   dia. Ver `tests/test_ri_regra_acervo_4015.py`.
        if matricula_de_acervo(m["numero"]):
            m["tipo_ficha"] = "ACERVO"
        atos = q("""SELECT * FROM ri_atos WHERE matricula_id=%s
                    ORDER BY numero, tipo""", (matricula_id,))
        partes = q("""SELECT * FROM ri_partes WHERE matricula_id=%s
                      ORDER BY proprietario_ativo DESC, nome, id""", (matricula_id,))
        imagens = q("SELECT * FROM ri_imagens WHERE matricula_id=%s "
                    "ORDER BY ordem NULLS FIRST, id", (matricula_id,))
        with db.connect() as _c_cnib:
            cnib_dos_atos = CNIB.consultas_da_matricula(_c_cnib, matricula_id)

        # O CARIMBO DA TELA É O MESMO DO PAPEL — ordem do oficial em
        # 15/09/2026: «preze por esse modelo tanto no html como no odt e pdf,
        # exatamente assim em todos». Antes a ficha imprimia aqui o conteúdo
        # cru de `a.selo_texto`, que guarda o **número** de 28 caracteres, e o
        # resumo de `a.emolumentos` colado com um travessão.
        #
        #   A ETIQUETA VEM DO RAZÃO, pela mesma razão do `.odt`: a coluna do
        #   ato não tem valor nenhum dentro, e sem eles o carimbo não mostra os
        #   emolumentos. A chave é `tabela` MAIS `ato_id` — por `ato_id`
        #   sozinho vem selo de outra atribuição.
        # VARIOS SELOS POR ATO — Beatriz 23/09/2026 (desmembramento 4001):
        # um ato pode ter 16.22.8.1 + 16.5 x2. `setdefault` só guardava o
        # PRIMEIRO; a ficha precisa mostrar todos os carimbos do razão.
        selo_do_ato: dict[int, list[str]] = {}
        if atos:
            lugares = ",".join(["%s"] * len(atos))
            # HOTFIX-2026-10-07-04/selos (Beatriz 08/10/2026, mat. 4019): selo
            # CANCELADO no razão não vai ao carimbo (R-01 saía com 2 selos de
            # registro), e o 16.39 do ato não se repete como «averbação 2/2»
            # — ele já sai no carimbo próprio de arquivamento.
            _arq_do_ato = {int(x["id"]): str(x["selo_arquivamento"] or "").strip()
                           for x in atos}
            for r in q(f"""SELECT ato_id, numero, texto FROM sd_selos
                            WHERE tabela='ri_atos' AND ato_id IN ({lugares})
                              AND cancelado_em IS NULL
                            ORDER BY id""",
                       [int(x["id"]) for x in atos]):
                _arq = _arq_do_ato.get(int(r["ato_id"]))
                if _arq and str(r["numero"] or "").strip() == _arq:
                    continue
                txt = str(r["texto"] or "").strip()
                if txt:
                    selo_do_ato.setdefault(int(r["ato_id"]), []).append(txt)

        # SELO DA PRENOTACAO + SELO DO ATO — 22/09/2026 (substituta):
        # cada ato de RI ligado a um protocolo (ex.: 11539 -> AV-7/8/9 da
        # 1197) leva o carimbo da prenotacao E o do ato lavrado. Sem
        # protocolo, fica so o do ato.
        selo_da_prenotacao: dict[str, str] = {}
        if atos:
            brutos = []
            for a in atos:
                n = str(a["protocolo"] or "").strip()
                dig = "".join(ch for ch in n if ch.isdigit()) if n else ""
                if dig:
                    brutos.append(dig)
            if brutos:
                lugares = ",".join(["%s"] * len(brutos))
                for r in q(
                    f"""SELECT CAST(numero AS TEXT) numero, selo_prenotacao
                          FROM ri_protocolos
                         WHERE REPLACE(CAST(numero AS TEXT), '.', '')
                               IN ({lugares})
                            OR CAST(numero AS TEXT) IN ({lugares})
                         ORDER BY id""",
                    brutos + brutos,
                ):
                    dig = "".join(
                        ch for ch in str(r["numero"] or "") if ch.isdigit())
                    if dig and r["selo_prenotacao"]:
                        selo_da_prenotacao.setdefault(
                            dig, r["selo_prenotacao"])
                nums = list({v for v in selo_da_prenotacao.values() if v})
                etiq: dict[str, str] = {}
                if nums:
                    lugares = ",".join(["%s"] * len(nums))
                    for r in q(
                        f"""SELECT numero, texto FROM sd_selos
                             WHERE numero IN ({lugares})
                             ORDER BY obtido_em, id""",
                        nums,
                    ):
                        etiq.setdefault(r["numero"], r["texto"])
                for dig, num_selo in list(selo_da_prenotacao.items()):
                    selo_da_prenotacao[dig] = (
                        str(etiq.get(num_selo) or "").strip() or num_selo)

        def _digitos_protocolo(a) -> str:
            n = str(a["protocolo"] or "").strip()
            return "".join(ch for ch in n if ch.isdigit()) if n else ""

        def carimbo_da_tela(a) -> str:
            partes = []
            dig = _digitos_protocolo(a)
            pre = selo_da_prenotacao.get(dig) if dig else None
            if pre:
                partes.append(carimbo_compacto_html(
                    pre, rotulo='SELO DE PRENOTAÇÃO'))
            etiquetas = list(selo_do_ato.get(int(a["id"])) or [])
            if not etiquetas:
                um = str(a["selo_texto"] or "").strip()
                if um:
                    etiquetas = [um]
            # HOTFIX-2026-10-09-06: rotulo pelo prefixo do selo.
            for etiqueta, rotulo in selos_do_ato_rotulados(a["tipo"], etiquetas):
                partes.append(carimbo_compacto_html(etiqueta, rotulo=rotulo))
            # Arquivamento 16.39, se gerado neste ato.
            arq_num = str(a["selo_arquivamento"] or "").strip()
            if arq_num:
                arq_et = q1(
                    """SELECT texto FROM sd_selos WHERE numero=%s
                        ORDER BY obtido_em DESC LIMIT 1""", (arq_num,))
                arq_txt = (str((arq_et or {})["texto"] or "").strip()
                           if arq_et else "") or arq_num
                folhas_arq = a["folhas_arquivamento"]
                rot_arq = "SELO DE ARQUIVAMENTO"
                if folhas_arq:
                    rot_arq = f"SELO DE ARQUIVAMENTO ({folhas_arq} fl.)"
                partes.append(carimbo_compacto_html(arq_txt, rotulo=rot_arq))
            return "".join(partes)

        def carimbo_da_abertura() -> str:
            do_razao = q1(
                """SELECT texto FROM sd_selos
                    WHERE tabela='ri_matriculas' AND ato_id=%s
                    ORDER BY obtido_em DESC, id DESC LIMIT 1""", (matricula_id,))
            etiqueta = (str((do_razao or {})["texto"] or "").strip()
                        if do_razao else "") or m["selo_abertura_texto"]
            if not etiqueta:
                return ""
            # O ROTULO ENCURTOU PORQUE A LINHA E UMA SO — medido nos
            # 1.965 selos do RI desta casa: com «SELO DE ABERTURA DA
            # MATRÍCULA» a linha passa dos 16 cm da ficha em 3 deles; com
            # «SELO DE ABERTURA», em 2. E a ficha ja diz de que matricula e.
            return carimbo_compacto_html(
                etiqueta, rotulo="SELO DE ABERTURA")

        cadeia = [dict(a) | {"matricula_numero": m["numero"], "data_ato": a["data_ato"] or ""}
                  for a in atos]
        # HOTFIX-2026-10-09-08: ato que ja tem selo nao vira pendencia de selo.
        _n_razao: dict[int, int] = {}
        if atos:
            for r in q(f"""SELECT ato_id, COUNT(*) n FROM sd_selos
                            WHERE tabela='ri_atos' AND cancelado_em IS NULL
                              AND ato_id IN ({",".join(["%s"] * len(atos))})
                            GROUP BY ato_id""", [int(x["id"]) for x in atos]):
                _n_razao[int(r["ato_id"])] = int(r["n"])
        atos = [dict(a) | {"carimbo": carimbo_da_tela(a),
                           "ja_selado": motivo_ja_selado(a, _n_razao.get(int(a["id"]), 0))}
                for a in atos]
        quebras = {x["id"] for x in verifica_cadeia(cadeia)}

        # O TEOR DA FICHA EM LEITURA — relato #67, 15/09/2026: «precisa
        # atualizar o teor da ficha com os atos recem lavrados».
        #
        # **E ISSO NAO SE FAZ ESCREVENDO NO TEOR**, pela mesma razao que o
        # modulo `ri_numeros_do_teor` nao cria ato a partir do texto: o texto da
        # ficha nao e feito so de atos — nas 429 fichas estruturadas com texto,
        # em 314 delas MAIS DE METADE do teor esta fora de qualquer ato (a
        # descricao do imovel, as confrontacoes) —, e o teor do acervo e o que
        # o E-Oficio gravou. Acrescentar-lhe texto hoje faria a ficha de tela
        # discordar do papel que esta na estante, que e o carimbo que mente.
        #
        # **O QUE FALTAVA ERA A LEITURA, E O RELATO E JUSTO NISSO.** O painel
        # «Teor da ficha» mostrava so o texto gravado, e o ato novo aparecia
        # apenas no cartao de cima — quem lia o teor, que e o que se le para
        # saber o que a ficha diz, nao o encontrava. Agora os atos que o texto
        # ainda nao conta vem DEPOIS dele, uma vez cada.
        #
        # **E OS NUMEROS DESTE PARAGRAFO ENVELHECERAM, E UM DELES ESTAVA
        # ERRADO DESDE QUE NASCEU** — remedido em 18/09/2026, junto com o #71:
        # sao **1.248** atos nesta casa (e nao 1.244) — **1.246** com teor, 2
        # sem texto nenhum —, **531** ja escritos inteiros dentro do teor da
        # ficha e **717** que o teor nao conta, em **291** fichas. E o «todos
        # em ficha estruturada» era o CONTRARIO do medido:
        # **nenhum** dos 531 esta em ficha ESTRUTURADA — as 6 desta casa nao
        # tem um unico ato —, e os 531 sao de ficha **ACERVO**, onde o E-Oficio
        # escrevia o ato dentro do texto da matricula. Quem ler o numero ou a
        # razao sem medir de novo vai repetir os dois erros.
        #
        # O ato sem teor tambem entra: sem texto nao ha o que comparar, e ele
        # ainda tem rotulo, natureza e data para mostrar. Sao 5 fichas nesta
        # casa sem texto nenhum e com ato — e nelas o painel abria vazio.
        fora_do_teor = NUMT.atos_fora_do_teor(m["teor"], atos, matricula=m)
        # O TEXTO DO ATO SAI UMA VEZ SÓ — relato #71, 18/09/2026.
        #
        #   «mostra duas vezes as 3 averbaçoes feitas» — Carla, na tela
        #   `/registro-imoveis/5377` (a matrícula 3.110), em 16/09.
        #
        # **E ela estava certa, medida no HTML que o balcão recebe**: na 3.110
        # os três textos saíam duas vezes cada — uma no painel «Atos», no alto,
        # e outra na seção que o relato #67 criou depois do teor. Medido na
        # produção em 18/09: **291 fichas** e **717 atos** com o texto repetido.
        #
        #   **A CULPA NÃO É DA SEÇÃO DE BAIXO, E SIM DO QUE FICOU EM CIMA.** Em
        #   15/09 o #67 pediu que o ato novo aparecesse na leitura da ficha — que
        #   é o que se lê para saber o que ela diz —, a seção foi criada abaixo do
        #   teor, e o painel do alto continuou como estava. As duas vistas
        #   ficaram, e as duas mostravam o mesmo texto.
        #
        # **O DESENHO ESCOLHIDO PELO OFICIAL EM 18/09: o painel do alto é o
        # ÍNDICE.** Ele fica com o rótulo, a data, os distintivos, o carimbo do
        # selo e os botões (cancelar, selar, expurgar) — porque é ali que se age
        # sobre o ato, e mandar os botões para baixo de um teor de 60 mil
        # caracteres seria escondê-los. O **texto** sai de lá e aparece uma única
        # vez, na sequência do teor — que é a ordem do papel: `ri_odt.
        # MODELO_FICHA_PADRAO` e a certidão de inteiro teor sempre imprimiram
        # cada ato uma vez.
        #
        # `texto_no_teor` é o que o índice precisa saber para dizer ao leitor ONDE
        # ler: dentro do teor (o acervo já o escreveu lá — 531 atos) ou abaixo
        # dele (717). A lista `fora_do_teor` é a MESMA que decide o papel: quem
        # manda o ato ao `.odt` e à certidão lê `teor_vai_ao_papel`.
        sem_texto_em_cima = {a["id"] for a in fora_do_teor}
        for _a in atos:
            _a["texto_no_teor"] = _a["id"] not in sem_texto_em_cima
        for _a in fora_do_teor:
            _a["rotulo"] = rotulo_ato(_a["tipo"], _a["numero"], m["numero"])
            _a["natureza_titulo"] = natureza_titulo_sem_rotulo(
                dict(_a).get("natureza_titulo"), _a["tipo"], _a["numero"], m["numero"])
            # O <h3> ja mostra o rotulo; o teor sob ele nao repete o cabecalho.
            if dict(_a).get("teor"):
                _a["teor"] = teor_sem_cabecalho_do_ato(
                    _a["teor"], _a["tipo"], _a["numero"], m["numero"])

        # Indisponibilidade das partes desta matricula, na copia local da CNIB.
        with db.connect() as con:
            cnib = consultar_cnib(
                con,
                [p["documento_numero"] for p in partes if p["documento_numero"]],
                [p["nome"] for p in partes],
            )
            cnib_pendencias = CNIB.filtrar_pendentes(con, matricula_id, cnib)
            cnib_decisoes = CNIB.decisoes_da_matricula(con, matricula_id)
        base_data, base_n = cnib_referencia()

        protocolos = q("""SELECT * FROM ri_protocolos WHERE matricula_id=%s
                          ORDER BY numero DESC, id DESC""", (matricula_id,))
        # OS PROTOCOLOS ABERTOS, para o ato escolher em vez de digitar.
        #
        #   Ate 28/08/2026 o campo «Protocolo» da lavratura era texto livre, e
        #   `ri_protocolos.ato_id` estava vazio em **784 de 784**. A prenotacao
        #   e o que garante a PRIORIDADE do titulo (Lei 6.015/1973, art. 186):
        #   quando dois titulos disputam o mesmo imovel, a pergunta e qual
        #   prenotacao veio antes **e qual ato saiu dela**. Sem a amarracao, a
        #   segunda metade da pergunta se responde a mao, comparando datas.
        # `id` entrou na lista: os documentos do protocolo se acham por ele, e
        # sem isto a tela estouraria ao montar a lista dos anexos.
        # Inclui a ponte com o caixa (FK) e quantos depositos previos
        # o titulo ja tem — sem inventar join. Em producao a FK pode
        # estar vazia; o deposito e a ponte operacional da casa.
        abertos = q("""SELECT p.id, p.numero, p.data_prenotacao, p.natureza_titulo,
                              p.apresentante,
                              (SELECT c.id FROM cx_protocolos c
                                WHERE c.ri_protocolo_id=p.id
                                  AND c.situacao='ABERTO'
                                ORDER BY c.id DESC LIMIT 1) AS cx_id,
                              (SELECT c.numero FROM cx_protocolos c
                                WHERE c.ri_protocolo_id=p.id
                                  AND c.situacao='ABERTO'
                                ORDER BY c.id DESC LIMIT 1) AS cx_numero,
                              (SELECT COUNT(*) FROM cx_depositos d
                                WHERE d.ri_protocolo_id=p.id) AS depositos_n
                         FROM ri_protocolos p WHERE p.situacao='ABERTO'
                        ORDER BY p.numero DESC, p.id DESC LIMIT 60""")

        audit("RI_FICHA_CONSULTADA", "RI_MATRICULA", matricula_id,
              {"numero": m["numero"], "livro": m["livro_norm"], "cnib": len(cnib)})
        # A LISTA DE ATENCAO PARA FRAUDES, sobre as partes da matricula.
        # Ela vem AO LADO da consulta ao CNIB, que ja roda aqui: sao duas
        # listas diferentes, de fontes diferentes, e nenhuma substitui a outra.
        with db.connect() as _c:
            fraudes = FR.conferir_pessoas(_c, [
                {"nome": x.get("nome"), "documento": x.get("documento_numero"),
                 "papel_no_ato": (x.get("papel") or x.get("qualificacao")
                                  or "parte")}
                for x in map(dict, partes)])
        with db.connect() as _c:
            rascunho = RASC.da_matricula(_c, matricula_id)
            # OS DOCUMENTOS DO PROTOCOLO, PARA QUEM ESTA LAVRANDO — relato #25:
            # «o ato em que se vincula a esse determinado protocolo precisa
            # poder visualizar os documentos anexos ao protocolo, até para
            # facilitar a lavratura do ato».
            #
            # Quem lavra tem o papel na mão e o teor em branco na frente. Ir a
            # outra tela buscar a escritura é largar o que está escrevendo.
            docs_por_ato = {a["id"]: RDOC.documentos_para_lavrar(_c, a["id"])
                            for a in atos}
            # DE QUE NUMERO O PROXIMO ATO NAO PODE SER MENOR, e por que.
            # Nas fichas de acervo o numero se digita, e ate hoje a tela nao
            # dizia qual era o certo: quem digitava tinha de ir ao papel.
            piso = NUMT.piso_do_proximo(_c, matricula_id)
            # O QUE A REVISAO APONTOU E NINGUEM CONFERIU AINDA. Vem aqui, e
            # nao so na tela propria, porque quem sela abre a ficha — uma
            # lista que se abre de proposito e uma lista que ninguem abre.
            revisoes = RV.da_matricula(_c, matricula_id)
            # AS MINUTAS QUE ESPERAM REVISAO E LAVRATURA. Elas vem para a
            # ficha, e nao para uma tela propria, porque e aqui que quem
            # lavra esta — a lista que se abre de proposito e a lista que
            # ninguem abre (a licao do painel dos inacabados).
            minutas = RIMIN.listar(_c, matricula_id)
        # A MINUTA ESCOLHIDA ABRE O FORMULARIO DE LAVRAR JA PREENCHIDO. Quem
        # lavra e a rota de sempre: uma segunda porta para lavrar seria uma
        # segunda versao da regra que numera, sela e cobra.
        minuta_aberta = None
        # AS PARTES DA MINUTA VOLTAM AO FORMULARIO — 16/09/2026, e sem isto
        # o circulo da suspensao nao fecha. O ato suspenso guarda o teor, a
        # qualificacao E as partes; se a tela devolvesse so o texto, quem
        # reabrisse a minuta teria de digitar os nomes outra vez — e o selo
        # recusaria pelo mesmo motivo («Os nomes das partes devem ser
        # informados»), que foi exatamente o caso da AV-05 da 3.110 em 15/09.
        minuta_partes = []
        if numero_digitado(request.args.get("minuta")) is not None:
            with db.connect() as _c:
                escolhida = RIMIN.uma(_c, numero_digitado(request.args["minuta"]))
                if (escolhida
                        and escolhida["matricula_id"] == matricula_id
                        and escolhida["situacao"] == RIMIN.A_REVISAR):
                    minuta_aberta = escolhida
                    minuta_partes = RIMIN.partes(_c, int(escolhida["id"]))
        # PROTOCOLO UNIFICADO: prenotacao (prioridade) + caixa (itens).
        # Pedido do oficial 15/09/2026 («faca isso»): um fluxo so, sem o
        # balcao jogar dois «protocolo» sem entender. A FK
        # cx_protocolos.ri_protocolo_id liga quando preenchida; senao, a
        # ponte da casa e o deposito previo. Nao se inventa join.
        # O NÚMERO DO ENDEREÇO TEM TAMANHO (`numero_digitado`, LD10): o que
        # não é número que o banco guarde vale como não escolhido.
        prenotacao_escolhida_id = request.args.get("prenotacao_id")
        if prenotacao_escolhida_id and numero_digitado(prenotacao_escolhida_id) is None:
            prenotacao_escolhida_id = None
        protocolo_caixa_arg = request.args.get("protocolo_id")
        if protocolo_caixa_arg and numero_digitado(protocolo_caixa_arg) is None:
            protocolo_caixa_arg = None
        with db.connect() as _cx:
            protocolos_caixa = RITEOR.protocolos_do_caixa_abertos(_cx)
            # O PROTOCOLO DA CERTIDAO SE ESCOLHE DA LISTA — relato #76,
            # 17/09/2026: «ter que lembrar o numero do protocolo de
            # determinado cliente pode atrasar a emissao da certidao, melhor
            # mostrar os protocolos abertos e aguardando pagamento como opcao
            # de escolha». Ele relatou da matricula 5377, e medido hoje nas
            # **372** certidoes desta casa que tem protocolo gravado: **368**
            # citam o **protocolo de CAIXA** (o acervo inteiro) e **4** citam a
            # **PRENOTACAO** — e as quatro sao justamente as que ESTE sistema
            # emitiu (11571 na 3.110 e 11559 na 4.016). Por isso a lista da
            # tela tem as duas coisas, cada uma dizendo qual e.
            #
            # O RECORTE E DO RI, E NAO E PEQUENO — medido na producao em
            # 17/09/2026: dos **4.628** protocolos de caixa em andamento, **925
            # sao do RI** e **2.785 sao de firma**, mais 734 do RCPN, 98 das
            # notas, 70 do protesto, 12 do RTD, 3 de outros e 1 do RCPJ. Sem o
            # recorte a janela seria metade de reconhecimento de firma, que
            # numa certidao de imovel nao serve para nada. Com ele, os 80 mais
            # recentes do RI cobrem **01/07/2025 a 17/09/2026** (64 `A_PAGAR`
            # e 16 `ABERTO`), e os 80 tem `interessado` — a lista diz de quem
            # e o pedido.
            #
            # SAO DUAS LISTAS DE PROPOSITO, e nao a mesma recortada: a de
            # cima (`protocolos_caixa`) alimenta o <select> do quadro de
            # custas, que e LISTA FECHADA — o que nao estiver la nao se
            # digita. Recortar aquela tiraria do operador a unica forma de
            # ligar um protocolo de outra atribuicao ao ato desta ficha. Esta
            # de baixo alimenta o campo de texto da certidao, que ACEITA o
            # numero digitado — aqui o recorte so encurta a escolha.
            protocolos_da_certidao = RITEOR.protocolos_do_caixa_abertos(
                _cx, atribuicao="RI")
            resolvido = RITEOR.resolver_protocolo_caixa(
                _cx,
                protocolo_caixa_id=protocolo_caixa_arg,
                ri_protocolo_id=prenotacao_escolhida_id,
            )
            protocolo_caixa_escolhido = resolvido.get("protocolo_caixa_id")
            if protocolo_caixa_escolhido is not None:
                protocolo_caixa_escolhido = str(protocolo_caixa_escolhido)
            itens_do_protocolo_caixa = RITEOR.itens_do_protocolo_disponiveis(
                _cx, protocolo_caixa_escolhido)
            itens_ri_texto_completo = RITEOR.itens_com_texto_completo(_cx)
            depositos_da_prenotacao = resolvido.get("depositos") or []
            caixa_origem = resolvido.get("origem") or "nenhum"
            caixa_ligado = resolvido.get("caixa")
            # OS DOCUMENTOS PARA QUALIFICACAO DO PROTOCOLO GERAL ligado a
            # prenotacao escolhida — relato #135, decisao do oficial em
            # 15/10/2026: quem lavra ve o que o cliente entregou no balcao.
            # So da prenotacao ESCOLHIDA, e nao de todas as abertas: o bloco
            # das abertas saiu desta ficha no relato #85, por ser ruido.
            import protocolo_documentos as PDOC
            docs_qualificacao_lavrar = PDOC.da_prenotacao(
                _cx, prenotacao_escolhida_id)["ativos"]
        prenotacao_escolhida = None
        if prenotacao_escolhida_id:
            for p in abertos:
                if str(p["id"]) == str(prenotacao_escolhida_id):
                    prenotacao_escolhida = p
                    break
            if prenotacao_escolhida is None:
                prenotacao_escolhida = q1(
                    "SELECT id, numero, data_prenotacao, natureza_titulo, "
                    "apresentante FROM ri_protocolos WHERE id=%s",
                    (int(prenotacao_escolhida_id),))

        # AS CERTIDÕES DESTA FICHA — 16/09/2026, para reimprimir sem
        # reemitir. As vinte últimas bastam: quem procura uma de 2019 usa a
        # tela de certidões, que busca; aqui o caso é «acabei de emitir e a
        # impressora engasgou».
        certidoes = q("""SELECT * FROM ri_certidoes WHERE matricula_id=%s
                         ORDER BY ano DESC, numero DESC LIMIT 20""",
                      (matricula_id,))
        # QUANTAS CERTIDÕES A FICHA JÁ SOLTOU, E QUANTAS NÃO VALEM MAIS —
        # relato #81, 17/09/2026. O título da gaveta contava as LINHAS EM TELA,
        # e «20 certidões, 1 cancelada» não diz o mesmo que «trinta e duas, seis
        # canceladas».
        #
        # **A CONTA É DA FICHA INTEIRA, E NÃO DAS VINTE EM TELA.** A lista que
        # a ficha carrega tem `LIMIT 20` — é a janela de quem quer reimprimir a
        # que acabou de sair —, e contar dentro dela devolve o número da
        # JANELA. Quem lê o título o lê como o da matrícula, porque é isso que
        # ele promete; número que mede outra coisa é o carimbo que mente.
        #
        #   **E ele mentiria sem ninguém notar, porque o número sai
        #   plausível.** Medido na produção em 17/09/2026: **375** certidões do
        #   RI em **276** matrículas, **62** fichas com mais de uma certidão, e
        #   **a maior ficha tem 8** — nenhuma chega às vinte de hoje, de modo
        #   que os dois números coincidem em todas elas. Isto não conserta um
        #   número que alguém esteja vendo errado: fecha o dia em que uma ficha
        #   passar de vinte, e a tela passa a dizer que está mostrando menos que
        #   o total (o aviso logo abaixo do título, na ficha).
        contagem = q1("""SELECT COUNT(*) emitidas,
                                COALESCE(SUM(cancelada), 0)::bigint canceladas
                           FROM ri_certidoes WHERE matricula_id=%s""",
                      (matricula_id,))
        certidoes_canceladas = contagem["canceladas"] if contagem else 0
        certidoes_emitidas = contagem["emitidas"] if contagem else 0
        # OS PROTOCOLOS QUE PODEM PAGAR A CERTIDÃO, para a escrevente escolher
        # no formulário de emitir (22/10/2026, trava do selo pago).
        with db.connect() as _c_selo:
            candidatos_do_selo_da_certidao = _candidatos_da_certidao_do_ri(_c_selo)
            atendendo_do_selo = CXPROT.em_atendimento(
                banco(_c_selo), app.extensions["usuario_nome"]())

        # STUB ARQUIVADO DO LOTE OCR — 22/09/2026: a matrícula 1009 (e 1354)
        # ficou sem digitalização/atos de propósito; o scan era de outra
        # matrícula. Sem aviso no alto, o balcão pergunta «cadê o resto?».
        stub_arquivado = (
            "STUB_ARQUIVADO" in str(m.get("origem_chave") or "")
            or "[ARQUIVADO" in str(m.get("observacao") or "")
        )
        matricula_corrigida = None
        if stub_arquivado:
            import re as _re_stub
            _busca = f"{m.get('origem_chave') or ''} {m.get('observacao') or ''}"
            _mo = _re_stub.search(
                r"matr[ií]cula\s+(\d+)", _busca, _re_stub.IGNORECASE)
            if _mo:
                _alvo = q1(
                    "SELECT id, numero FROM ri_matriculas "
                    "WHERE cast(numero as text)=%s",
                    (_mo.group(1),))
                if _alvo and str(_alvo["id"]) != str(matricula_id):
                    matricula_corrigida = dict(_alvo)

        # O QUADRO DA CERTIDÃO DE ÔNUS — 13/10/2026: o que o sistema sabe dos
        # atos lavrados, a sugestão da IA (se houver, e se foi feita sobre a
        # ficha como está) e os trechos que podem ir transcritos. SÓ LÊ.
        with db.connect() as _c_onus:
            onus_painel = RONIA.painel(
                _c_onus, matricula_id,
                RIONUS.onus_vigentes(
                    atos, rotulo=lambda a: rotulo_ato(a["tipo"], a["numero"],
                                                      m["numero"])),
                Path(app.config["DATA_DIR"]),
                proprietarios_cadastro=[dict(p) for p in partes
                                        if p["proprietario_ativo"]])

        return render_template(
            "ri_ficha.html", m=m, atos=atos, partes=partes, imagens=imagens,
            onus_painel=onus_painel, RESULTADOS_ONUS=RONIA.RESULTADOS,

            certidoes=certidoes, certidoes_canceladas=certidoes_canceladas,
            certidoes_emitidas=certidoes_emitidas,
            certidoes_aguardando_selo=_certidoes_aguardando_selo(
                [c["id"] for c in certidoes]),
            candidatos_do_selo_da_certidao=candidatos_do_selo_da_certidao,
            CODIGO_BASE_DA_CERTIDAO=_codigo_base_da_certidao(),
            atendendo_do_selo=atendendo_do_selo,
            stub_arquivado=stub_arquivado,
            matricula_corrigida=matricula_corrigida,
            TIPOS_CERTIDAO=TIPOS_CERTIDAO,
            # AS MATRÍCULAS DE ORIGEM QUE O REGISTRO ANTERIOR CITA — a sugestão
            # do campo da certidão dominial. SÓ LÊ: quem decide o que entra é o
            # balcão, e em branco a emissão segue o registro anterior.
            ANOS_DA_VINTENARIA=sorted(RIDOM.ANOS_PERMITIDOS),
            ANOS_PADRAO_VINTENARIA=RIDOM.ANOS_PADRAO_VINTENARIA,
            origens_sugeridas=RIDOM.sugerir_numeros_origem(
                m["registro_anterior"], numero_atual=m["numero"]),
            revisoes=revisoes,
            revisoes_abertas=[r for r in revisoes if r["situacao"] == RV.ABERTA],
            minutas=minutas, minuta_aberta=minuta_aberta,
            carimbo_abertura=carimbo_da_abertura(),
            minuta_partes=minuta_partes,
            MINUTA_TIPOS=RIMIN.TIPOS,
            # O RASCUNHO daquela matrícula, se houver — lido, nunca criado
            # numa tela de leitura.
            rascunho=rascunho, piso=piso,
            # OS ITENS QUE ESTA CASA USOU no selo do ato, na ordem de uso —
            # medidos no acervo, e não uma lista escrita à mão que envelhece
            # na tarde em que se escreve.
            ITENS_DO_ATO_DO_RI=AS.itens_medidos_do_ato_do_ri(),
            itens_ri_texto_completo=itens_ri_texto_completo,
            protocolos_caixa=protocolos_caixa,
            # A LISTA DO CAMPO «PROTOCOLO» DA CERTIDAO — relato #76. O campo
            # continua livre: protocolo fora da janela se digita.
            protocolos_da_certidao=protocolos_da_certidao,
            protocolo_caixa_escolhido=protocolo_caixa_escolhido,
            itens_do_protocolo_caixa=itens_do_protocolo_caixa,
            prenotacao_escolhida=prenotacao_escolhida,
            prenotacao_escolhida_id=prenotacao_escolhida_id,
            depositos_da_prenotacao=depositos_da_prenotacao,
            caixa_origem=caixa_origem,
            caixa_ligado=caixa_ligado,
            docs_qualificacao_lavrar=docs_qualificacao_lavrar,
            # OS MOTIVOS DE GRATUIDADE QUE ESTA CASA ESCREVEU, na ordem de uso
            # — a lista existe para o balcão não redigitar a mesma frase com
            # erro, como aconteceu nos 48 do acervo.
            MOTIVOS_DA_GRATUIDADE_DO_RI=AS.MOTIVOS_DA_GRATUIDADE_DO_RI,
            docs_por_ato=docs_por_ato,
            e_imagem=RDOC.e_imagem,
            fraudes=fraudes,
            quebras=quebras, teor_seguro=teor_seguro, ROTULO=ROTULO_TIPO_FICHA,
            # OS ATOS QUE O TEXTO DA FICHA AINDA NAO CONTA — relato #67. Vao
            # depois do teor, e nao dentro dele: o teor gravado e o que o
            # registro diz, e o que se acrescenta desde entao se le ao lado.
            fora_do_teor=fora_do_teor,
            hoje=date.today().isoformat(),
            abrir_form=(request.args.get("lavrar") == "1"
                        or _pre_encerramento(m, piso, atos) is not None),
            enc_pre=_pre_encerramento(m, piso, atos),
            cnib=cnib, cnib_decisoes=cnib_decisoes, cnib_pendencias=cnib_pendencias, cnib_base_data=base_data, cnib_base_n=base_n,
            # QUÃO VELHA É A CÓPIA — e a tela diz isso SEMPRE, e não só quando
            # acha ordem.
            #
            #   «Sistema pode melhorar o módulo do CNIB, cobrando atualizações
            #   frequentes» — o oficial, 27/08/2026. Medido no mesmo dia: a
            #   ordem mais recente da cópia desta casa é de **19/03/2023**.
            #   Três anos.
            #
            #   O DEFEITO NÃO É A CÓPIA SER VELHA: é a tela CALAR quando não
            #   acha nada. A data só aparecia dentro do aviso de ordem
            #   encontrada — justamente o caso em que o escrevente já está
            #   alerta. Quando não havia ordem, a ficha ficava limpa, e limpa
            #   parece «nada consta» quando na verdade é «não sei, minha cópia
            #   é de 2023».
            cnib_idade=cnib_idade(base_data),
            cnib_dias_para_avisar=CNIB_DIAS_PARA_AVISAR,
            cnib_dos_atos=cnib_dos_atos,
            cnib_exige_protocolo=(
                db.get_setting(CNIB.CHAVE_EXIGIR_PROTOCOLO, "0") == "1"),
            protocolos=protocolos,
            protocolos_abertos=abertos,
            # O CNM DAS ANTIGAS, que o E-Ofício não trouxe: 43 das 1.701. Ele é
            # derivado, e por isso a tela pode mostrá-lo mesmo sem estar
            # gravado — dizendo que não está.
            cnm_calculado=(None if m["cnm"]
                           else _cnm_da_matricula(m["livro_norm"], m["numero"])),
            # QUEM ASSINA O ATO QUE VAI SAIR — relato #65: é quem está logado.
            # A lista de delegatários saiu daqui porque deixou de ser escolha;
            # ela continua viva para o timbre e para os atos antigos, na tela
            # própria (`/registro-imoveis/delegatarios`).
            quem_assina=quem_pratica_o_ato(),
            PAPEIS_RI=RC.PAPEIS,
            # So o ULTIMO ato pode ser expurgado: o hash de cada ato encadeia no
            # anterior, e tirar um do meio quebraria a conferencia dos seguintes.
            ultimo_ato_id=(max(a["id"] for a in atos) if atos else None),
        )

    @app.route("/registro-imoveis/<int:matricula_id>/conferir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_conferir(matricula_id):
        m = q1("SELECT numero, conferido FROM ri_matriculas WHERE id=%s", (matricula_id,))
        if not m:
            abort(404)
        novo = 0 if m["conferido"] else 1
        with db.transaction() as con:
            banco(con).escrever(
                """UPDATE ri_matriculas SET conferido=%s, conferido_em=%s, conferido_por=%s
                   WHERE id=%s""",
                (novo, db.now() if novo else None, None, matricula_id),
            )
        audit("RI_MATRICULA_CONFERIDA" if novo else "RI_CONFERENCIA_REVOGADA",
              "RI_MATRICULA", matricula_id, {"numero": m["numero"]})
        flash("Matrícula marcada como conferida contra o livro físico." if novo
              else "Conferência revogada. A matrícula volta a aparecer como não conferida.",
              "success" if novo else "warning")
        return redirect(url_for("ri_ficha", matricula_id=matricula_id))

    # ------------------------------------------------------- numeracao

    @app.route("/registro-imoveis/numeracao", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER")
    def ri_numeracao():
        if request.method == "POST":
            livro = (request.form.get("livro") or "").strip().upper()
            # LD13: 30 dígitos passavam pelo `int()` e estouravam no INSERT;
            # o que não é número continua sendo o 0 que a régua abaixo recusa.
            proximo = numero_digitado(request.form.get("proximo_numero")) or 0
            # O maior em uso e da SERIE, nao do volume: os livros 2, 2A ... 2S sao
            # volumes do mesmo Livro 2, e a matricula e numerada pela serventia.
            # Olhar so o volume foi o que fez nascer a 4011 depois da 4013.
            with db.connect() as con:
                maior = RC.maior_numero_da_serie(con, livro)
            if proximo <= maior:
                flash(f"A série do livro {livro} já usa o número {maior}. "
                      f"Fixar o próximo em {proximo} repetiria matrícula existente. "
                      f"O número da matrícula é único na serventia, não no volume.",
                      "danger")
            else:
                with db.transaction() as con:
                    banco(con).escrever(
                        """INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso, fixado_em, observacao)
                           VALUES (%s,%s,%s,%s,%s)
                           ON CONFLICT(livro) DO UPDATE SET proximo_numero=excluded.proximo_numero,
                             fixado_em=excluded.fixado_em, observacao=excluded.observacao""",
                        (livro, proximo, maior, db.now(),
                         (request.form.get("observacao") or "").strip() or "Fixado manualmente"),
                    )
                audit("RI_NUMERACAO_FIXADA", "RI_NUMERACAO", None,
                      {"livro": livro, "proximo": proximo, "maior_em_uso": maior})
                flash(f"Próximo número do livro {livro} fixado em {proximo}.", "success")
            return redirect(url_for("ri_numeracao"))

        rows = [dict(r) for r in q(
            """SELECT n.*, (SELECT COUNT(*) FROM ri_matriculas m WHERE m.livro_norm=n.livro) matriculas
               FROM ri_numeracao n ORDER BY n.livro""")]
        with db.connect() as con:
            for r in rows:
                r["serie"] = RC.serie_do_livro(r["livro"])
                r["maior_da_serie"] = RC.maior_numero_da_serie(con, r["livro"])
                r["proximo_da_serie"] = r["maior_da_serie"] + 1
                r["desalinhado"] = int(r["proximo_numero"] or 0) != r["proximo_da_serie"]
        # O QUE MANDA E A SERIE, e por isso ela vem PRIMEIRO na tela.
        #
        #   Havia vinte linhas de volume e nenhuma linha de serie — e as vinte
        #   mostram numeros diferentes, sobras da importacao de 13/08/2026. Quem
        #   lesse a tabela crua concluiria que escolher `2A` abriria a matricula
        #   714. **Nao abriria**: `proximo_numero` conta pela serie e devolve
        #   4014 para qualquer volume. Eu mesmo me enganei lendo a coluna crua
        #   antes de perguntar a funcao.
        #
        #   Tela que so mostra o dado cru deixa quem a le tirar a conclusao
        #   errada sozinho. Agora ela mostra o que vale, e o cru embaixo.
        series = {}
        with db.connect() as con:
            bd = banco(con)
            for r in rows:
                if r["serie"] in series:
                    series[r["serie"]]["volumes"] += 1
                    continue
                series[r["serie"]] = {
                    "serie": r["serie"],
                    "proximo": r["proximo_da_serie"],
                    "maior": r["maior_da_serie"],
                    "volumes": 1,
                    "matriculas": bd.valor(
                        "SELECT COUNT(*) AS n FROM ri_matriculas "
                        "WHERE livro_norm ILIKE %s", (r["serie"] + "%",)),
                }
        return render_template("ri_numeracao.html", rows=rows, series=sorted(series.values(), key=lambda x: x['serie']))

    # --------------------------------------------- livro de protocolo

    def _cnm_da_matricula(livro, numero) -> str | None:
        """O CNM daquela matrícula, ou None quando não dá para montar. Só LÊ.

        NÃO DERRUBA A ABERTURA. Sem o CNS da serventia informado, o código não
        sai — e a matrícula tem de sair do mesmo jeito: o CNM é identificação,
        e recusar a abertura por causa dele seria travar o registro por um
        campo que se completa depois.
        """
        try:
            return CNM.montar(db.get_setting("ri_cns", ""), livro, numero)
        except CNM.CnmError:
            return None

    def _feriados() -> set:
        return ler_feriados_locais(db.get_setting("ri_feriados_locais", ""))

    def _prazo_gravado(p) -> int | None:
        """Quantos dias uteis esta prenotacao ganhou. So LE.

        Do que foi GRAVADO, e nao de uma constante: 20 dias no comum e 40 no
        REURB-S, e o comprovante nao precisa saber qual e qual — a data-limite
        ja foi calculada quando a prenotacao nasceu, com os feriados da casa.
        """
        try:
            return dias_uteis_entre(date.fromisoformat(p["data_prenotacao"]),
                                    date.fromisoformat(p["data_limite"]),
                                    _feriados())
        except (ValueError, TypeError, KeyError):
            return None

    def _dias_que_faltam(p) -> int | None:
        """Quantos dias uteis ainda restam, de hoje ate o limite. So LE.

        «Vence em 12/09» faz o cliente contar no calendario; «faltam 14 dias
        uteis» ele entende no balcao. Negativo quer dizer prazo vencido, e o
        comprovante diz isso com todas as letras.
        """
        try:
            return dias_uteis_entre(date.today(),
                                    date.fromisoformat(p["data_limite"]),
                                    _feriados())
        except (ValueError, TypeError, KeyError):
            return None

    def _selar_a_prenotacao(protocolo_id: int, numero, form, *,
                             gravado=None) -> str:
        """Pede o selo da prenotacao DEPOIS de ela existir. FALA COM A REDE.

        «Quando um titulo e prenotado no RI devemos emitir recibo ao cliente…
        A prenotacao do RI e cobrada e deve emitir selo» — o oficial, em
        27/08/2026. Ele esta certo, e o acervo confirma: **829 selos** de
        `/selo/imovel/prenotacao`.

        FORA DA TRANSACAO DO ATO — a chamada tem prazo de vinte segundos, e
        segurar o `BEGIN IMMEDIATE` da casa por vinte segundos poria todo
        outro balcao no `busy_timeout`.

        NUNCA DERRUBA A PRENOTACAO. Prenotacao desfeita por causa de selo e
        pior que prenotacao sem selo: ela e o que garante a prioridade do
        titulo, e a prioridade se conta da hora em que ele entrou.

        A ISENCAO PEDE MOTIVO ESCRITO, e o envelope o leva — 48 dos 829 selos
        sairam isentos, com o motivo dentro (REURB, Lei 13.465/2017).
        """
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return SR.recado_pendente_selo()
        item = (form.get("codigo_tj") or "").strip() or None
        isento, motivo = ler_isencao_do_form(form)
        natureza = ((form.get("natureza_titulo") or "").strip()
                    or (form.get("objeto") or "").strip())
        if not natureza:
            return (" A prenotação foi lavrada SEM SELO: o selo pede a "
                    "natureza do título, e ela não foi informada.")
        versao = AS.versao_da_tabela_de_custas(
            "/selo/imovel/prenotacao",
            db.get_setting("selo_tabela_custas_em", ""))
        if not versao:
            return (" A prenotação foi lavrada SEM SELO: falta dizer de que "
                    "data é a tabela de custas em vigor, em Administrativo → "
                    "Configurações.")
        apresentante = (form.get("apresentante") or "").strip()
        documento = form.get("apresentante_documento")
        # SÓ NO «SELAR» DEPOIS — a rota passa `gravado`, a lavratura não.
        # A faixa «Pendente de selo» não manda o apresentante; ele já está
        # na prenotação. Sem este nome o envelope sai com parteAto vazio e
        # o aparelho recusa «Os nomes das partes devem ser informados».
        # O que o formulário trouxer continua valendo.
        if not apresentante and gravado is not None:
            apresentante = (gravado["apresentante"] or "").strip()
            if apresentante and not str(documento or "").strip():
                documento = gravado["apresentante_documento"]
            if not apresentante:
                return (" A prenotação foi lavrada SEM SELO: informe o "
                        "apresentante — o selo exige os nomes das partes, e "
                        "esta prenotação não tem apresentante gravado.")
        try:
            envelope = AS.envelope_da_prenotacao(
                protocolo=numero,
                escrevente=app.extensions["usuario_nome"](),
                versao_tabela=versao, descricao_natureza=natureza,
                partes=([{"nome": apresentante, "documento": documento}]
                        if apresentante else []),
                codigo_tj=item, isento=isento, motivo_isencao=motivo)
        except AS.AtoError as erro:
            return f" A prenotação foi lavrada SEM SELO: {erro}"

        r = AS.selar_o_ato_lavrado(
            db, Path(app.config["DATA_DIR"]), tabela="ri_protocolos",
            ato_id=protocolo_id, tipo="PRENOTACAO", atribuicao="RI",
            agora=datetime.now().isoformat(timespec="seconds"),
            cns=db.get_setting("ri_cns", ""),
            usuario=app.extensions["usuario_nome"](), dados=envelope,
            referencia=f"ri_protocolos:{int(protocolo_id)}")
        if not r["selado"]:
            return f" A prenotação foi lavrada SEM SELO: {r['motivo']}"
        return f" Selo {r['numero']}."

    def _o_selador_esta_pronto() -> bool:
        """O aparelho tem endereco e credencial nesta instalacao? So LE.

        SERVE PARA UMA DECISAO SO, e ela e a da suspensao: «selo recusado
        suspende ato» pressupoe que houve RECUSA. Numa casa que ainda nao
        configurou o selador nao ha recusa nenhuma — ha um aparelho que
        ninguem apontou —, e suspender ali poria todo ato num laco sem
        saida: lavra, suspende, relavra, suspende, e o livro nunca anda.

        `situacao(...)["pronto"]` e a mesma medida que a tela do selador
        mostra: endereco em uso mais credencial gravada. Uma segunda regra
        aqui divergiria dela no primeiro conserto.
        """
        try:
            with db.connect() as _c:
                return bool(SELCFG.situacao(
                    _c, Path(app.config["DATA_DIR"]))["pronto"])
        except Exception:                                      # noqa: BLE001
            # Sem resposta, trata-se como NAO pronto: o ato fica lavrado e
            # some para a lista de atos sem selo, que e o caminho conhecido.
            return False


    def ler_isencao_do_form(form) -> tuple[bool, str | None]:
        """Lê isento + motivo do POST, com a guarda do R-01/4019 (23/09/2026).

        A tela do ato do RI escondia a gratuidade num `<details>` fechado:
        checkbox `isento=1` e campo `motivo_isencao`. Beatriz preencheu o
        motivo (art. 290-A) e o selo saiu **cobrado** (~R$ 1.173) porque o
        checkbox não veio no POST — `isento` ficou 0 no banco com o motivo
        gravado. O envelope só manda `motivoIsentoGratuito` quando
        `isento=True`.

        REGRA: motivo escrito = intenção de gratuidade. A marca confirma;
        se o motivo veio e a marca não, trata-se como isento (e a recusa
        de isento-sem-motivo continua em `falta_para_selar`).
        """
        isento = form.get("isento") == "1"
        motivo = (form.get("motivo_isencao") or "").strip() or None
        if motivo and not isento:
            isento = True
        # REURB-S (Lei 13.465/2017 art. 13 §1º): isento automático — 30/09/2026 Beatriz.
        # Checkbox antigo `reurb=1` equivale a tipo S (prazo 40 + isento).
        tipo = (form.get("reurb_tipo") or "").strip().upper()
        if not tipo and form.get("reurb") == "1":
            tipo = "S"
        if tipo == "S":
            isento = True
            if not motivo:
                motivo = (
                    "O REGISTRO DISPENSA O PAGAMENTO DE EMOLUMENTOS PREVISTO NA "
                    "LEI Nº 13.465, DE 2017."
                )
        return isento, motivo

    def falta_para_selar(*, natureza, codigo_tj, isento, motivo_isencao,
                         selo_a_mao, e_acervo: bool = False,
                         base_calculo=None) -> str:
        """O que impede o selo de sair, dito ANTES de o ato existir. So le.

        RELATO DO OFICIAL EM 15/09/2026: «deu problema no av05 e foi lavrado,
        mas cancelado so pq nao saiu selo. nao eh assim que deve operar, se deu
        problema no selo deve voltar e permitir retificar o erro e tentar
        lavrar novamente o mesmo ato».

        ELE ESTA CERTO, E A REGRA DA CASA JA DIZIA ISSO NOUTRO CAMPO. Sobre a
        gratuidade, em 14/09: «**A RECUSA E AQUI, E NAO NO SELO.** O envelope
        tambem a faria, mas ali o ato ja estaria lavrado e na cadeia de hash
        (...). Aqui o cliente ainda esta na frente.» O mesmo vale para a
        natureza e para o item da tabela: sao coisas que a TELA sabe antes de
        qualquer rede, e recusar depois custa um ato cancelado no livro.

        SAO DUAS ESPECIES DE FALHA, E SO UMA CABE AQUI:

          - **o que a tela sabe** — falta natureza, falta item, isento sem
            motivo: recusa-se antes, o ato nao nasce, e quem atende corrige e
            lavra de novo o MESMO ato;
          - **o que so a rede diz** — aparelho fora do ar, credencial vencida,
            recusa do TJMA: aí o ato **fica lavrado**, e o selo entra depois
            pelo botao «Selar este ato». Balcao parado e pior que selo
            atrasado, e essa e a regra escrita desta casa desde agosto.

        O ATO DE ACERVO NAO PRECISA DO ITEM — decisao do oficial em
        16/09/2026: «ato de acerto fica sem item de custa».

          E ele esta certo, e o dado prova: `codigo_tj` esta preenchido em
          **zero dos 1.248** atos herdados. O ato de acervo ja foi praticado,
          ja foi cobrado e ja foi selado NO PAPEL, anos atras; exigir o item
          para lanca-lo no sistema faria a casa nao conseguir digitar o
          proprio livro. O que entra ali e HISTORIA, e nao servico novo.

          **A NATUREZA CONTINUA SENDO EXIGIDA**, e a diferenca importa: ela
          descreve o ato — e o indice real do ONR a le —, enquanto o item
          descreve o que se COBROU. Nao se cobra o que ja foi cobrado; mas o
          ato continua tendo de dizer o que e.

        Devolve texto vazio quando nao ha impedimento.
        """
        if str(selo_a_mao or "").strip():
            # Selo digitado a mao: o automatico nem e pedido, e nada do que
            # o envelope exigiria se aplica.
            return ""
        if isento and not str(motivo_isencao or "").strip():
            return ("Ato gratuito precisa do motivo escrito — é ele que sai "
                    "dentro do selo e que a correição lê.")
        if not str(natureza or "").strip():
            return ("Informe a natureza do título: o selo a exige, e sem ela "
                    "ele não sai. Ela está no campo «Natureza do título», "
                    "logo acima do teor.")
        if not str(codigo_tj or "").strip() and not e_acervo:
            return ("Escolha o item da tabela de custas: o selo o exige, e "
                    "ele não sai do tipo do ato — por isso a tela pergunta.")
        # 16.3 = "Registros de atos com valor declarado". Em branco a tela
        # manda pelo caminho sem-valor; o TJ recusa com «Nenhuma das
        # informações sobre a base de cálculo do valor declarado foi
        # preenchida» (Beatriz, R-01/4019, 23/09/2026, duas vezes).
        # A recusa é AQUI, antes do ato nascer — mesma regra da natureza.
        codigo = str(codigo_tj or "").strip()
        try:
            base = float(base_calculo or 0)
        except (TypeError, ValueError):
            base = 0.0
        if codigo == "16.3" or codigo.startswith("16.3."):
            if base <= 0:
                return ("O item 16.3 (registro com valor declarado) exige o "
                        "campo «Valor declarado (base de cálculo)». Ele está "
                        "logo abaixo do item da tabela. Em branco o selo vai "
                        "pelo caminho sem valor e o Tribunal recusa. A "
                        "gratuidade (art. 290-A) não dispensa esse campo — "
                        "marque isento e ainda assim informe o valor do título.")
        return ""

    def _partes_para_o_selo_ri(matricula, partes, ato_id=None) -> list:
        """HOTFIX-2026-10-13-03 (AV-08/1196): o TJMA recusa «Os nomes das partes
        devem ser informados». Ato de ofício (encerramento) não tem parte.
        Ordem: partes do ato; proprietários ativos da matrícula; partes do
        último ato da matrícula que tem partes; a serventia (de ofício)."""
        def limpar(linhas):
            vistos, saida = set(), []
            for n, d in linhas:
                nome = " ".join(str(n or "").split()).strip(" ,;")
                if not nome or nome.upper() in vistos:
                    continue
                vistos.add(nome.upper())
                saida.append({"nome": nome, "documento": d or ""})
            return saida
        achadas = limpar(partes or [])
        if achadas:
            return achadas
        try:
            if matricula is not None:
                mid = int(matricula["id"])
            else:
                mid = int(q1("SELECT matricula_id FROM ri_atos WHERE id=%s", (int(ato_id),))["matricula_id"])
            achadas = limpar([(r["nome"], r["documento_numero"]) for r in q(
                "SELECT nome, documento_numero FROM ri_partes WHERE matricula_id=%s "
                "AND proprietario_ativo=1 ORDER BY id", (mid,))])
            if not achadas:
                ult = q1("""SELECT p.ato_id FROM ri_partes p JOIN ri_atos a ON a.id=p.ato_id
                            WHERE p.matricula_id=%s AND COALESCE(a.cancelado,0)=0
                            ORDER BY a.numero DESC, p.ato_id DESC LIMIT 1""", (mid,))
                if ult:
                    achadas = limpar([(r["nome"], r["documento_numero"]) for r in q(
                        "SELECT nome, documento_numero FROM ri_partes WHERE ato_id=%s "
                        "ORDER BY id", (ult["ato_id"],))])
        except Exception:
            achadas = []
        if achadas:
            return achadas
        return [{"nome": (db.get_setting("unit_name", "") or dados_serventia(db.get_settings)["unit_name"]),
                 "documento": db.get_setting("serventia_cnpj", "") or ""}]

    def _selar_o_ato_do_ri(*, ato_id: int, tipo: str, numero: int, matricula,
                           base_calculo, codigo_tj, descricao_natureza,
                           protocolo, partes, selo_a_mao,
                           isento: bool = False, motivo_isencao=None,
                           referencia=None) -> dict:
        """Pede o selo do REGISTRO ou da AVERBACAO. FALA COM A REDE.

        Ordem do oficial em 14/09/2026: «incorpore o selador automatizado de
        dentro do sistema». Ate aqui o ato do RI era a unica coisa que esta
        casa lavrava e mandava o escrevente selar noutro programa — a
        prenotacao e a certidao do RI ja selavam sozinhas.

        O CAMINHO SAI DO VALOR DECLARADO, e nao do tipo do ato: ha averbacao
        com valor e registro sem. Ver a medicao dos 120 envelopes no cabecalho
        de `envelope_do_ato_do_ri`.

        DEVOLVE `{"recado", "suspende"}`, E O SEGUNDO CAMPO DECIDE SE O ATO
        SE SUSPENDE — 16/09/2026, e ele nasceu de um defeito meu.

          **E ELE SE CHAMAVA `da_rede` ATE O FIM DAQUELE DIA**, quando o
          oficial decidiu o item 1: «se falhar o selo, SEMPRE suspender o ato
          para corrigir o problema» vale tambem para a casa que ainda nao
          apontou o aparelho — para quem le o livro, os dois casos sao um ato
          sem selo. O nome mudou junto porque a pergunta mudou: nao e mais «a
          falha veio da rede?», e sim «este ato se suspende?».

          A ordem do oficial e «selo recusado suspende ato». Ao liga-la, eu
          fiz TODA frase «SEM SELO» suspender — e tres das cinco daqui nao
          sao recusa de selo nenhum: sao coisas que faltam PREENCHER ou
          CONFIGURAR. A pior delas e o item da tabela de custas, que ele
          acabara de dispensar no mesmo dia («ato de acerto fica sem item de
          custa»): o ato de acervo seria suspenso, relavrado, suspenso outra
          vez, **para sempre**, e a ficha nunca receberia o proprio livro.

          O QUE SEPARA AS DUAS ESPECIES ja estava escrito em
          `falta_para_selar`: **o que a tela sabe** se recusa antes de o ato
          nascer; **o que so o selo diz** — aparelho fora do ar, aparelho que
          ninguem apontou, credencial vencida, recusa do TJMA — e o caso em
          que CORRIGIR E LAVRAR DE NOVO resolve, e e por isso que ele
          suspende.

          O QUE CONTINUA SENDO LAVRADO SEM SELO e so o que quem atende NAO
          TEM COMO CORRIGIR: o ato de ACERVO sem item de custa, que o oficial
          dispensou em 16/09. Suspende-lo poria aquele ato num laco — lavra,
          suspende, relavra, suspende —, e a ficha nunca receberia o proprio
          livro. **Selador nao apontado nao e laco: e parede, e tem quem a
          derrube** apontando o aparelho.

          E O CAMPO E UM `bool`, e nao uma palavra dentro da frase. Adivinhar
          a especie lendo o texto do recado seria o varredor batendo na
          propria prosa pela decima terceira vez — e aqui o custo e um ato que
          nao se lavra.

        O SELO DIGITADO A MAO GANHA, e o automatico nem e pedido: e o caminho
        de quando o selador esta fora do ar, e pedir outro por cima faria a
        casa comprar dois selos para o mesmo ato.
        """
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return {"recado": SR.recado_pendente_selo(),
                    "suspende": False, "pendente_de_selo": True}
        def falta(frase: str) -> dict:
            """Falha que quem atende NAO tem como corrigir: o ato fica."""
            return {"recado": f" O ato foi lavrado SEM SELO: {frase}",
                    "suspende": False}

        if str(selo_a_mao or "").strip():
            return {"recado": "", "suspende": False}
        natureza = str(descricao_natureza or "").strip()
        if not natureza:
            return falta("o selo pede a natureza do título, e ela não foi "
                         "informada.")
        if not str(codigo_tj or "").strip():
            # O ATO DE ACERVO CHEGA AQUI DE PROPOSITO — `falta_para_selar` o
            # deixou passar por ordem do oficial. Ele fica lavrado e sem selo,
            # que e o que ele e no papel ha anos.
            return falta("falta escolher o item da tabela de custas — ele não "
                         "sai do tipo do ato, e por isso a tela pergunta.")
        # BASE EFETIVA POR ITEM — Beatriz 24/09/2026 (AV-01/4001):
        # a tela manda o valor do imovel (para 16.22.8.1); itens so-sem-valor
        # (16.5) precisam de caminho /sem-valor. Sem este corte, o TJ recusa
        # com «valor declarado fora da faixa».
        # HOTFIX R-8/3359 (27/10/2026): subitem de faixa do caixa (16.45.33)
        # vai ao TJ como o item (16.45); o TJ recusava o subitem.
        import caixa_protocolo as _CXP_FAIXA
        codigo_tj = _CXP_FAIXA.subitem_da_faixa(codigo_tj) or str(codigo_tj).strip()
        base_reais = (base_calculo or 0) / 100.0
        base_para_o_selo = AS.base_calculo_do_selo_ri(codigo_tj, base_reais)
        caminho = AS.caminho_do_ato_do_ri(base_para_o_selo)
        versao = AS.versao_da_tabela_de_custas(
            caminho, db.get_setting("selo_tabela_custas_em", ""))
        if not versao:
            return falta("falta dizer de que data é a tabela de custas em "
                         "vigor, em Administrativo / Configuracoes.")
        try:
            envelope = AS.envelope_do_ato_do_ri(
                matricula=matricula["numero"], numero_do_ato=numero,
                escrevente=app.extensions["usuario_nome"](),
                versao_tabela=versao, descricao_natureza=natureza,
                # O LIVRO E O VOLUME DA MATRICULA ('2S', '2-Q'), medido em
                # 120/120 — e nao o `1A` do livro de protocolo.
                livro=matricula["livro"], codigo_tj=codigo_tj,
                protocolo=protocolo,
                # EM REAIS, e nao em centavos: a casa guarda centavos inteiros
                # e o selador quer o valor decimal. A conversao mora aqui, num
                # lugar so.
                base_calculo=base_reais,
                partes=_partes_para_o_selo_ri(matricula, partes),
                # O SELO SAI ISENTO, COM O MOTIVO DENTRO — a forma está medida
                # e provada contra o aparelho: `isento` booleano mais
                # `motivoIsentoGratuito`. É a mesma que a prenotação deste
                # módulo manda em 48 envelopes.
                isento=isento, motivo_isencao=motivo_isencao)
        except AS.AtoError as erro:
            # DADO QUE O ENVELOPE RECUSA, e nao a rede: montar de novo com o
            # mesmo dado recusaria de novo.
            return falta(str(erro))

        r = AS.selar_o_ato_lavrado(
            db, Path(app.config["DATA_DIR"]), tabela="ri_atos", ato_id=ato_id,
            tipo=tipo, atribuicao="IMOVEL",
            agora=datetime.now().isoformat(timespec="seconds"),
            cns=db.get_setting("ri_cns", ""),
            usuario=app.extensions["usuario_nome"](), dados=envelope,
            # O CAMINHO VAI PRONTO: `caminho_do_ato('ri_atos', ...)` devolve
            # None de proposito, porque so quem tem o valor declarado na mao
            # sabe escolher entre com-valor e sem-valor.
            caminho=caminho,
            # REFERENCIA UNICA POR OCORRENCIA — com varios selos no mesmo ato
            # (ex.: 16.5 duas vezes), sem o indice o aparelho devolveria o
            # MESMO selo. Quem chama com lista usa ri_atos:{id}:{cod}:{n}.
            referencia=(referencia or f"ri_atos:{int(ato_id)}"))
        if not r["selado"]:
            # O SELO NAO SAIU — E O ATO SE SUSPENDE, ITEM 1 DE 16/09/2026.
            #
            #   Ate esta data havia aqui `_o_selador_esta_pronto()`: com o
            #   aparelho apontado, «nao saiu» era recusa e suspendia; **sem
            #   aparelho apontado o ato ficava lavrado sem selo**. O oficial
            #   decidiu que os dois suspendem — «se falhar o selo, sempre
            #   suspender o ato para corrigir o problema» —, e ele esta certo:
            #   para quem le o livro os dois casos sao a mesma coisa, um ato
            #   sem selo, e o segundo tem correcao tao clara quanto o primeiro.
            return {"recado": f" O ato foi lavrado SEM SELO: {r['motivo']}",
                    "suspende": True}
        return {"recado": f" Selo {r['numero']}.", "suspende": False}

    

    def _fila_de_selos_faltando(ato_id: int, codigos: list[str]) -> list[str]:
        """Unidades da fila ainda sem referencia no razao.

        Referencia: ri_atos:{id}:{codigo}:{indice}. Sem isto, «Selar este ato»
        recusava completar multi-selo parcial (16.5 x2 faltando apos 16.22.8.1).
        """
        ja = set()
        with db.connect() as con:
            for r in banco(con).ler(
                "SELECT referencia FROM sd_selos "
                "WHERE tabela='ri_atos' AND ato_id=%s AND cancelado_em IS NULL "
                "ORDER BY id",
                (int(ato_id),)):
                ref = str(r["referencia"] or "").strip()
                if ref:
                    ja.add(ref)
        faltam: list[str] = []
        ocorrencias: dict[str, int] = {}
        for codigo in [str(c or '').strip() for c in (codigos or []) if str(c or '').strip()]:
            ocorrencias[codigo] = ocorrencias.get(codigo, 0) + 1
            indice = ocorrencias[codigo]
            ref = f"ri_atos:{int(ato_id)}:{codigo}:{indice}"
            if ref not in ja:
                faltam.append(codigo)
        return faltam

    def _codigos_de_selo_do_form(form) -> list[str]:
        """Lista expandida de itens da tabela (um codigo por selo a pedir).

        Beatriz 23/09/2026 — desmembramento da 4001: no mesmo ato cabem
        16.22.8.1 uma vez e 16.5 duas vezes. A tela manda pares
        `codigo_tj_selo` + `qtd_selo`; aqui vira a fila que o selador consome.

        Compatível com o formulário antigo (um só `codigo_tj`) e com a
        lavratura (`codigo_tj_item` / itens de protocolo já achatados).
        """
        codigos: list[str] = []
        itens = [str(x or "").strip() for x in form.getlist("codigo_tj_selo")]
        qtds = form.getlist("qtd_selo")
        if any(itens):
            for i, cod in enumerate(itens):
                if not cod:
                    continue
                bruto = qtds[i] if i < len(qtds) else "1"
                try:
                    q = int(str(bruto or "1").strip() or "1")
                except ValueError:
                    q = 1
                q = max(1, min(q, 50))
                codigos.extend([cod] * q)
            return codigos
        for c in form.getlist("codigo_tj_item"):
            c = str(c or "").strip()
            if c:
                codigos.append(c)
        um = str(form.get("codigo_tj") or "").strip()
        if um and um not in codigos:
            # Campo livre: entra se a lista de radios/checkboxes veio vazia
            # OU se o operador digitou um complemento fora da lista.
            if not codigos:
                codigos = [um]
        return codigos

    def _selar_itens_do_ato_do_ri(*, ato_id: int, tipo: str, numero: int,
                                  matricula, base_calculo, codigos_tj,
                                  descricao_natureza, protocolo, partes,
                                  selo_a_mao, isento: bool = False,
                                  motivo_isencao=None) -> dict:
        """Um selo por item/unidade. FALA COM A REDE.

        Espelho do Protesto: cada codigo da fila vira o SEU selo, com
        referencia `ri_atos:{id}:{codigo}:{indice}`. Sem o indice, duas
        unidades do mesmo item (16.5 x2) receberiam o mesmo SID.

        SEM BYPASS: se nenhum selo sai, suspende (regra da casa). Se alguns
        saem e outros falham, NÃO inventa sucesso — devolve o recado parcial
        e NÃO suspende (ja ha selo pago amarrado ao ato; suspender sumiria
        com o rastilho do dinheiro).
        """
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return {"recado": SR.recado_pendente_selo(),
                    "suspende": False, "pendente_de_selo": True}
        if str(selo_a_mao or "").strip():
            return {"recado": "", "suspende": False}
        codigos = [str(c or "").strip() for c in (codigos_tj or [])
                   if str(c or "").strip()]
        if not codigos:
            return _selar_o_ato_do_ri(
                ato_id=ato_id, tipo=tipo, numero=numero, matricula=matricula,
                base_calculo=base_calculo, codigo_tj=None,
                descricao_natureza=descricao_natureza, protocolo=protocolo,
                partes=partes, selo_a_mao=None, isento=isento,
                motivo_isencao=motivo_isencao)
        if len(codigos) == 1:
            return _selar_o_ato_do_ri(
                ato_id=ato_id, tipo=tipo, numero=numero, matricula=matricula,
                base_calculo=base_calculo, codigo_tj=codigos[0],
                descricao_natureza=descricao_natureza, protocolo=protocolo,
                partes=partes, selo_a_mao=None, isento=isento,
                motivo_isencao=motivo_isencao)

        saiu: list[str] = []
        faltou: list[str] = []
        ocorrencias: dict[str, int] = {}
        for codigo in codigos:
            ocorrencias[codigo] = ocorrencias.get(codigo, 0) + 1
            indice = ocorrencias[codigo]
            r = _selar_o_ato_do_ri(
                ato_id=ato_id, tipo=tipo, numero=numero, matricula=matricula,
                base_calculo=base_calculo, codigo_tj=codigo,
                descricao_natureza=descricao_natureza, protocolo=protocolo,
                partes=partes, selo_a_mao=None, isento=isento,
                motivo_isencao=motivo_isencao,
                referencia=f"ri_atos:{int(ato_id)}:{codigo}:{indice}")
            frase = str(r.get("recado") or "")
            if "SEM SELO" in frase or r.get("suspende"):
                motivo = frase.split("SEM SELO:", 1)[-1].strip() if "SEM SELO" in frase else frase.strip()
                faltou.append(f"{codigo}: {motivo or 'não saiu'}")
            else:
                # " Selo XYZ." → XYZ
                num = frase.replace("Selo", "").replace(".", "").strip()
                saiu.append(num or codigo)

        if saiu and not faltou:
            return {"recado": (f" {len(saiu)} selo(s): {', '.join(saiu)}."),
                    "suspende": False}
        if saiu:
            return {"recado": (f" {len(saiu)} selo(s) ok ({', '.join(saiu)}); "
                               f"{len(faltou)} falhou: {faltou[0]}"),
                    "suspende": False}
        return {"recado": (f" O ato foi lavrado SEM SELO: "
                           f"{faltou[0] if faltou else 'nenhum item saiu'}"),
                "suspende": True}


    def _selar_arquivamento_do_ri(*, ato_id: int, folhas: int,
                                   selo_do_ato: str | None = None,
                                   partes=None,
                                   isento: bool = False,
                                   motivo_isencao=None) -> dict:
        """Pede o selo 16.39 (arquivamento por folha). FALA COM A REDE.

        OPCIONAL E INDEPENDENTE do selo do registro/averbacao (Beatriz
        23/09/2026). Se o ato ja selou e o arquivamento falhar, o ato
        continua ok — devolve `ok=False` com motivo claro; NAO inventa
        bypass nem suspende o ato.

        `vincular_ao_ato` grava em `selo_texto`; por isso, depois do pedido,
        restauramos o selo do ato e gravamos o de arquivamento na coluna
        propria (mesmo corretivo do RCPJ Santa Isabel / 15.22).
        """
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return {"ok": False, "motivo": SR.recado_pendente_selo().strip(),
                    "pendente_de_selo": True}
        try:
            q = max(1, int(folhas or 0))
        except (TypeError, ValueError):
            return {"ok": False,
                    "motivo": "informe a quantidade de folhas (>= 1)."}
        if q < 1:
            return {"ok": False,
                    "motivo": "informe a quantidade de folhas (>= 1)."}
        caminho = AS.CAMINHO_ARQUIVAMENTO_RI
        versao = AS.versao_da_tabela_de_custas(
            caminho, db.get_setting("selo_tabela_custas_em", ""))
        if not versao:
            return {"ok": False,
                    "motivo": ("falta a data da tabela de custas em "
                               "Administrativo / Configuracoes.")}
        try:
            envelope = AS.envelope_do_arquivamento_do_ri(
                escrevente=app.extensions["usuario_nome"](),
                versao_tabela=versao, quantidade=q,
                partes=_partes_para_o_selo_ri(None, partes, ato_id=ato_id),
                isento=bool(isento),
                motivo_isencao=motivo_isencao)
        except AS.AtoError as erro:
            return {"ok": False, "motivo": str(erro)}

        # Guarda o selo do ato ANTES — selar_o_ato_lavrado sobrescreve
        # selo_texto via vincular_ao_ato.
        if selo_do_ato is None:
            with db.connect() as con:
                row = banco(con).um(
                    "SELECT selo_texto FROM ri_atos WHERE id=%s",
                    (int(ato_id),))
                selo_do_ato = (row["selo_texto"] if row else None)

        r = AS.selar_o_ato_lavrado(
            db, Path(app.config["DATA_DIR"]), tabela="ri_atos", ato_id=ato_id,
            tipo="ARQUIV", atribuicao="IMOVEL",
            agora=datetime.now().isoformat(timespec="seconds"),
            cns=db.get_setting("ri_cns", ""),
            usuario=app.extensions["usuario_nome"](), dados=envelope,
            caminho=caminho,
            referencia=f"ri_atos:{int(ato_id)}:{AS.CODIGO_ARQUIVAMENTO_RI}:1")
        if not r["selado"]:
            # Restaura selo_texto se o vincular chegou a gravar algo errado
            # (quando nao selado, vincular nao roda — mas por precaução).
            if selo_do_ato:
                with db.transaction() as con:
                    banco(con).escrever(
                        "UPDATE ri_atos SET selo_texto=%s WHERE id=%s",
                        (selo_do_ato, int(ato_id)))
            return {"ok": False, "motivo": r["motivo"]}

        with db.transaction() as con:
            bd = banco(con)
            bd.escrever(
                """UPDATE ri_atos
                      SET selo_texto=COALESCE(%s, selo_texto),
                          selo_arquivamento=%s,
                          folhas_arquivamento=%s
                    WHERE id=%s""",
                (selo_do_ato or None, r["numero"], q, int(ato_id)))
            # Arquivamento 16.39 ok -> encerra a prenotação do ato (Beatriz
            # 23/09/2026). Falha aqui NÃO desfaz o selo: só registra o recado.
            enc = encerrar_prenotacao_do_ato_apos_arquivamento(bd, int(ato_id))
        if enc and enc.get("encerrou"):
            try:
                audit(
                    "RI_PROTOCOLO_ENCERRADO", "RI_PROTOCOLO",
                    enc["protocolo_id"],
                    {"situacao": "ENCERRADO", "numero": enc["numero"],
                     "via": "arquivamento_16.39", "ato_id": int(ato_id),
                     "selo_arquivamento": r["numero"]})
            except Exception:
                pass
        frase_enc = recado_do_encerramento_por_arquivamento(enc)
        return {"ok": True, "numero": r["numero"], "folhas": q,
                "recado": (f" Arquivamento {r['numero']} ({q} folha(s))."
                           f"{frase_enc}"),
                "prenotacao_encerrada": enc}


    @app.route("/registro-imoveis/protocolo", methods=["GET", "POST"])
    @login_required
    @roles_required(*PRATICA, metodos=("POST",))
    def ri_protocolo():
        if request.method == "POST":
            if request.form.get("acao") == "encerrar":
                # F11: encerrar exige motivo e papel; situações controladas.
                from flask import session as _sess
                papel = (getattr(getattr(request, "user", None), "role", None)
                         or _sess.get("role") or "")
                # fallback: current_user via extensions
                try:
                    cu = app.extensions.get("current_user")
                    u = cu() if cu else None
                    if u:
                        papel = u["role"] if "role" in u.keys() else papel
                except Exception:
                    pass
                if str(papel).upper() not in ("ADMIN", "MANAGER"):
                    flash("Encerrar prenotação é do oficial ou do gerente — "
                          "não do balcão.", "danger")
                    return redirect(url_for("ri_protocolo"))
                # LD13: «abc» era 500; 30 dígitos davam «marcado como
                # encerrado» sem nada encerrado. O vazio segue o 0 de antes.
                pid = numero_digitado(request.form.get("protocolo_id") or 0)
                if pid is None:
                    flash("Não achei a prenotação a encerrar: o número que veio da "
                          "tela não é de prenotação nenhuma. Nada foi encerrado.",
                          "danger")
                    return redirect(url_for("ri_protocolo"))
                motivo = (request.form.get("motivo") or "").strip()
                if len(motivo) < 5:
                    flash("Informe o motivo do encerramento (mínimo 5 caracteres). "
                          "A reabertura também exige motivo — o rastro precisa "
                          "explicar a correição.", "danger")
                    return redirect(url_for("ri_protocolo"))
                situacao = (request.form.get("situacao") or "ENCERRADO").upper()
                permitidas = {"ENCERRADO", "CANCELADO", "RECUSADO", "DEVOLVIDO"}
                if situacao not in permitidas:
                    flash(f"Situação «{situacao}» não é válida para encerrar. "
                          f"Use: {', '.join(sorted(permitidas))}.", "danger")
                    return redirect(url_for("ri_protocolo"))
                with db.transaction() as con:
                    banco(con).escrever(
                        """UPDATE ri_protocolos SET situacao=%s,
                               anotacao=COALESCE(anotacao,'') || %s
                         WHERE id=%s""",
                        (situacao,
                         f"\n[Encerrado] {motivo}",
                         pid))
                audit("RI_PROTOCOLO_ENCERRADO", "RI_PROTOCOLO", pid,
                      {"situacao": situacao, "motivo": motivo})
                flash(f"Protocolo marcado como {situacao.lower()}. Motivo registrado.",
                      "success")
                # A VENCIDA SE DECIDE NO PAINEL DOS PEDIDOS, e a decisão volta
                # para lá — quem está percorrendo a lista não perde o lugar.
                if request.form.get("voltar") == "pedidos":
                    return redirect(url_for("ri_pedidos"))
                return redirect(url_for("ri_protocolo"))

            # O LIVRO DO PROTOCOLO NAO SE ESCOLHE — e sempre o 1-A.
            #
            #   Era campo livre na tela, e o oficial reclamou dele em
            #   27/08/2026. Medindo para atende-lo: `ri_protocolos.livro` esta
            #   `1A` em **783 dos 784** registros, e o selo manda `livro: "1A"`
            #   em **829 de 829**. A unica linha com `2` e alguem tendo
            #   digitado — o campo livre convidando ao erro.
            #
            #   O livro que o balcao PRECISA escolher e outro: o de DESTINO do
            #   titulo, 2 (matriculas) ou 3 (demais atos). Sao coisas
            #   diferentes, e agora sao dois campos.
            livro = AS.LIVRO_DO_PROTOCOLO_DO_RI
            destino = (request.form.get("livro_destino") or "").strip()
            if destino not in ("2", "3"):
                flash("Diga para que livro vai o título: Livro 2 (matrículas) "
                      "ou Livro 3 (demais atos do RI).", "danger")
                return redirect(url_for("ri_protocolo"))
            # TELEFONE OU E-MAIL, PELO MENOS UM — ordem do oficial, 10/10/2026:
            # sem contato a nota devolutiva e o vencimento não chegam a ninguém.
            try:
                CONTATO.exigir(request.form.get("telefone"), request.form.get("email"))
            except CONTATO.ContatoError as e:
                flash(str(e), "danger")
                return redirect(url_for("ri_protocolo"))
            # O PROTOCOLO GERAL DE ONDE O TÍTULO VEIO, conferido ANTES de
            # prenotar: ligar a um geral que já tem prenotação trocaria a
            # ligação do outro título sem ninguém ver.
            cx_escolhido = (request.form.get("cx_protocolo_id") or "").strip()
            if cx_escolhido:
                # LD13: o «²» e os 5.000 dígitos passavam pelo `isdigit()` e
                # caíam no `int()`; agora são o «não existe» do texto.
                g = q1("SELECT id, numero, atribuicao, ri_protocolo_id FROM cx_protocolos WHERE id=%s",
                       (numero_digitado(cx_escolhido),))
                if not g or (g["atribuicao"] or "").upper() != "RI" or g["ri_protocolo_id"]:
                    flash("O protocolo geral indicado não existe, não é do Registro de "
                          "Imóveis ou já tem prenotação. Nada foi prenotado.", "danger")
                    return redirect(url_for("ri_protocolo"))
            with db.transaction() as con:
                bd = banco(con)
                bd.travar("ri_protocolos.numero")
                ultimo = bd.valor("SELECT MAX(numero) AS n FROM ri_protocolos WHERE livro=%s",
                                  (livro,))
                numero = int((ultimo or 0)) + 1
                # F10: a data da prenotação é a do momento (Lei 6.015 arts. 182/186/205).
                # Retroativa/futura digitável quebrava a prioridade.
                data = db.now()[:10]
                # Lei 6.015/73 art. 205 (red. Lei 14.382/2022) e Codigo de Normas
                # TJMA arts. 436 e 452: 20 dias UTEIS, ou 40 em REURB-S.
                # 30/09/2026: reurb_tipo S|E|MISTO — só S alonga prazo e isenta.
                tipo_reurb = (request.form.get("reurb_tipo") or "").strip().upper()
                if not tipo_reurb and request.form.get("reurb") == "1":
                    tipo_reurb = "S"
                if tipo_reurb not in ("S", "E", "MISTO"):
                    tipo_reurb = ""
                reurb = tipo_reurb == "S"
                prazo = PRAZO_PRENOTACAO_REURB if reurb else PRAZO_PRENOTACAO
                feriados = ler_feriados_locais(db.get_setting("ri_feriados_locais", ""))
                try:
                    limite = soma_dias_uteis(date.fromisoformat(data), prazo, feriados).isoformat()
                except ValueError:
                    limite = None
                mat = (request.form.get("matricula_numero") or "").strip()
                mid = None
                if mat:
                    achou = bd.um("SELECT id FROM ri_matriculas WHERE numero=%s ORDER BY id LIMIT 1",
                                  (mat,))
                    mid = achou["id"] if achou else None
                novo = bd.escrever(
                    """INSERT INTO ri_protocolos
                       (numero, livro, livro_destino, data_prenotacao, hora,
                        apresentante, apresentante_documento,
                        natureza_titulo, objeto, matricula_id, matricula_numero, data_limite,
                        telefone, email, documento_descricao,
                        reurb, reurb_tipo,
                        situacao, anotacao, origem, criado_em, criado_por)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, 'ABERTO', %s, 'MANUAL', %s, %s)
                       RETURNING id""",
                    (numero, livro, destino, data, datetime.now().strftime("%H:%M:%S"),
                     (request.form.get("apresentante") or "").strip() or None,
                     so_digitos(request.form.get("apresentante_documento")) or None,
                     (request.form.get("natureza_titulo") or "").strip() or None,
                     (request.form.get("objeto") or "").strip() or None,
                     mid, mat or None, limite,
                     (request.form.get("telefone") or "").strip() or None,
                     (request.form.get("email") or "").strip() or None,
                     (request.form.get("documento_descricao") or "").strip() or None,
                     # A MARCA FICA GRAVADA, e não só o prazo que ela produziu:
                     # prenotação com 40 dias tem de dizer por que tem 40.
                     1 if reurb else 0,
                     tipo_reurb or None,
                     (request.form.get("anotacao") or "").strip() or None,
                     db.now(), app.extensions["usuario_id"]()),  # quem prenotou (robô incluso); criado_por e FK para users(id): o NOME aqui dava 500 em toda prenotacao (06/10/2026)
                )[0]["id"]
                novo = int(novo)
                # TODA PRENOTAÇÃO TEM PROTOCOLO GERAL — decisão do oficial,
                # 12/10/2026 («criar automático»). Medido antes: das 31
                # prenotações abertas, 1 tinha protocolo geral; dos 22 gerais
                # do RI, 2 tinham prenotação. Vindo do protocolo geral (o
                # botão «Prenotar este título» da ficha dele), liga-se àquele;
                # sem ele, abre-se um aqui, na MESMA transação — prenotação sem
                # o geral é o que deixava o dinheiro e o título sem se achar.
                cx_id = numero_digitado(request.form.get("cx_protocolo_id"))
                if cx_id is not None:
                    geral = CXPROT.vincular_ri(con, cx_id, novo)
                    geral_numero = geral["protocolo_numero"]
                else:
                    geral = CXPROT.abrir(
                        con, data_abertura=data, agora=db.now(),
                        atribuicao="RI",
                        interessado=(request.form.get("apresentante") or "").strip() or None,
                        interessado_documento=so_digitos(
                            request.form.get("apresentante_documento")) or None,
                        telefone=(request.form.get("telefone") or "").strip() or None,
                        email=(request.form.get("email") or "").strip() or None,
                        assunto=f"Prenotação {numero}/{livro}",
                        observacao=((request.form.get("natureza_titulo") or "")
                                    .strip()[:240] or None),
                        criado_por=app.extensions["usuario_id"](),
                        ri_protocolo_id=novo)
                    geral_numero = geral["numero"]
                # O ANDAMENTO NO ONR («Título prenotado») se anota NA MESMA
                # transação: prenotação que não entra não deixa andamento na
                # fila. O envio é outra rotina, fora de transação — e o gancho
                # nunca derruba a prenotação (`onr_acompanhamento`).
                ACOMP.anotar_prenotacao(con, novo, agora=db.now())
            # O SELO SAI AGORA, FORA DA TRANSACAO — «o selo deve ser emitido
            # quando praticado o ato». A prenotacao E ato: tem livro, numero,
            # custas e selo proprio, e 829 dela estao no acervo.
            #
            # O PROTOCOLO QUE PAGA O SELO DELA (22/10/2026, trava do selo
            # pago): o marcado na tela, ou — vindo do «Prenotar este título» —
            # o protocolo geral que a escrevente escolheu para este título no
            # mesmo formulário. Recusa não desfaz a prenotação: a prioridade
            # se conta da hora em que o título entrou.
            _cx = numero_digitado(request.form.get("cx_protocolo_id"))
            recusa = _atender_o_protocolo_escolhido({"protocolo_selo": (
                request.form.get("protocolo_selo")
                or (str(_cx) if _cx is not None else ""))})
            if recusa:
                flash(recusa, "warning")
            selado = _selar_a_prenotacao(novo, numero, request.form)
            audit("RI_PRENOTACAO", "RI_PROTOCOLO", novo,
                  {"numero": numero, "livro": livro, "livro_destino": destino,
                   "matricula": mat, "prazo_dias_uteis": prazo,
                   "reurb": reurb, "reurb_tipo": tipo_reurb or None,
                   "limite": limite})
            flash(f"Protocolo {numero} prenotado em {data}. Prazo de {prazo} dias úteis"
                  f"{' (REURB-' + (tipo_reurb or 'S') + ')' if tipo_reurb else ''}: vence em {limite}. "
                  f"Protocolo geral {geral_numero}.{selado}",
                  "success")
            return redirect(url_for("ri_protocolo"))

        situacao = (request.args.get("situacao") or "").strip().upper()
        busca = (request.args.get("busca") or "").strip()
        onde, params = ["1=1"], []
        if situacao:
            onde.append("p.situacao = %s")
            params.append(situacao)
        if busca:
            onde.append("(CAST(p.numero AS TEXT) ILIKE %s OR p.objeto ILIKE %s "
                        "OR p.apresentante ILIKE %s OR p.matricula_numero ILIKE %s)")
            params += [f"%{busca}%"] * 4
        filtro = " AND ".join(onde)

        rows = q(f"""SELECT p.*, m.id mid FROM ri_protocolos p
                     LEFT JOIN ri_matriculas m ON m.id = p.matricula_id
                     WHERE {filtro} ORDER BY p.livro, p.numero DESC LIMIT 300""", params)
        resumo = q1("""SELECT COUNT(*) total,
                    COALESCE(SUM(CASE WHEN situacao='ABERTO' THEN 1 ELSE 0 END),0)::bigint abertos,
                    COALESCE(SUM(CASE WHEN situacao='ABERTO' AND data_limite < %s AND prazo_suspenso_desde IS NULL THEN 1 ELSE 0 END),0)::bigint vencidos,
                    COALESCE(SUM(CASE WHEN apresentante IS NULL THEN 1 ELSE 0 END),0)::bigint sem_apresentante
                    FROM ri_protocolos""", (date.today().isoformat(),))
        feriados = ler_feriados_locais(db.get_setting("ri_feriados_locais", ""))
        hoje = date.today()
        restam = {}
        for r in rows:
            if (r["situacao"] == "ABERTO" and r["data_limite"]
                    and not PRAZO.suspensa(r)):
                try:
                    restam[r["id"]] = dias_uteis_entre(hoje, date.fromisoformat(r["data_limite"]), feriados)
                except ValueError:
                    pass
        # VINDO DO PROTOCOLO GERAL («Prenotar este título»), o formulário abre
        # preenchido com quem já se identificou no balcão — e leva o número do
        # geral escondido, para a prenotação se ligar a ele e não abrir outro.
        de_cx = None
        cx_arg = numero_digitado(request.args.get("cx"))
        if cx_arg is not None:
            de_cx = q1("""SELECT * FROM cx_protocolos WHERE id=%s AND atribuicao='RI'
                          AND ri_protocolo_id IS NULL""", (cx_arg,))
        return render_template("ri_protocolo.html", rows=rows, resumo=resumo,
                               de_cx=dict(de_cx) if de_cx else None,
                               situacao=situacao, busca=busca, hoje=hoje.isoformat(),
                               prazo=PRAZO_PRENOTACAO, prazo_reurb=PRAZO_PRENOTACAO_REURB,
                               restam=restam,
                               MOTIVOS_DA_GRATUIDADE_DO_RI=AS.MOTIVOS_DA_GRATUIDADE_DO_RI)

    # ===================================== a tela do título, com o que corrigir
    #
    # POR QUE ESTA TELA PASSOU A EXISTIR
    #     O protocolo do Registro de Imóveis só tinha lista. Dava para prenotar
    #     e dava para encerrar — e mais nada. Encerrado por engano, não havia
    #     como voltar atrás; digitado errado, não havia como corrigir.
    #
    #     Um título encerrado por engano é uma prenotação que sumiu do prazo sem
    #     ter perdido o prazo. Não dá para "abrir outro": o número de ordem é o
    #     que garante a prioridade do direito (Lei 6.015/73, art. 186), e abrir
    #     outro joga o título para o fim da fila.
    #
    # A CORREÇÃO SE DOCUMENTA, NÃO SE ESCONDE
    #     Reabrir não apaga o encerramento: grava que houve um, qual era a
    #     situação, quem reabriu, quando e por quê. Prenotação é ato de livro, e
    #     correição pergunta.

    def _protocolo_ou_404(protocolo_id: int):
        p = q1("SELECT * FROM ri_protocolos WHERE id=%s", (protocolo_id,))
        if not p:
            abort(404)
        return p

    CAMPOS_EDITAVEIS = (
        ("apresentante", "Apresentante"),
        ("apresentante_documento", "CPF/CNPJ do apresentante"),
        ("natureza_titulo", "Natureza do título"),
        ("objeto", "Objeto"),
        ("matricula_numero", "Matrícula"),
        ("telefone", "Telefone"),
        ("email", "E-mail"),
        ("documento_descricao", "Documento apresentado"),
        ("anotacao", "Anotação"),
    )

    @app.route("/registro-imoveis/protocolo/<int:protocolo_id>",
               methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    # O AUDITOR ve a tela; o que ela GRAVA (POST) exige papel que pratica ato.
    @roles_required("ADMIN", "MANAGER", "USER", metodos=("POST",))
    def ri_protocolo_ver(protocolo_id):
        p = _protocolo_ou_404(protocolo_id)

        if request.method == "POST":
            acao = request.form.get("acao")

            # ------------------------------------------------------ reabrir
            if acao == "reabrir":
                motivo = (request.form.get("motivo") or "").strip()
                if len(motivo) < 10:
                    flash("Diga por que está reabrindo, com pelo menos dez "
                          "letras. Reabertura de prenotação é correção de ato de "
                          "livro: o motivo é o que se mostra na correição.",
                          "danger")
                    return redirect(url_for("ri_protocolo_ver",
                                            protocolo_id=protocolo_id))
                if p["situacao"] == "ABERTO":
                    flash("Este protocolo já está aberto.", "warning")
                    return redirect(url_for("ri_protocolo_ver",
                                            protocolo_id=protocolo_id))
                with db.transaction() as con:
                    banco(con).escrever(
                        """UPDATE ri_protocolos
                           SET situacao='ABERTO', situacao_anterior=%s,
                               reaberto_em=%s, reaberto_por=%s, motivo_reabertura=%s
                           WHERE id=%s""",
                        (p["situacao"], db.now(),
                         app.extensions["usuario_nome"](), motivo, protocolo_id))
                audit("RI_PROTOCOLO_REABERTO", "RI_PROTOCOLO", protocolo_id,
                      {"numero": p["numero"], "de": p["situacao"], "para": "ABERTO",
                       "motivo": motivo})
                # O PRAZO NÃO É RECALCULADO, e é o ponto todo.
                #   A prenotação vale 20 dias úteis contados do lançamento no
                #   protocolo — não do dia em que alguém corrigiu um erro de
                #   digitação. Reabrir devolvendo prazo novo seria usar a
                #   correção para esticar a prioridade do título.
                flash(f"Protocolo {p['numero']} reaberto. O prazo continua o "
                      f"mesmo: a prenotação corre desde {fmt_date(p['data_prenotacao'])} "
                      f"e vence em {fmt_date(p['data_limite'])} — reabrir corrige "
                      f"o engano, não devolve prazo.", "success")
                return redirect(url_for("ri_protocolo_ver",
                                        protocolo_id=protocolo_id))

            # ------------------------------------------------------- editar
            if acao == "editar":
                mudou = {}
                sets, valores = [], []
                for campo, rotulo in CAMPOS_EDITAVEIS:
                    if campo not in request.form:
                        continue
                    novo = (request.form.get(campo) or "").strip() or None
                    if campo == "apresentante_documento":
                        novo = so_digitos(novo) or None
                    antigo = p[campo] if campo in p.keys() else None
                    if (antigo or None) == novo:
                        continue
                    sets.append(f"{campo}=%s")
                    valores.append(novo)
                    mudou[rotulo] = {"antes": antigo, "depois": novo}
                if not mudou:
                    flash("Nada foi alterado.", "warning")
                    return redirect(url_for("ri_protocolo_ver",
                                            protocolo_id=protocolo_id))
                with db.transaction() as con:
                    # Mudou o número da matrícula: reamarra o vínculo interno.
                    # Sem isto o protocolo mostraria uma matrícula no texto e
                    # continuaria ligado a outra por dentro — que é pior do que
                    # não estar ligado a nenhuma, porque parece certo.
                    bd = banco(con)
                    novo_mat = (request.form.get("matricula_numero") or "").strip()
                    if "matricula_numero=%s" in sets:
                        achou = bd.um(
                            "SELECT id FROM ri_matriculas WHERE numero=%s ORDER BY id LIMIT 1",
                            (novo_mat,)) if novo_mat else None
                        sets.append("matricula_id=%s")
                        valores.append(achou["id"] if achou else None)
                    bd.escrever(
                        f"UPDATE ri_protocolos SET {', '.join(sets)} WHERE id=%s",
                        valores + [protocolo_id])
                # A AUDITORIA GUARDA O ANTES E O DEPOIS, e não só "editado".
                #   "Protocolo 11548 editado" não responde a pergunta que a
                #   correição faz, que é o que estava escrito antes.
                audit("RI_PROTOCOLO_EDITADO", "RI_PROTOCOLO", protocolo_id,
                      {"numero": p["numero"], "alteracoes": mudou})
                flash(f"{len(mudou)} campo(s) corrigido(s): "
                      f"{', '.join(mudou)}. O que estava escrito antes ficou na "
                      f"auditoria.", "success")
                return redirect(url_for("ri_protocolo_ver",
                                        protocolo_id=protocolo_id))

            # ---------------------------------------------- depósito prévio
            if acao == "deposito":
                valor = centavos(request.form.get("valor"))
                depositante = ((request.form.get("depositante") or "").strip()
                               or (p["apresentante"] or "").strip())
                operador = app.extensions["usuario_nome"]()
                aberto = q1("""SELECT * FROM cx_caixas WHERE operador_nome=%s
                               AND situacao='ABERTO' ORDER BY data DESC LIMIT 1""",
                            (operador,))
                with db.transaction() as con:
                    try:
                        feito = DEP.criar(
                            con, valor_centavos=valor, depositante=depositante,
                            agora=db.now(),
                            documento=(request.form.get("depositante_documento")
                                       or p["apresentante_documento"]),
                            observacao=(request.form.get("observacao") or
                                        f"Depósito prévio do título "
                                        f"{p['numero']}/{p['livro']}"),
                            forma_pagamento=request.form.get("forma_pagamento"),
                            caixa_id=aberto["id"] if aberto else None,
                            ri_protocolo_id=protocolo_id)
                    except ValueError as erro:
                        flash(str(erro), "danger")
                        return redirect(url_for("ri_protocolo_ver",
                                                protocolo_id=protocolo_id))
                audit("DEPOSITO_PREVIO_CRIADO", "DEPOSITO", feito["id"],
                      {"numero": feito["numero"], "valor": feito["valor"],
                       "ri_protocolo": p["numero"], "depositante": depositante})
                flash(f"Depósito {feito['numero']} — R$ {feito['valor']} — "
                      f"registrado no título {p['numero']}"
                      + (" e lançado no caixa do dia." if feito["lancado_no_caixa"]
                         else ". ATENÇÃO: não há caixa aberto no seu nome, então "
                              "ele não entrou no movimento do dia. Abra o caixa e "
                              "lance a entrada, senão a gaveta não fecha."),
                      "success" if feito["lancado_no_caixa"] else "warning")
                return redirect(url_for("ri_protocolo_ver",
                                        protocolo_id=protocolo_id))

            # ----------------------------------- caixa / orçamento (#89)
            if acao == "abrir_caixa":
                with db.connect() as con:
                    ligado = RITEOR.caixa_ligado_a_prenotacao(con, protocolo_id)
                if ligado:
                    return redirect(url_for("caixa_protocolo",
                                            protocolo_id=ligado["id"]))
                with db.transaction() as con:
                    feito = CXPROT.abrir(
                        con,
                        data_abertura=date.today().isoformat(),
                        agora=db.now(),
                        atribuicao="RI",
                        interessado=(p["apresentante"] or "").strip() or None,
                        interessado_documento=p["apresentante_documento"],
                        telefone=(p["telefone"] if "telefone" in p.keys()
                                  else None),
                        email=(p["email"] if "email" in p.keys() else None),
                        assunto=(f"Prenotação {p['numero']}/{p['livro'] or '1A'}"
                                 .strip()),
                        observacao=(((p["objeto"] if "objeto" in p.keys()
                                      else None) or "").strip()[:240]
                                    or None),
                        ri_protocolo_id=protocolo_id,
                    )
                audit("RI_PRENOTACAO_CAIXA_ABERTO", "RI_PROTOCOLO",
                      protocolo_id,
                      {"caixa_protocolo_id": feito["protocolo_id"],
                       "caixa_numero": feito["numero"]})
                flash(
                    f"Protocolo de caixa {feito['numero']} aberto e vinculado "
                    f"a este título — acrescente os serviços e emita o "
                    f"orçamento sem sair da prenotação pelo painel "
                    f"«Emolumentos e orçamento».",
                    "success")
                return redirect(url_for("ri_protocolo_ver",
                                        protocolo_id=protocolo_id))

            flash("Ação desconhecida.", "danger")
            return redirect(url_for("ri_protocolo_ver", protocolo_id=protocolo_id))

        # ------------------------------------------------------------- GET
        with db.connect() as con:
            depositos = DEP.do_titulo(con, protocolo_id)
        saldo = DEP.saldo_do_titulo(depositos)
        feriados = ler_feriados_locais(db.get_setting("ri_feriados_locais", ""))
        restam = None
        if (p["situacao"] == "ABERTO" and p["data_limite"]
                and not PRAZO.suspensa(p)):
            try:
                restam = dias_uteis_entre(date.today(),
                                          date.fromisoformat(p["data_limite"]),
                                          feriados)
            except ValueError:
                restam = None
        notas = q("""SELECT * FROM ri_notas_devolutivas WHERE protocolo_id=%s
                     ORDER BY id DESC""", (protocolo_id,))
        with db.connect() as _q:
            qualificacoes = PED.qualificacoes_de(_q, protocolo_id)
        etapa_do_pedido = PED.etapa(p, qualificacoes[-1] if qualificacoes else None,
                                    date.today().isoformat())
        # O histórico sai da auditoria que o sistema já grava — não de uma
        # segunda tabela só para esta tela. Duas verdades sobre o mesmo ato é
        # como se perde a que vale.
        historico = q("""SELECT ts, username_snapshot AS quem, action, details,
                                agente, a_mando_de
                         FROM audit_logs
                         WHERE entity_type='RI_PROTOCOLO' AND entity_id=%s
                         ORDER BY id DESC LIMIT 30""", (protocolo_id,))
        with db.connect() as _c:
            documentos = RDOC.documentos_de(_c, RDOC.ENTIDADE_RI, protocolo_id)
        caixa_ligado = None
        caixa_atos: list[dict] = []
        caixa_soma = None
        caixa_protocolo_id = None
        with db.connect() as _cx:
            res_caixa = RITEOR.resolver_protocolo_caixa(
                _cx, ri_protocolo_id=protocolo_id)
            caixa_ligado = res_caixa.get("caixa")
            caixa_protocolo_id = res_caixa.get("protocolo_caixa_id")
            if caixa_protocolo_id:
                caixa_atos = [
                    dict(r) for r in banco(_cx).ler(
                        """SELECT * FROM cx_protocolo_atos
                           WHERE protocolo_id=%s ORDER BY id""",
                        (int(caixa_protocolo_id),))]
                if caixa_atos:
                    caixa_soma = EMOL.somar_itens(caixa_atos)
        # OS DOCUMENTOS PARA QUALIFICACAO do Protocolo Geral ligado — relato
        # #135, 15/10/2026: a tarefa 386 guardava os papeis da prenotacao
        # 11.573 numa pasta fora do sistema. So os ativos; so LE.
        docs_protocolo_geral = []
        if caixa_protocolo_id:
            import protocolo_documentos as PDOC
            with db.connect() as _pd:
                docs_protocolo_geral = PDOC.documentos(
                    _pd, int(caixa_protocolo_id))["ativos"]
        # O QUE ESTE TÍTULO JÁ DISSE AO ONR (Acompanhamento de Títulos) — só lê.
        with db.connect() as _ac:
            acompanhamento_onr = ACOMP.da_prenotacao(_ac, protocolo_id)
        return render_template("ri_protocolo_ver.html", p=dict(p),
                               acompanhamento_onr=acompanhamento_onr,
                               documentos=documentos, e_imagem=RDOC.e_imagem,
                               docs_protocolo_geral=docs_protocolo_geral,
                               depositos=depositos, saldo=reais(saldo),
                               restam=restam, notas=notas, historico=historico,
                               TIPOS_DO_TITULO=RND.TIPOS_DE_DOCUMENTO,
                               ROTULO_DO_TIPO=RND.ROTULO_DO_TIPO,
                               nota_aberta=next((n for n in notas
                                                 if n["situacao"] == "ABERTA"), None),
                               nota_recusa=RND.por_que_nao_emite(p),
                               qualificacoes=qualificacoes,
                               etapa_do_pedido=etapa_do_pedido,
                               ROTULO_DA_ETAPA=PED.ROTULO_DA_ETAPA,
                               campos=CAMPOS_EDITAVEIS,
                               SITUACOES_PROTOCOLO=("ABERTO", "ENCERRADO",
                                                    "CANCELADO", "DEVOLVIDO"),
                               prazo_suspenso=PRAZO.suspensa(p),
                               MOTIVOS_SUSPENSAO=PRAZO.MOTIVOS,
                               caixa_ligado=caixa_ligado,
                               caixa_protocolo_id=caixa_protocolo_id,
                               caixa_atos=caixa_atos,
                               caixa_soma=caixa_soma)

    # ======================================= os pedidos de ato, numa tela só
    #
    # Pedido do oficial em 12/10/2026, com as quatro decisões dele: painel
    # próprio, protocolo geral automático, vencida marcada e decidida por
    # gente, só o RI primeiro. A etapa se CALCULA (`ri_pedidos.etapa`); o que
    # se grava é a qualificação. Ver o docstring de `ri_pedidos`.

    @app.route("/registro-imoveis/pedidos")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def ri_pedidos():
        filtro = (request.args.get("etapa") or "").strip().upper()
        with db.connect() as con:
            dados = PED.listar(con, hoje=date.today(), feriados=_feriados())
        pedidos = dados["pedidos"]
        if filtro in PED.ROTULO_DA_ETAPA:
            pedidos = [x for x in pedidos if x["etapa"] == filtro]
        else:
            filtro = ""
        return render_template("ri_pedidos.html", pedidos=pedidos,
                               contagem=dados["contagem"], ETAPAS=PED.ETAPAS,
                               ROTULO_DA_ETAPA=PED.ROTULO_DA_ETAPA,
                               filtro=filtro, reais=reais)

    @app.route("/registro-imoveis/protocolo/<int:protocolo_id>/qualificar",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_qualificar(protocolo_id):
        """Qualificação POSITIVA — o título está apto para registro.

        A negativa não passa por aqui: ela é a nota devolutiva, e a rota da
        nota grava a qualificação na mesma transação.
        """
        _protocolo_ou_404(protocolo_id)
        quem = (app.extensions["usuario_nome"]() or "").strip() or None
        try:
            with db.transaction() as con:
                feito = PED.qualificar_positiva(
                    con, protocolo_id,
                    fundamentacao=request.form.get("fundamentacao"),
                    quem=quem, usuario_id=app.extensions["usuario_id"](),
                    agora=db.now())
        except PED.PedidoError as erro:
            flash(str(erro), "danger")
        else:
            audit("RI_QUALIFICACAO_POSITIVA", "RI_PROTOCOLO", protocolo_id,
                  {"ordem": feito["ordem"]})
            flash(f"Qualificação positiva registrada ({feito['ordem']}ª). O título "
                  f"está apto para registro — o ato se lavra na matrícula, com "
                  f"número, selo e custas.", "success")
        if request.form.get("voltar") == "pedidos":
            return redirect(url_for("ri_pedidos"))
        return redirect(url_for("ri_protocolo_ver", protocolo_id=protocolo_id))

    @app.route("/registro-imoveis/protocolo/<int:protocolo_id>/prazo",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def ri_protocolo_prazo(protocolo_id):
        """Suspende ou retoma o prazo da prenotacao (TJMA 452, § 3º)."""
        antes = _protocolo_ou_404(protocolo_id)
        acao = request.form.get("acao")
        quem = (app.extensions["usuario_nome"]() or "").strip() or None
        try:
            with db.transaction() as con:
                if acao == "suspender":
                    motivo = request.form.get("motivo") or ""
                    PRAZO.suspender(con, protocolo_id, motivo=motivo,
                                    quem=quem, hoje=date.today())
                    feito = {"acao": "suspender", "motivo": motivo}
                    # Suspensão por DÚVIDA é a «Suscitação de dúvida» do ONR;
                    # as outras hipóteses não têm status lá (o gancho confere).
                    ACOMP.anotar_duvida(con, protocolo_id, agora=db.now())
                elif acao == "retomar":
                    feito = {"acao": "retomar"} | PRAZO.retomar(
                        con, protocolo_id, quem=quem, hoje=date.today(),
                        feriados=_feriados())
                    # A retomada empurra o limite: é o «Prorrogado o prazo da
                    # prenotação» do ONR (sem dia a mais, nada se anota).
                    ACOMP.anotar_prorrogacao(
                        con, protocolo_id, de=antes["data_limite"],
                        para=feito["data_limite"], dias=feito["dias"], agora=db.now())
                else:
                    raise PRAZO.PrazoError("Ação desconhecida.")
        except PRAZO.PrazoError as erro:
            flash(str(erro), "danger")
        else:
            audit("RI_PRENOTACAO_PRAZO", "RI_PROTOCOLO", protocolo_id, feito)
            flash("Prazo da prenotação suspenso — não corre até ser retomado."
                  if acao == "suspender" else
                  f"Contagem retomada: +{feito['dias']} dia(s) útil(eis); "
                  f"novo limite {fmt_date(feito['data_limite'])}.", "success")
        return redirect(url_for("ri_protocolo_ver", protocolo_id=protocolo_id))

    @app.route("/registro-imoveis/protocolo/<int:protocolo_id>/comprovante")
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_prenotacao_comprovante(protocolo_id):
        """Comprovante de prenotação — a via que fica com o apresentante.

        É o que prova a prioridade: quem apresentou primeiro, e até quando o
        título a conserva. Sai do cartório, então CPF, telefone e e-mail vão
        mascarados (Lei 13.709/2018, art. 6º, III).
        """
        p = q1("SELECT * FROM ri_protocolos WHERE id=%s", (protocolo_id,))
        if not p:
            abort(404)
        from jinja2.sandbox import SandboxedEnvironment
        env = SandboxedEnvironment(autoescape=False)
        # Quem emitiu e em que funcao — pela sessao, e nao por um atributo que
        # ninguem definia. Ver `app.py`: o comprovante de prenotacao saia com o
        # nome da substituta e a funcao "Escrevente" para todo mundo.
        usuario = app.extensions["usuario_nome"]()
        funcao = app.extensions["usuario_funcao"]()
        import ri_frases
        with db.connect() as _c:
            _modelo = MODELOS.corpo_de(_c, "RI_PRENOTACAO")
            _modelo_suspenso = ri_frases.texto("RI_PRENOTACAO_PRAZO_SUSPENSO", _c)
        limite = fmt_date(p["data_limite"]) if p["data_limite"] else ""
        suspenso = PRAZO.suspensa(p)
        if suspenso:
            # O modelo e editavel pela casa e so conhece `limite`/`faltam`: a
            # suspensao vai no proprio texto do limite, e `faltam` some para
            # o papel nao dizer «prazo vencido» de prenotacao viva.
            #
            # A FRASE MORA NA BASE — LF06B (`RI_PRENOTACAO_PRAZO_SUSPENSO`);
            # quando ela entra e o nome do motivo continuam sendo daqui.
            limite = ri_frases.montar(
                _modelo_suspenso, limite=limite,
                desde=fmt_date(p['prazo_suspenso_desde']),
                motivo=PRAZO.MOTIVOS.get(p['prazo_suspenso_motivo'],
                                         p['prazo_suspenso_motivo'])).strip(" —")
        html = env.from_string(_modelo).render(
            p=dict(p), sv=dados_serventia(db.get_settings),
            documento=mascarar_documento(p["apresentante_documento"]),
            telefone=mascarar_telefone(p["telefone"]),
            email=mascarar_email(p["email"]),
            data=fmt_date(p["data_prenotacao"]),
            limite=limite,
            # O PRAZO SAI DO PROPRIO REGISTRO, e nao de uma constante.
            #
            #   Estava `PRAZO_PRENOTACAO` fixo — 20 dias. O REURB-S tem 40
            #   (Codigo de Normas TJMA, art. 452), e o comprovante dele saia
            #   dizendo 20: o papel que o cliente leva para casa afirmando um
            #   prazo menor do que o que ele tem. Estava no backlog do balcao
            #   desde a revisao do RI.
            #
            #   Contar do que foi GRAVADO acerta os dois casos sem perguntar
            #   qual e qual: a data-limite ja foi calculada quando a prenotacao
            #   nasceu, com os feriados da casa.
            prazo=_prazo_gravado(p) or PRAZO_PRENOTACAO,
            faltam=None if suspenso else _dias_que_faltam(p),
            hoje_extenso=data_por_extenso(date.today()),
            emitido_por=usuario, funcao=funcao)
        # **O CARIMBO DO SELO NO COMPROVANTE — 22/09/2026, ordem do
        # oficial: «comprovante da prenotacao tem que sair carimbo do selo
        # completo».**
        #
        # A tabela do comprovante trazia uma linha «Selo» com o NUMERO e mais
        # nada — o mesmo que as certidoes traziam antes de 17/09. Medido no
        # razao: esta casa comprou **835 selos** em `/selo/imovel/prenotacao`,
        # e o papel que o apresentante leva nao dizia o ato, a data, as partes
        # nem quanto se cobrou. Numero de selo sozinho nao se confere.
        #
        # **O FEITIO E O DA CERTIDAO, e nao o do livro.** A ordem de 16/09
        # tirou o QR e o link do carimbo do ATO — e ela e sobre o livro
        # fisico, que fica na estante desta casa. Este papel SAI do cartorio,
        # e quem o le e o apresentante, o banco e o comprador: para eles o
        # atalho de conferencia e justamente o que serve. E o mesmo desenho
        # das quatro certidoes.
        #
        # **A ETIQUETA VEM DO RAZAO, E NAO DA COLUNA.** `selo_prenotacao`
        # guarda o numero de 28 caracteres; quem tem o texto do aparelho e
        # `sd_selos` — e e `etiqueta_do_ato` que sabe procura-lo. Medido em
        # 22/09/2026 nas 803 prenotacoes: **771 devolvem a etiqueta inteira**,
        # 14 devolvem so o numero (o razao nao guardou o texto daquelas) e
        # **nenhuma devolve vazio**. Quem nao tem texto sai com o numero, que
        # e o que se digita — carimbo com o numero cru e melhor que nenhum.
        with db.connect() as _c:
            etiqueta = AS.etiqueta_do_ato(
                _c, "ri_protocolos", protocolo_id,
                (p["selo_prenotacao"] or "").strip())
        frag_do_selo, imagens_do_selo = carimbo_da_certidao_odf(
            etiqueta, rotulo="SELO DA PRENOTAÇÃO",
            prefixo="qr-selo-prenotacao")
        arquivo = gerar_odt(html_para_odf(html) + frag_do_selo,
                            titulo=f"Prenotação {p['numero']}",
                            imagens=imagens_do_selo or None)
        audit("RI_PRENOTACAO_COMPROVANTE", "RI_PROTOCOLO", protocolo_id,
              {"numero": p["numero"]})
        return Response(arquivo, mimetype="application/vnd.oasis.opendocument.text",
                        headers={"Content-Disposition":
                                 f'attachment; filename="prenotacao-{p["numero"]}.odt"'})

    # ------------------------------------------------------------ CNIB

    @app.route("/registro-imoveis/cnib")
    @login_required
    def ri_cnib():
        busca = (request.args.get("busca") or "").strip()
        achados = []
        if busca:
            with db.connect() as con:
                achados = consultar_cnib(con, [busca], [busca])
            audit("RI_CNIB_CONSULTADA", "RI_CNIB", None,
                  {"busca": busca, "achados": len(achados)})
        base_data, base_n = cnib_referencia()
        return render_template("ri_cnib.html", busca=busca, achados=achados,
                               base_data=base_data, base_n=base_n)

    @app.route("/registro-imoveis/<int:matricula_id>/cnib/resolver", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_cnib_resolver(matricula_id):
        decisao = request.form.get("decisao") or ""
        try:
            with db.transaction() as con:
                decisao_id = CNIB.resolver_ocorrencia(
                    con, matricula_id=matricula_id,
                    protocolo=request.form.get("protocolo_cnib"),
                    pessoa_nome=request.form.get("pessoa_nome"),
                    pessoa_documento=request.form.get("pessoa_documento"),
                    decisao=decisao, motivo=request.form.get("motivo"),
                    quem=_usuario_atual(), agora=db.now())
        except CNIB.CnibError as e:
            flash(str(e), "danger")
        except sqlite3.IntegrityError:
            flash("Esta ocorrencia ja tinha uma decisao registrada.", "success")
        else:
            audit("RI_CNIB_DECIDIDA", "RI_CNIB_DECISAO", decisao_id,
                  {"matricula_id": matricula_id, "decisao": decisao})
            flash("Conferencia registrada com responsavel e motivo. Esta ocorrencia saiu do aviso; minutas vinculadas ainda nao lavradas foram retiradas da fila.", "success")
        return redirect(url_for("ri_ficha", matricula_id=matricula_id) + "#cnib-historico")

    @app.route("/registro-imoveis/cnib/pendentes", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_cnib_pendentes():
        """As ordens que atingem parte de matricula desta casa, com o texto pronto.

        «AVISAR E PREPARAR A AVERBACAO, FICANDO PENDENTE OKAY DO CARTORIO» —
        decisao do oficial em 28/08/2026, quando perguntei se o sistema devia
        averbar sozinho. O trabalho fica pronto; quem assina decide.

        A LISTA E CALCULADA, E NAO GUARDADA. O que se guarda e a DECISAO — e e
        so por isso que a lista diminui. Guardar a pendencia faria uma segunda
        verdade sobre o mesmo fato, que envelheceria quando a copia do CNIB
        fosse trocada.
        """
        if request.method == "POST":
            # LD13: «abc» era 500, e 30 dígitos estouravam no INSERT da decisão.
            matricula_da_ordem = numero_digitado(request.form.get("matricula_id") or 0)
            if matricula_da_ordem is None:
                flash("A matrícula desta ordem não veio certa da tela. Abra a "
                      "lista de novo e decida por ela.", "danger")
                return redirect(url_for("ri_cnib_pendentes"))
            try:
                with db.transaction() as con:
                    decisao_id = CNIB.decidir(
                        con,
                        matricula_id=matricula_da_ordem,
                        ordem={
                            "protocolo_cnib": request.form.get("protocolo_cnib"),
                            "nome": request.form.get("pessoa_nome"),
                            "documento": request.form.get("pessoa_documento"),
                            "criterio": request.form.get("criterio"),
                        },
                        decisao=CNIB.NAO_E_A_PESSOA,
                        motivo=request.form.get("motivo"),
                        ato_id=None,
                        # O MESMO caminho que a auditoria usa para saber
                        # quem foi — e nao um campo digitado na tela.
                        quem=_usuario_atual(),
                        agora=db.now())
            except CNIB.CnibError as e:
                flash(str(e), "danger")
                return redirect(url_for("ri_cnib_pendentes"))
            except sqlite3.IntegrityError:
                # O `UNIQUE` do banco pegando o duplo clique. Nao e erro do
                # operador, e nao vale assustar quem so clicou duas vezes.
                flash("Esta ordem já tinha sido resolvida.", "success")
                return redirect(url_for("ri_cnib_pendentes"))
            audit("RI_CNIB_DECIDIDA", "RI_CNIB_DECISAO", decisao_id,
                  {"decisao": CNIB.NAO_E_A_PESSOA})
            flash("Anotado: esta ordem não atinge esta matrícula, e o motivo "
                  "ficou registrado. Ela sai da lista.", "success")
            return redirect(url_for("ri_cnib_pendentes"))

        with db.connect() as con:
            pendentes = CNIB.pendentes(con)
        base_data, base_n = cnib_referencia()
        return render_template("ri_cnib_pendentes.html", pendentes=pendentes,
                               base_data=base_data, base_n=base_n,
                               cnib_idade=cnib_idade(base_data),
                               cnib_dias_para_avisar=CNIB_DIAS_PARA_AVISAR)

    def _pasta_dos_documentos(protocolo_numero: str):
        """Onde o documento do protocolo fica guardado.

        Dentro da pasta de arquivos que o backup ja varre — a mesma decisao das
        fichas digitalizadas. Documento que so existe fora do backup e
        documento que se perde na primeira troca de maquina.
        """
        raiz = Path(db.get_setting("archive_root", "").strip()
                    or (Path(db.db_path).parent / "arquivos"))
        destino = raiz / "ri" / "prenotacoes" / _nome_seguro(protocolo_numero)
        destino.mkdir(parents=True, exist_ok=True)
        return destino

    def _nome_seguro(texto) -> str:
        limpo = "".join(c if (c.isalnum() or c in "-_.") else "_"
                        for c in str(texto or "sem-numero"))
        return limpo[:60] or "sem-numero"

    @app.route("/registro-imoveis/prenotacao/<int:protocolo_id>/documento",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_prenotacao_documento(protocolo_id):
        """Anexa o título apresentado à prenotação — o relato #25 do oficial.

        «protocolo precisa permitir anexar documentos e visualizar esses
         documentos. E o ato em que se vincula a esse determinado protocolo
         precisa poder visualizar os documentos anexos ao protocolo, até para
         facilitar a lavratura do ato»
        """
        p = _protocolo_ou_404(protocolo_id)
        arquivos = [f for f in request.files.getlist("documento") if f and f.filename]
        if not arquivos:
            flash("Escolha o arquivo antes de anexar.", "danger")
            return redirect(url_for("ri_protocolo_ver", protocolo_id=protocolo_id))
        descricao = (request.form.get("descricao") or "").strip() or None
        tipo = (request.form.get("tipo") or "").strip() or None
        if tipo and tipo not in RND.ROTULO_DO_TIPO:
            flash(f"«{tipo}» não é um tipo de documento que eu conheça.", "danger")
            return redirect(url_for("ri_protocolo_ver", protocolo_id=protocolo_id))
        # O ANEXO PODE SER A NOTA, OU O CUMPRIMENTO DELA — 25/10/2026. Medido: das
        # notas desta casa, as feitas em Word só eram anexadas, e o protocolo ficava
        # ABERTO, sem prazo de exigência; nenhuma tinha sido cadastrada pela tela.
        if tipo == RND.NOTA:
            return _emitir_nota_devolutiva(p, arquivos=arquivos, descricao=descricao)
        if tipo == RND.CUMPRIMENTO:
            with db.connect() as _c:
                aberta = RND.nota_aberta(_c, protocolo_id)
            if aberta:
                return _registrar_reingresso(aberta, p, arquivos=arquivos, descricao=descricao)
        ids, nomes = _anexar_ao_protocolo(p, arquivos, descricao, tipo=tipo)
        if tipo == RND.CUMPRIMENTO:
            flash("Não há nota devolutiva aguardando cumprimento neste protocolo: o "
                  "documento foi anexado como cumprimento de exigência, sem registrar "
                  "reingresso.", "warning")
            return redirect(url_for("ri_protocolo_ver", protocolo_id=protocolo_id))
        if len(nomes) == 1:
            flash(f"{nomes[0]} anexado a prenotacao {p['numero']}. "
                  f"Ele aparece na tela de lavrar o ato que sair deste protocolo.",
                  "success")
        else:
            flash(f"{len(nomes)} arquivos anexados a prenotacao {p['numero']}: "
                  f"{', '.join(nomes)}. Aparecem na tela de lavrar o ato.",
                  "success")
        return redirect(url_for("ri_protocolo_ver", protocolo_id=protocolo_id))

    def _anexar_ao_protocolo(p, arquivos, descricao, *, tipo=None):
        """Guarda os arquivos na pasta do protocolo e os anexa a ele. GRAVA.

        Devolve (ids, nomes). O tipo, quando escolhido, fica no próprio anexo
        (`attachments.documento_tipo`) — a mesma coluna do protocolo geral.
        """
        pasta = _pasta_dos_documentos(p["numero"])
        uid = _usuario_id_atual()
        ids, nomes = [], []
        for arquivo in arquivos:
            info = save_upload(arquivo, pasta)
            ids.append(db.add_attachment(RDOC.ENTIDADE_RI, p["id"], info, uid, descricao))
            nomes.append(info["original_name"])
        if tipo:
            with db.transaction() as con:
                for anexo in ids:
                    RND.marcar_anexo(con, p["id"], anexo, tipo=tipo, descricao=descricao)
        audit("RI_PRENOTACAO_DOCUMENTO", "RI_PROTOCOLO", p["id"],
              {"anexos": ids, "arquivos": nomes, "qtd": len(nomes), "tipo": tipo})
        return ids, nomes

    def _usuario_id_atual():
        from flask import session
        uid = session.get("user_id")
        return int(uid) if uid else None

    @app.route("/registro-imoveis/numeracao-no-teor")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def ri_numeracao_no_teor():
        """As fichas cujo TEXTO traz ato que a tabela de atos não tem.

        É o tamanho do que o relato «AV-28 aparecendo no teor de ficha do
        acervo» escondia. Só lê, e não conserta nada: consertar seria criar ato
        a partir de texto lido por programa.
        """
        with db.connect() as con:
            lista = NUMT.matriculas_em_risco(con)
            bd = banco(con)
            for x in lista:
                linha = bd.um(
                    "SELECT tipo_ficha FROM ri_matriculas WHERE id=%s",
                    (x["matricula_id"],))
                x["tipo_ficha"] = linha["tipo_ficha"] if linha else None
        # AS ESTRUTURADAS PRIMEIRO, e não as de maior distância: são as únicas
        # em que o sistema numera SOZINHO, e por isso as únicas em que o erro
        # sairia sem ninguém digitar nada.
        lista.sort(key=lambda x: (x["tipo_ficha"] != "ESTRUTURADA",
                                  -x["distancia"]))
        estruturadas = [x for x in lista if x["tipo_ficha"] == "ESTRUTURADA"]
        return render_template("ri_numeracao_no_teor.html", lista=lista,
                               estruturadas=estruturadas)

    # ---------------------------------- o ato antes de ser ato: o rascunho

    @app.route("/registro-imoveis/<int:matricula_id>/rascunho",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_rascunho_guardar(matricula_id):
        """Guarda o texto do ato SEM lavrar — e sem tomar o numero.

        Os dois débitos do balcão, «pré-visualizar matrícula com o ato novo» e
        «rascunho de ato sem consumir número», são a mesma necessidade: escrever
        a averbação, ver como a matrícula vai ler com ela dentro, e só então
        lavrar.
        """
        if not q1("SELECT id FROM ri_matriculas WHERE id=%s", (matricula_id,)):
            abort(404)
        acao = request.form.get("acao")
        try:
            with db.transaction() as con:
                if acao == "apagar_rascunho":
                    havia = RASC.apagar(con, matricula_id)
                else:
                    RASC.salvar(
                        con, matricula_id,
                        tipo=request.form.get("tipo"),
                        teor=request.form.get("teor"),
                        modelo_codigo=(request.form.get("modelo_codigo")
                                       or "").strip().upper() or None,
                        natureza_titulo=(request.form.get("natureza_titulo")
                                         or "").strip() or None,
                        protocolo=(request.form.get("protocolo") or "").strip() or None,
                        prenotacao=(request.form.get("prenotacao") or "").strip() or None,
                        data_ato=(request.form.get("data_ato") or "").strip() or None,
                        quem=_usuario_atual(), agora=db.now())
        except RASC.RascunhoError as e:
            flash(str(e), "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))
        if acao == "apagar_rascunho":
            audit("RI_RASCUNHO_APAGADO", "RI_MATRICULA", matricula_id, {})
            flash("Rascunho jogado fora." if havia
                  else "Não havia rascunho nesta matrícula.", "success")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))
        audit("RI_RASCUNHO_GUARDADO", "RI_MATRICULA", matricula_id,
              {"tipo": request.form.get("tipo")})
        flash("Rascunho guardado. Ele NÃO é ato: não tomou número, não entrou "
              "na matrícula e não vale como registro.", "success")
        return redirect(url_for("ri_rascunho_ver", matricula_id=matricula_id))

    @app.route("/registro-imoveis/<int:matricula_id>/como-ficara")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def ri_rascunho_ver(matricula_id):
        """A matrícula como ela vai ler com o ato novo dentro. NÃO GRAVA NADA.

        A tela monta em memória e é de leitura pura — nem o número previsto se
        consome ao olhar: `numero_que_teria` calcula, como toda função de
        contador desta casa.
        """
        with db.connect() as con:
            try:
                visao = RASC.como_ficara(con, matricula_id)
            except RASC.RascunhoError:
                abort(404)
        return render_template("ri_como_ficara.html", **visao, MARCA=RASC.MARCA)

    @app.route("/registro-imoveis/rascunhos")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def ri_rascunhos():
        """Os rascunhos abertos — trabalho que alguém não terminou.

        Sem esta lista o rascunho só apareceria a quem abrisse aquela matrícula
        por acaso.
        """
        with db.connect() as con:
            lista = RASC.abertos(con)
        return render_template("ri_rascunhos.html", rascunhos=lista)

    # ------------------------------------------------- lavrar novo ato

    def _quem_mexeu_na_minuta() -> str | None:
        """Quem criou, revisou, lavrou ou descartou a minuta. Só lê.

        É O NOME, E NÃO O LOGIN — e esta escolha tem um motivo medido. O RI usa
        as duas convenções: `_usuario_atual()` devolve o login («mario») e serve
        a ata do expurgo e o rascunho; `usuario_nome()` devolve «MARIO EXEMPLO
        DOS SANTOS» e é o que sai no selo, no escrevente e em `reaberta_por`,
        que a ficha **mostra na tela**.

        O rastro da minuta é da segunda espécie: ele vai ser lido por uma
        pessoa que abre a ficha meses depois e pergunta «quem revisou este
        texto?». «mario» não responde isso. A primeira versão gravava o login, e
        quem apontou foi o teste que comparou com o que a reabertura grava ao
        lado, na mesma ficha — **duas convenções na mesma tela é como elas
        divergem**.
        """
        return app.extensions["usuario_nome"]()

    def _partes_da_tela(form) -> list[dict]:
        """As partes que o formulário mandou — lê e limpa. NÃO grava nada.

        RELATO #86, 18/09/2026: «precisa ser possivel incluir tantas quantas as
        partes do ato». O teto de três era da TELA, e o `getlist` já lia
        quantas viessem — o que faltava era o desenho oferecer o quarto bloco.
        Aqui é o lado que recebe, e ele não conta, não corta e não ordena.

        UM LUGAR SÓ PARA LER OS CAMPOS, e não dois: quem GUARDA a revisão da
        minuta e quem GRAVA em `ri_partes` (mais abaixo) leem estes mesmos
        nomes — `parte_nome`, `parte_documento`, `parte_papel` e as duas de
        volta (`parte_qualificacao`, `parte_documento_tipo`). Duas leituras
        divergiriam no dia em que a tela ganhasse um campo: uma gravaria o
        campo novo e a outra não, e a diferença só apareceria no papel.

        **E ESTE PARÁGRAFO DIZIA «E NÃO DOIS» COM UM TERCEIRO LEITOR DE PÉ.**
        O envelope do selo (`_selar_o_ato_do_ri`) também lê a tela, com
        `zip(getlist("parte_nome"), getlist("parte_documento"))`. Ele fica como
        está de propósito, e a diferença é medida: **o `zip` trunca, não
        escorrega** — as duas listas saem dos mesmos blocos, na mesma ordem, e
        quem não tem nome não entra no envelope (o filtro está lá dentro). O
        que a lista torta estragaria é a QUALIFICAÇÃO cair na parte errada, e
        essa leitura é só desta função.

        `getlist` ALINHA POR POSIÇÃO, e cliente que mande menos documentos do
        que nomes não pode derrubar a tela: o que falta vira vazio, que é o
        mesmo que a linha em branco. **Lista torta é entrada possível; erro de
        índice no balcão não é resposta.**

        A QUALIFICAÇÃO E O TIPO DE DOCUMENTO VÊM DO BLOCO ESCONDIDO, e o
        motivo está em `_parte_do_ato.html`: a tela não os edita, mas a parte
        que voltou de um ato suspenso os traz, e o que a tela não mostra não
        pode sumir na gravação.

        E ELAS SÓ VALEM SE VIEREM UMA POR BLOCO — é o que `_sem_torto` exige,
        e o defeito que ela impede tem nome: `getlist` casa as listas POR
        POSIÇÃO, então uma lista de dois valores para três blocos faria a
        qualificação do SEGUNDO cair no NOME DO TERCEIRO, calada, num registro
        público. O bloco do template sempre emite os dois campos, mesmo vazios,
        e é isso que constrói a igualdade; quando ela não vem, o valor é
        declarado ausente (`None`) em vez de adivinhado.

        Bloco SEM NOME não é parte — é a linha em branco da tela, e quem a
        descarta é aqui, uma vez, em vez de em cada lugar que grava.
        """
        nomes = form.getlist("parte_nome")
        docs = form.getlist("parte_documento")
        papeis = form.getlist("parte_papel")
        quails = form.getlist("parte_qualificacao")
        tipos = form.getlist("parte_documento_tipo")

        def _na(lista, i) -> str:
            return ((lista[i] if i < len(lista) else "") or "").strip()

        def _sem_torto(lista) -> bool:
            """Só uso a lista se ela tiver exatamente uma entrada por bloco."""
            return not lista or len(lista) == len(nomes)

        if not _sem_torto(quails):
            quails = []
        if not _sem_torto(tipos):
            tipos = []

        partes = []
        for i in range(len(nomes)):
            nome = _na(nomes, i)
            if not nome:
                continue
            partes.append({"nome": nome,
                           "documento_tipo": _na(tipos, i) or None,
                           "documento_numero": _na(docs, i),
                           "qualificacao": _na(quails, i) or None,
                           "papel": _na(papeis, i)})
        return partes

    def _partes_da_revisao(form) -> list[dict] | None:
        """As partes para GUARDAR a revisão — ou `None`, se a tela não as mandou.

        A DIFERENÇA ENTRE `[]` E `None` É O QUE ESTA FUNÇÃO EXISTE PARA FAZER.
        `RIMIN.atualizar` diz, com todas as letras, que `partes=None` quer dizer
        «a tela não mexeu nisto» — e `[]` quer dizer «não há parte nenhuma», que
        APAGA as que estavam guardadas. `_partes_da_tela` devolve lista sempre,
        e por isso quem só quisesse gravar o teor (um POST de script, o
        `rascunho.js`, um teste) limparia as partes da minuta sem ter tocado
        nelas — e a minuta voltaria vazia para a fila, que é o defeito de 15/09
        pela porta do meio.

        QUEM DECIDE É O CAMPO, E NÃO A LISTA: a ficha manda sempre ao menos um
        bloco — mesmo em branco, porque é ele que permite digitar uma parte sem
        JavaScript —, logo `parte_nome` existe em todo POST da tela. Campo
        AUSENTE veio de outro cliente, e ali a resposta honesta é «não sei»,
        que é o que `None` diz e `[]` não.
        """
        if not form.getlist("parte_nome"):
            return None
        return _partes_da_tela(form)

    def quem_pratica_o_ato() -> tuple[str | None, str | None, str | None]:
        """Quem assina o ato que está sendo lavrado agora — só calcula.

        Devolve `(nome, titulo, artigo)`, congelados em `ri_atos` na lavratura.

        RELATO #65 DO OFICIAL, 15/09/2026: «tirar a opção de escolher ato
        praticado por, atos novos são sempre praticados pelo delegatário ou
        escrevente atual do sistema».

        DE ONDE VEM, E POR QUE NÃO SE ESCOLHE
            Do cadastro de quem está logado (`users`), pela mesma regra que o
            Tabelionato de Notas já usa — `lavrado_nome or usuario_nome()` e
            `lavrado_titulo or usuario_funcao()`. O nome e a função são os que
            saem embaixo da assinatura (Lei 8.935/94, arts. 20 e 21), e quem
            os corrige é a tela Usuários, que já avisa quem está sem função
            cadastrada.

        E A LISTA DE NOMES QUE HAVIA AQUI?
            `ri_delegatarios` FICA, e continua respondendo pelo ato no período
            do titular — é dela que saem os títulos do timbre
            (`titulo_registrador`, `titulo_substituta`) e a resolução dos atos
            antigos. O que saiu foi o campo de ESCOLHA: a lista era a mesma em
            todo ato, e quem já lavrou não escolhe por quem assina.

        CONGELA COMO ANTES
            Os três valores continuam indo para `ri_atos` na hora da lavratura:
            se a função de quem assinou mudar amanhã, este ato continua dizendo
            o que dizia hoje.

        O ARTIGO
            «O» ou «A», e ele é do FECHO — nenhum artigo da Lei 6.015/1973 o
            exige, e a assinatura desta casa o usa. Sai da última palavra da
            função, e confere no cadastro de hoje: «Tabelião e Oficial de
            Registro» → O · «Substituta» → A · «Escrevente Autorizada» → A ·
            «Auxiliar» → O.
        """
        nome = (app.extensions["usuario_nome"]() or "").strip() or None
        titulo = (app.extensions["usuario_funcao"]() or "").strip() or None
        artigo = None
        if titulo:
            artigo = "A" if titulo.split()[-1].lower().endswith("a") else "O"
        return nome, titulo, artigo

    # O LIVRO 3 PERGUNTA A MESMA COISA — LH13, 21/10/2026 («15 a»: «como no
    # Livro 2»). As rotas dele moram em `atribuicoes_web`, registradas depois
    # destas, e pegam daqui o MESMO objeto — como `usuario_nome` no `app` —,
    # e não uma segunda cópia da regra do artigo.
    app.extensions["quem_pratica_o_ato"] = quem_pratica_o_ato

    def _marcar_a_ficha_encerrada(con, matricula_id: int, *, motivo: str,
                                  destino: str, data_ato: str) -> None:
        """Escreve as marcas do encerramento na ficha. ESCREVE.

        UM LUGAR SÓ PARA AS QUATRO COLUNAS — 15/09/2026. Elas eram escritas em
        `ri_encerrar_matricula` e passaram a ser escritas também por
        `ri_lavrar_ato`, quando o ato lavrado É o encerramento. Duas cópias
        divergiriam no primeiro conserto, e aqui a divergência é caríssima: uma
        ficha que diz `encerrada=0` com um ato de encerramento no livro aceita
        registro novo sobre imóvel que já foi transportado.

        O DESTINO VAI DENTRO DO MOTIVO, e não em coluna própria — medido no
        esquema: `ri_matriculas` tem `encerrada`, `motivo_encerramento` e
        `data_encerramento`, e nada de `destino_encerramento`. É a forma que
        `ri_encerrar_matricula` já usava.
        """
        bd = banco(con)
        bd.escrever(
            """UPDATE ri_matriculas SET encerrada=1, situacao='ENCERRADA',
                   motivo_encerramento=%s, data_encerramento=%s,
                   reaberta_em=NULL, reaberta_por=NULL, motivo_reabertura=NULL,
                   atualizado_em=%s WHERE id=%s""",
            (motivo + (f" Destino: {destino}." if destino else ""),
             data_ato, db.now(), int(matricula_id)))
        # Titularidade deixa de ser atual numa matricula encerrada.
        bd.escrever(
            "UPDATE ri_partes SET proprietario_ativo=0 WHERE matricula_id=%s",
            (int(matricula_id),))

    @app.route("/registro-imoveis/<int:matricula_id>/atos", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_lavrar_ato(matricula_id):
        m = q1("SELECT * FROM ri_matriculas WHERE id=%s", (matricula_id,))
        if not m:
            abort(404)
        if m["encerrada"]:
            flash("Matrícula encerrada. Não é possível lavrar novo ato.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        tipo = (request.form.get("tipo") or "").strip().upper()
        if tipo not in ("R", "AV"):
            flash("Tipo de ato inválido.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        # Em ficha estruturada o sistema sabe a sequencia. Em ficha de acervo
        # os atos estao dentro de um bloco de texto, entao o numero vem do livro.
        e_acervo = (m["tipo_ficha"] == "ACERVO"
                    or matricula_de_acervo(m["numero"]))
        if e_acervo:
            # LD13: 30 dígitos passavam pelo `int()` e estouravam no INSERT do
            # ato; o que não é número continua sendo o 0 recusado aqui.
            numero = numero_digitado(request.form.get("numero")) or 0
            if numero <= 0:
                flash("Nesta ficha de acervo o número do ato precisa ser informado, "
                      "conforme o livro físico.", "danger")
                return redirect(url_for("ri_ficha", matricula_id=matricula_id))
        else:
            # A numeracao da matricula e CONTINUA: registros e averbacoes
            # dividem a mesma sequencia (R-01, AV-02, R-03...), como se ve no
            # acervo e no modelo de ficha da serventia. Nao ha sequencia
            # separada por tipo.
            #
            # E ELA CONTA TAMBEM O QUE ESTA ESCRITO NO TEOR — o defeito que o
            # relato «AV-28 aparecendo no teor de ficha do acervo» escondia.
            #
            #   Nas fichas que vieram do E-Oficio os atos moram DENTRO do texto
            #   («R-33/314:-»), e nao como linha em `ri_atos`. `MAX(numero)+1`
            #   nao os enxerga. Medido em 28/08/2026: em **13 fichas
            #   ESTRUTURADAS** o sistema numeraria um ato com numero que a ficha
            #   ja usou — na matricula 314 sairia R-15 com a ficha em R-35.
            #
            #   Nas 743 fichas de ACERVO isso nao acontecia, porque ali o numero
            #   ja era exigido a mao (o `if` acima). O silencio era so nas
            #   estruturadas, e por isso ninguem tinha visto.
            #
            # O PISO NAO INVENTA ATO: ele so recusa REPETIR um numero que esta
            # escrito na propria ficha. Criar linha em `ri_atos` a partir do
            # texto seria fabricar ato com data e conteudo adivinhados, e ainda
            # po-lo na corrente de hash — ver `ri_numeros_do_teor`.
            with db.connect() as _c:
                piso = NUMT.piso_do_proximo(_c, matricula_id)
            numero = piso["proximo"]

        # A RECUSA TAMBEM OLHA O TEXTO DA FICHA, e nao so as linhas. Era aqui
        # que os 756 casos passavam: o numero estava livre em `ri_atos` e
        # ocupado no papel.
        with db.connect() as _c:
            no_papel = NUMT.ja_usado_na_ficha(_c, matricula_id, numero)
        if no_papel:
            flash(
                f"O número {numero} já está usado nesta matrícula: a própria "
                f"ficha traz «{no_papel['rotulo']}». Está escrito assim no "
                f"teor — “…{no_papel['trecho'][:110]}…”. Informe outro número, "
                f"conforme o livro físico.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        existe = q1("SELECT tipo, numero FROM ri_atos WHERE matricula_id=%s AND numero=%s",
                    (matricula_id, numero))
        if existe:
            flash(f"O número {numero} já está ocupado nesta matrícula pelo ato "
                  f"{existe['tipo']}-{existe['numero']:02d}. A numeração é contínua entre "
                  f"registros e averbações.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        teor = (request.form.get("teor") or "").strip()
        if not teor:
            flash("O teor do ato não pode ficar em branco.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))
        # MARCADOR DE MODELO CRU NÃO ENTRA NO LIVRO — 06/10/2026. Esta rota
        # grava o teor como vem do formulário, sem motor de modelo; as 11
        # minutas da CNIB traziam `{{ rotulo }}` e `{{ protocolo_frase }}`, e
        # lavrar qualquer uma poria o marcador na ficha e na corrente de hash,
        # onde não se corrige mais. Recusa antes de tomar número ou pedir selo.
        marca_crua = RIMIN.marcador_de_modelo(teor)
        if marca_crua:
            flash(f"O teor traz «{marca_crua}», marcação de modelo que não foi "
                  f"preenchida — no livro sairia literalmente assim. Troque "
                  f"pelo texto do ato (o rótulo, a frase do protocolo) e lavre "
                  f"de novo. Nada foi lavrado.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        # O [CAMPO] DO MODELO QUE NINGUÉM PREENCHEU TAMBÉM NÃO ENTRA — LD03,
        # 21/10/2026 («corrija tudo»; o LT03 achou). A guarda de cima recusa o
        # `{{ }}`, que é do motor, e deixava passar o colchete de propósito: o
        # acervo transcrito tem colchete legítimo («[rubrica]»). Mas o colchete
        # do MODELO informado em `modelo_codigo` é outra coisa — «[DATA DA
        # ESCRITURA]» no livro é o R-1 sem a data do título (LRP art. 176,
        # § 1º, III, 4), e o teor congela na corrente de hash. A régua é a do
        # próprio modelo (`ri_modelos_atos.por_preencher`). Antes de número e
        # selo; e quem veio de uma minuta volta para ela, com o texto dentro.
        faltam_no_modelo = por_preencher_do_modelo(
            teor, request.form.get("modelo_codigo"))
        if faltam_no_modelo:
            flash(f"O texto ainda traz {len(faltam_no_modelo)} campo(s) do "
                  f"modelo por preencher — {'; '.join(faltam_no_modelo[:6])}"
                  f"{' …' if len(faltam_no_modelo) > 6 else ''}. No livro "
                  f"sairiam assim, entre colchetes. Preencha e lavre de novo. "
                  f"Nada foi lavrado.", "danger")
            minuta_da_recusa = (request.form.get("minuta_id") or "").strip()
            return redirect(url_for(
                "ri_ficha", matricula_id=matricula_id,
                **({"minuta": minuta_da_recusa, "lavrar": 1}
                   if minuta_da_recusa.isdigit() else {})))

        # MODELO DE ENCERRAMENTO NÃO PREENCHIDO — HOTFIX-2026-10-08-08. O
        # «PREENCHER…» é do modelo que o botão «Encerrar matrícula» põe no
        # texto; ficou, o livro o imprimiria. Recusa antes de número e selo.
        if MARCA_A_PREENCHER in teor:
            flash("O texto do ato ainda tem trecho «PREENCHER…» do modelo de "
                  "encerramento. Troque pelo texto definitivo e lavre de novo. "
                  "Nada foi lavrado.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        # A REVISÃO ANTES DA LAVRATURA — ordem do oficial em 06/10/2026: o
        # Opus lê o ato com a matrícula antes de ele existir. Ver
        # `revisao_previa.py`: sem chave da IA a etapa não existe, e IA fora do
        # ar não trava o balcão. Antes de tomar número ou pedir selo.
        import revisao_previa as RV
        try:
            with db.transaction() as _con_rv:
                # HOTFIX-2026-10-08-07: papel + «lavrar com a revisão anterior».
                _rv_como = RV.exigir_para_lavrar(
                    _con_rv, Path(app.config["DATA_DIR"]), "RI", int(matricula_id),
                    RV.hash_do_ato(tipo, teor),
                    justificativa=request.form.get("revisao_justificativa") or "",
                    usuario=app.extensions["usuario_nome"](),
                    papel=app.extensions["usuario_papel"](),
                    usar_revisao_anterior=request.form.get("revisao_usar_anterior") == "1",
                    justificativa_anterior=request.form.get("revisao_justificativa_anterior") or "",
                    texto_atual=teor, tipo=tipo,
                    # HOTFIX-2026-10-13-01: encerramento/isento = ato de oficio (consultivo).
                    contexto_oficio=(request.form.get("encerra") == "1"
                                     or request.form.get("isento") == "1"
                                     or bool((request.form.get("motivo_isencao") or "").strip())),
                    prosseguir=request.form.get("revisao_prosseguir") == "1")
            if str(_rv_como).startswith("consultivo"):
                audit("REVISAO_PREVIA_CONSULTIVA", "RI_MATRICULA", int(matricula_id),
                      {"como": _rv_como, "tipo": tipo})
            if str(_rv_como).startswith("anterior"):
                audit("REVISAO_PREVIA_ANTERIOR_USADA", "RI_MATRICULA", int(matricula_id),
                      {"como": _rv_como, "tipo": tipo,
                       "justificativa": request.form.get("revisao_justificativa_anterior") or ""})
        except RV.RevisaoPendente as erro:
            # A recusa fica na auditoria: o flash some com a página, e foi assim
            # que o bloqueio do AV-8/1196 (08/10/2026) ficou sem rastro.
            audit("RI_LAVRAR_RECUSADO_REVISAO", "RI_MATRICULA", int(matricula_id),
                  {"tipo": tipo, "motivo": str(erro)[:400]})
            flash(f"{erro} Nada foi lavrado.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        data_ato = (request.form.get("data_ato") or "").strip() or db.now()[:10]
        # O SELO SAI DO SELADOR, E NAO DA AREA DE TRANSFERENCIA — 14/09/2026,
        # ordem do oficial: «ainda tem campo para colar o qr code do selo
        # emitido fora. Tire essas parte, incorpore o selador automatizado».
        #
        #   Medido antes de tirar: em **1.245 atos, ZERO** tinham QR colado, e
        #   so 4 tinham etiqueta digitada — os 4 que este sistema lavrou. O
        #   campo existia, ninguem usou, e ele pedia ao escrevente que fosse
        #   buscar noutro programa o que o aparelho da rede local responde em
        #   dois segundos.
        #
        #   AS COLUNAS FICAM: `selo_qr`/`selo_qr_2` continuam no esquema e a
        #   ficha continua mostrando o que houver nelas. Apagar coluna e apagar
        #   o que o acervo trouxer amanha; o que saiu foi o CAMPO DE ENTRADA.
        base_calculo = centavos(request.form.get("base_calculo"))
        codigo_tj = (request.form.get("codigo_tj") or "").strip() or None

        # ARQUIVAMENTO OPCIONAL (16.39) — Beatriz 23/09/2026. RI_ARQUIV_FORM
        # Checkbox + folhas: so obriga folhas se marcar. Sem marcar, zero impacto.
        gerar_arquivamento = request.form.get("gerar_arquivamento") == "1"
        folhas_arquivamento = None
        if gerar_arquivamento:
            bruto_folhas = (request.form.get("folhas_arquivamento") or "").strip()
            try:
                folhas_arquivamento = int(bruto_folhas or 0)
            except ValueError:
                folhas_arquivamento = 0
            if folhas_arquivamento < 1:
                flash("Para gerar o selo de arquivamento, informe a quantidade "
                      "de folhas do documento/processo (numero >= 1).", "danger")
                return redirect(url_for("ri_ficha", matricula_id=matricula_id,
                                        lavrar=1))

        # VERSAO FINAL COM EMOLUMENTOS + ESPACO DO SELO (pedido do oficial
        # 15/09/2026). Espelha o RCPJ: itens do protocolo de caixa quando
        # houver; sem protocolo, o item escolhido pelo texto completo (ou o
        # codigo_tj digitado). A relacao tambem pode constar no carimbo
        # (`bloco_selo_*` + selo_no_papel.linha_de_valores).
        # Multi-selo na lavratura (codigo_tj_selo + qtd_selo) — Beatriz 24/09/2026.
        # Se a operadora preencheu as linhas «Varios selos neste ato», essa fila
        # manda (inclui quantidade: 16.5 x2). Senao, cai no catalogo/protocolo.
        tem_multi_selo = any(str(x or "").strip()
                             for x in request.form.getlist("codigo_tj_selo"))
        codigos_escolhidos = []
        if tem_multi_selo:
            codigos_escolhidos = list(_codigos_de_selo_do_form(request.form))
        # LD13: o «²» e os 5.000 dígitos passavam pelo `isdigit()` e caíam no
        # `int()` de baixo; o que não é número fica de fora, como antes.
        ids_protocolo_item = [n for n in map(numero_digitado,
                                             request.form.getlist("protocolo_item_id"))
                              if n is not None]
        protocolo_caixa_id = numero_digitado(request.form.get("protocolo_id"))
        with db.connect() as _cx:
            if ((not tem_multi_selo) and ids_protocolo_item
                    and protocolo_caixa_id is not None):
                # O ITEM SE GASTA POR UNIDADE, E ESTA ERA A TERCEIRA COPIA DA
                # CONDICAO ERRADA — relato do oficial em 15/09/2026, a segunda
                # vez no mesmo dia: «preenchi tudo, escolhi o ato sem valor
                # declarado (tinha 5) e deu isso».
                #
                #   Aqui estava `AND usado_em IS NULL`. O item 32476 do
                #   protocolo 2026.09.23 e «De ato sem valor declarado»,
                #   **quantidade 5**, e tem `usado_em` preenchido desde que a
                #   AV-04 gastou a primeira: a consulta devolvia ZERO linhas,
                #   `codigos_escolhidos` ficava vazio, e o item que ele marcou
                #   na tela nao chegava a rota. As outras quatro averbacoes
                #   que ele pagou eram invisiveis para quem lavra.
                #
                #   Eu ja havia consertado isto em `caixa_protocolo` e em
                #   `ri_lavrar_teor` de manha, e **deixei passar esta**, que e
                #   justamente a da rota que lavra. `itens_disponiveis` e a
                #   unica leitura da regra; repeti-la aqui e como as duas
                #   divergem — foi assim que esta ficou para tras.
                escolhidos = set(ids_protocolo_item)
                for item in CXPROT.itens_disponiveis(_cx, protocolo_caixa_id):
                    if int(item["id"]) not in escolhidos:
                        continue
                    c = str(item["codigo_ato"] or "").strip()
                    if c:
                        codigos_escolhidos.append(c)
            # Sem protocolo (ou sem item marcado): texto completo / codigo_tj.
            # Com multi-selo preenchido, a fila ja veio de codigo_tj_selo+qtd.
            if (not tem_multi_selo) and not codigos_escolhidos:
                for c in request.form.getlist("codigo_tj_item"):
                    c = str(c or "").strip()
                    if c:
                        codigos_escolhidos.append(c)
            if (not tem_multi_selo) and not codigos_escolhidos and codigo_tj:
                codigos_escolhidos = [codigo_tj]
            itens_calc = RITEOR.calcular_itens(
                _cx, codigos_escolhidos,
                base_calculo=base_calculo)
        if codigos_escolhidos and not codigo_tj:
            codigo_tj = codigos_escolhidos[0]
        # O TEOR GUARDA O ATO, E NAO O CARIMBO — correcao de 15/09/2026, a
        # pedido do oficial: «o teor foi com espacamento no meio, nao foi o
        # carimbo do selo e o relatorio de emolumentos deve ir junto com o
        # carimbo do selo e qr code».
        #
        #   Medido no ato 3737 (AV-04/3.110), lavrado hoje: o teor gravado tem
        #   **dez linhas**, e nove nao sao do ato. `versao_final_para_lavrar`
        #   acrescentava a relacao de emolumentos e o «espaco reservado para o
        #   selo», com a linha `[ selo / verificacao ]` e vinte espacos no
        #   meio — que foi o que ele viu no papel.
        #
        #   O DESENHO PREVIA QUE O CARIMBO DE VERDADE ENTRARIA DEPOIS, «quando
        #   o aparelho responde». So que **o teor congela na corrente de
        #   hash**: o marcador entrou e nao sai mais. Conferido contra a
        #   minuta e contra o ato original — os dois tem UMA linha.
        #
        #   O `sem_fecho_antigo` FICA, e e o que interessa dele aqui: e ele que
        #   tira o fecho manual que a minuta traz («Emolumentos: R$ ______ (...)
        #   Selo de Fiscalizacao Digital no ______»), que nao pode conviver com
        #   o selo que o aparelho emite.
        #
        #   E os dois parametros sao da propria API deste modulo — nao se
        #   reescreveu o modulo de outra passada para consertar o chamador.
        teor = RITEOR.versao_final_para_lavrar(
            teor, itens_calc, com_emolumentos=False, com_espaco_selo=False)
        emol_calc = RITEOR.frase_emolumentos_curta(itens_calc)
        if emol_calc and not (request.form.get("emolumentos") or "").strip():
            # Preenche o campo curto do ato quando o balcao nao digitou.
            pass  # aplicado no INSERT abaixo via emol_calc

        # A GRATUIDADE E EXCECAO, E EXIGE MOTIVO ESCRITO — pedido do oficial em
        # 14/09/2026. Medido: 48 das 829 prenotacoes sairam isentas (5,8%), e
        # **zero dos 120 atos**; quase todas por REURB-S.
        #
        #   **A RECUSA E AQUI, E NAO NO SELO.** O envelope tambem a faria (ele
        #   recusa isento sem motivo), mas ali o ato ja estaria lavrado e na
        #   cadeia de hash: sobraria um ato marcado como gratuito sem dizer por
        #   que, e consertar isso exigiria averbacao. Aqui o cliente ainda esta
        #   na frente. E a regra da participacao da DOI, pelo mesmo motivo.
        isento, motivo_isencao = ler_isencao_do_form(request.form)
        motivo_isencao = motivo_isencao or ""
        # Guardado antes das recusas: quem volta para corrigir tem de cair na
        # MESMA minuta, com o texto dentro — e nao na ficha crua.
        minuta_pedida = (request.form.get("minuta_id") or "").strip() or None

        # O QUE A TELA JA SABE SE RECUSA AQUI, E NAO DEPOIS DO ATO NASCER.
        #
        #   RELATO DO OFICIAL EM 15/09/2026: «deu problema no av05 e foi
        #   lavrado, mas cancelado so pq nao saiu selo. nao eh assim que deve
        #   operar, se deu problema no selo deve voltar e permitir retificar o
        #   erro e tentar lavrar novamente o mesmo ato».
        #
        #   A AV-05 foi lavrada e cancelada porque faltava a **natureza do
        #   titulo** — um campo que a tela tinha na frente dele o tempo todo.
        #   Recusar depois custou um ato cancelado no livro por um dado que
        #   nao dependia de rede nenhuma.
        #
        #   E A REGRA DA CASA JA DIZIA ISSO, escrita para a gratuidade em
        #   14/09: «a recusa e aqui, e nao no selo (...) aqui o cliente ainda
        #   esta na frente». Ela so nao alcancava a natureza e o item.
        #
        #   O QUE CONTINUA LAVRANDO SEM SELO e o que **so a rede diz**:
        #   aparelho fora do ar, credencial vencida, recusa do TJMA. Ali o ato
        #   fica, e o selo entra depois por «Selar este ato» — balcao parado e
        #   pior que selo atrasado.
        impedimento = falta_para_selar(
            natureza=request.form.get("natureza_titulo"),
            codigo_tj=codigo_tj, isento=isento,
            motivo_isencao=motivo_isencao,
            selo_a_mao=request.form.get("selo_texto"),
            # FICHA DE ACERVO NAO PRECISA DO ITEM DE CUSTA — ver a docstring.
            # `tipo_ficha` e a regua, e nao `origem`: aquela diz DE ONDE A
            # LINHA VEIO, esta diz COMO A FICHA SE ESCRITURA. E a mesma
            # correcao do aviso da digitalizacao, de 07/09.
            e_acervo=e_acervo,
            base_calculo=base_calculo)
        if impedimento:
            flash(impedimento + " O ato NÃO foi lavrado — corrija e lavre de "
                  "novo; nada se perdeu.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id,
                                    **({"minuta": minuta_pedida}
                                       if minuta_pedida else {})))

        # CNIB NA LAVRATURA (TJMA 506): a consulta sempre fica gravada no ato;
        # o protocolo da Central so e exigido quando a casa liga a regra.
        cnib_protocolo = (request.form.get("cnib_protocolo") or "").strip()
        if (not cnib_protocolo
                and db.get_setting(CNIB.CHAVE_EXIGIR_PROTOCOLO, "0") == "1"
                and CNIB.exige_consulta(request.form.get("natureza_titulo"),
                                        tipo)):
            flash("Alienação ou oneração: informe o protocolo da consulta à "
                  "CNIB feita na Central (TJMA 506). O ato NÃO foi lavrado — "
                  "nada se perdeu.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id,
                                    **({"minuta": minuta_pedida}
                                       if minuta_pedida else {})))
        cnib_base, _cnib_ordens = cnib_referencia()

        # A MINUTA QUE ESTA SENDO LAVRADA — pedido do oficial em 15/09/2026:
        # «precisam ficar como atos para serem revistos e lavrados».
        #
        #   QUEM LAVRA E ESTA ROTA, E NAO O MODULO DA MINUTA. `ri_minuta` nao
        #   numera, nao entra na corrente de hash, nao sela e nao cobra — se
        #   houvesse uma segunda porta para lavrar, seriam duas versoes da
        #   regra que numera e sela, e elas divergiriam no primeiro conserto.
        #   Aqui a minuta e so a procedencia do teor que o operador revisou.
        minuta = None
        if numero_digitado(request.form.get("minuta_id")) is not None:
            with db.connect() as _c:
                escolhida = RIMIN.uma(_c, numero_digitado(request.form["minuta_id"]))
            if not escolhida or escolhida["matricula_id"] != matricula_id \
                    or escolhida["situacao"] != RIMIN.A_REVISAR:
                flash("A minuta indicada não é desta matrícula ou já saiu da "
                      "fila de revisão. O ato não foi lavrado — abra a ficha e "
                      "escolha a minuta outra vez.", "danger")
                return redirect(url_for("ri_ficha", matricula_id=matricula_id))
            minuta = escolhida

        # ESTE ATO ENCERRA A FICHA? — 15/09/2026, e o buraco apareceu quando as
        # minutas da 3.110 voltaram para a fila.
        #
        #   A AV-06 daquela ficha **é** a averbação de encerramento: o teor
        #   dela diz «ENCERRAMENTO DA ESCRITURAÇÃO NO LIVRO E TRANSPORTE PARA
        #   FICHA». Lavrá-la por aqui deixava a ficha ABERTA, e quem quisesse
        #   fechá-la depois teria de clicar em «Encerrar esta matrícula» — que
        #   **lavra outra averbação**. A ficha terminaria com dois
        #   encerramentos, AV-06 e AV-07, e ninguém saberia qual vale.
        #
        #   ENCERRAR É DO OFICIAL, e esta rota atende o balcão (aceita USER).
        #   A guarda é por AÇÃO, e não por rota: `usuario_papel` existe para
        #   isto — há tela que se vê e onde não se pratica todo ato.
        encerra = request.form.get("encerra") == "1"
        encerra_motivo = (request.form.get("encerra_motivo") or "").strip()
        encerra_destino = (request.form.get("encerra_destino") or "").strip()
        if encerra:
            papel = app.extensions["usuario_papel"]()
            if papel not in ("ADMIN", "MANAGER"):
                flash("Encerrar a matrícula é do oficial. O ato não foi "
                      "lavrado — retire a marca de encerramento e lavre, que "
                      "o encerramento se faz depois.", "danger")
                return redirect(url_for("ri_ficha", matricula_id=matricula_id))
            if len(encerra_motivo) < 10:
                flash("Para o ato encerrar a ficha, escreva o motivo do "
                      "encerramento — é ele que a ficha passa a mostrar no "
                      "lugar do balcão, e que a correição lê.", "danger")
                return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        # QUEM ASSINA ESTE ATO — relato #65: quem está logado, e não se escolhe.
        pratica_nome, pratica_titulo, pratica_artigo = quem_pratica_o_ato()

        with db.transaction() as con:
            bd = banco(con)
            # O NÚMERO E O HASH ANTERIOR SE LEEM DE NOVO, DENTRO DA TRAVA — a
            # mesma chave do cancelamento e do encerramento. O piso, a recusa
            # do número ocupado e o elo da corrente foram lidos lá em cima,
            # fora da transação: um ato lavrado nesse meio-tempo na mesma ficha
            # daria dois atos com o mesmo número (R-05 e AV-05 cabem no índice
            # único, que é por tipo) e a corrente de hash bifurcada.
            bd.travar("ri_atos.numero")
            # A MINUTA SE CONFERE DE NOVO, PRESA — LD10, 21/10/2026, achado ao
            # prender a minuta da tela do modelo. A conferência lá de cima
            # («ainda a revisar») foi lida fora da transação: a mesma minuta
            # aberta em duas abas passava as duas por ela e virava DOIS atos do
            # mesmo texto, com dois selos — medido pelas telas, AV-01 e AV-02 —,
            # e a minuta ficava apontando só para o segundo. Presa aqui, dentro
            # da trava da numeração, a segunda aba acha a minuta já lavrada e
            # para; quem também a prende antes de gravar — a «Guardar
            # revisão» e o descarte (`ri_minuta._presa`) e a tela do modelo —
            # espera o ato sair e lê «lavrada».
            if minuta:
                bd._escrita()
                presa = bd.um("SELECT situacao FROM ri_minutas WHERE id=%s FOR UPDATE",
                              (int(minuta["id"]),))
                if not presa or presa["situacao"] != RIMIN.A_REVISAR:
                    flash("A minuta indicada já saiu da fila de revisão enquanto "
                          "este ato era lavrado (outra aba a lavrou ou a "
                          "descartou). O ato não foi lavrado — confira a ficha.",
                          "danger")
                    abort(redirect(url_for("ri_ficha", matricula_id=matricula_id)))
            if not e_acervo:
                numero = NUMT.piso_do_proximo(bd, matricula_id)["proximo"]
            existe = bd.um("""SELECT tipo, numero FROM ri_atos
                              WHERE matricula_id=%s AND numero=%s
                              ORDER BY id LIMIT 1""", (matricula_id, numero))
            if existe:
                flash(f"O número {numero} já está ocupado nesta matrícula pelo ato "
                      f"{existe['tipo']}-{existe['numero']:02d}. A numeração é contínua entre "
                      f"registros e averbações.", "danger")
                # A exceção desfaz a transação, e o Flask devolve o redirect.
                abort(redirect(url_for("ri_ficha", matricula_id=matricula_id)))
            anterior = bd.um("""SELECT hash_ato FROM ri_atos WHERE matricula_id=%s
                                ORDER BY id DESC LIMIT 1""", (matricula_id,))
            hash_anterior = anterior["hash_ato"] if anterior else None
            h = hash_ato(m["numero"], tipo, numero, data_ato, teor, hash_anterior)
            ato_id = bd.escrever(
                """INSERT INTO ri_atos
                   (matricula_id, tipo, numero, data_ato, natureza_titulo, protocolo,
                    prenotacao, teor, teor_formato, cancelado, acervo, origem,
                    selo_texto, base_calculo_centavos, codigo_tj,
                    isento, motivo_isencao,
                    emolumentos, modelo_codigo,
                    lavrado_nome, lavrado_titulo, lavrado_tratamento,
                    hash_ato, hash_anterior, lavrado_em, lavrado_por)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s, 'texto', 0, 0, 'MANUAL', %s,%s,%s,%s,%s,%s,%s, %s,%s,%s, %s,%s,%s,%s)
                   RETURNING id""",
                (matricula_id, tipo, numero, data_ato,
                 (request.form.get("natureza_titulo") or "").strip() or None,
                 (request.form.get("protocolo") or "").strip() or None,
                 (request.form.get("prenotacao") or "").strip() or None,
                 teor,
                 (request.form.get("selo_texto") or "").strip() or None,
                 base_calculo or None, codigo_tj,
                 1 if isento else 0, motivo_isencao or None,
                 ((request.form.get("emolumentos") or "").strip() or emol_calc or None),
                 (request.form.get("modelo_codigo") or "").strip().upper() or None,
                 # Congela quem praticou. Se a função de quem assinou mudar
                 # amanhã, este ato continua dizendo o que dizia hoje.
                 pratica_nome, pratica_titulo, pratica_artigo,
                 h, hash_anterior, db.now(), None),
            )[0]["id"]
            ato_id = int(ato_id)

            # Consome UMA UNIDADE de cada item apontado para este ato.
            #
            #   RELATO DO OFICIAL EM 15/09/2026: «a prenotacao 11571 e o
            #   protocolo 2026.09.23 nao estao permitindo que eu use um selo de
            #   averbacao para o ato que preciso, ainda que conste no protocolo
            #   5 atos de averbacao sem valor».
            #
            #   Este `UPDATE` marcava `usado_em` na LINHA INTEIRA. O item dele
            #   é «De ato sem valor declarado × 5»: a AV-04 o consumiu todo, e
            #   as outras quatro averbações ficaram sem item. Medido na
            #   produção: **4 itens** com quantidade > 1 já marcados e **83
            #   unidades perdidas**, uma delas de quantidade 66.
            #
            #   A REGRA MORA EM `caixa_protocolo`, e não aqui: `atribuicoes_web`
            #   faz o mesmo para o RCPJ/RTD, e duas cópias divergiriam no
            #   primeiro conserto — que é exatamente como esta nasceu.
            if ids_protocolo_item:
                for item_id in ids_protocolo_item:
                    CXPROT.consumir_item(
                        con, int(item_id), ato_id=ato_id, tabela="ri_atos",
                        agora=db.now())
            # A PRENOTAÇÃO SE AMARRA AO ATO QUE SAIU DELA — débito de agosto.
            #
            #   `ri_protocolos.ato_id` estava vazio em 784 de 784. A prenotação
            #   é o que garante a PRIORIDADE do título (Lei 6.015/1973, art.
            #   186), e sem a amarração a pergunta «qual ato saiu desta
            #   prenotação» se responde comparando datas à mão.
            amarrado = amarrar_prenotacao(
                bd, request.form.get("protocolo"),
                matricula_id=matricula_id, ato_id=ato_id)
            # AS PARTES VÊM DO BLOCO POR PARTE — relato #86, 18/09/2026, e a
            # leitura é a MESMA de quem guarda a revisão da minuta
            # (`_partes_da_tela`). O que se compartilha é o nome dos campos, e
            # não a gravação: aqui a linha entra em `ri_partes`, com o
            # `nome_norm` que a busca usa e com o `proprietario` que decide o
            # titular atual na certidão.
            #
            # SEM TETO, e o teto não era teórico: o formulário desenhava três
            # blocos e o `getlist` sempre leu quantos viessem — era o DESENHO
            # que parava na terceira parte. Medido na produção: 44 atos desta
            # casa têm mais de três, e o maior tem 22 (R-1 da 3.757).
            #
            # O TITULAR SAI DA RÉGUA ÚNICA — LD03, 21/10/2026. Aqui estava
            # `papel.startswith("propriet")`, e `ri_correcoes.PAPEL_DE_TITULAR`
            # (a régua da correção de parte) já contava o adquirente e o
            # nu-proprietário: as duas divergiam, e o R-1 de compra e venda
            # deixava a compradora fora do quadro de titulares — a certidão de
            # propriedade afirmava o vendedor (LRP art. 19, § 9º). Quem
            # transmitiu sai do quadro depois do selo, mais abaixo.
            partes_do_ato = _partes_da_tela(request.form)
            for parte in partes_do_ato:
                nome = parte["nome"]
                doc = so_digitos(parte["documento_numero"])
                titular = RC.e_titular(parte["papel"])
                # A QUALIFICACAO VOLTA PARA A LINHA, e este e o outro lado do
                # campo escondido — sem isto o campo invisivel nao serve de nada.
                # A corrente inteira ja a carregava: `voltar_do_ato` copia a
                # qualificacao de `ri_partes` para a minuta, a ficha a devolve no
                # bloco e `_partes_da_tela` a le. Ate 18/09/2026 ela MORRIA aqui,
                # porque este INSERT nao a gravava — re-lavrar um ato suspenso
                # apagava a qualificacao que o ato tinha, e ela e o que o modelo
                # do ato escreve ao lado do nome do transmitente
                # (`_contexto_modelo`). Some sem erro em lugar nenhum: o campo
                # fica em branco no papel.
                #
                # O TIPO DO DOCUMENTO CONTINUA SAINDO DO TAMANHO, que e a regra
                # desta tela, e o tipo informado entra como recurso quando o
                # documento nao decide — a linha que veio do acervo sem numero e
                # com o tipo gravado nao pode perder o tipo.
                #
                # E ELE TEM NOME PROPRIO — LD03, 21/10/2026. Chamava-se `tipo`,
                # o mesmo nome do tipo do ATO, e o laco o trocava: com partes,
                # o rotulo da consulta CNIB, a auditoria e o recado da tela
                # saiam «CPF-1» no lugar de «R-1».
                tipo_documento = ("CPF" if len(doc) == 11
                                  else "CNPJ" if len(doc) == 14
                                  else (parte["documento_tipo"] or None))
                bd.escrever(
                    """INSERT INTO ri_partes
                       (matricula_id, ato_id, nome, nome_norm, documento_tipo,
                        documento_numero, documento_valido, papel, qualificacao,
                        proprietario, proprietario_ativo, origem)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, 'MANUAL')""",
                    (matricula_id, ato_id, nome, normalizar_busca(nome),
                     tipo_documento, doc or None,
                     1 if doc and valida_cpf_cnpj(doc) else 0,
                     parte["papel"] or None, parte["qualificacao"],
                     1 if titular else 0, 1 if titular else 0),
                )
            consulta_cnib = CNIB.gravar_consulta_do_ato(
                con, ato_id=ato_id, matricula_id=matricula_id,
                ato_rotulo=f"{tipo}-{numero}", base_ate=cnib_base,
                protocolo_consulta=cnib_protocolo,
                quem=(app.extensions["usuario_nome"]() or "").strip() or None,
                agora=db.now())
            # A MINUTA NAO SE APAGA AO VIRAR ATO: ela e a prova de que aquele
            # texto existia antes, e de onde ele veio. Na MESMA transacao do
            # ato — se o ato nao entrar, a minuta continua na fila.
            if minuta:
                RIMIN.marcar_lavrada(con, minuta["id"], ato_id=ato_id,
                                     agora=db.now(),
                                     usuario=_quem_mexeu_na_minuta())
            # O ENCERRAMENTO ENTRA NA MESMA TRANSAÇÃO DO ATO. Fora dela, um
            # erro entre as duas deixaria a ficha fechada sem o ato que a
            # fechou — ou o ato no livro com a ficha aberta.
            if encerra:
                _marcar_a_ficha_encerrada(
                    bd, matricula_id, motivo=encerra_motivo,
                    destino=encerra_destino, data_ato=data_ato)

        # O SELO SAI AGORA, COM O ATO JA LAVRADO — e FORA da transação dele.
        #
        #   A chamada ao selador leva ate 20 s. Dentro do `db.transaction()`
        #   ela seguraria o `BEGIN IMMEDIATE` esse tempo todo e poria todo
        #   outro balcao no `busy_timeout`. E por isso que `selar_o_ato_
        #   lavrado` recebe `db`, e nao `con`.
        #
        #   O QUE ACONTECE QUANDO O SELO NAO SAI — e este comentario dizia o
        #   contrario do que o codigo fazia treze linhas abaixo.
        #
        #   Dizia «SELO RECUSADO NAO DERRUBA O ATO, porque quando a recusa
        #   chega o ato ja esta gravado e na cadeia de hash». Era verdade ate
        #   15/09/2026: o ato ficava, marcado, e aparecia em `atos_sem_selo`.
        #   **Desde essa data ele nao fica** — a menos que quem lavra marque a
        #   autorizacao expressa na tela, que e a regra que as telas mostram ao
        #   operador («Lavrar mesmo se o selo falhar, por decisao de quem esta
        #   lavrando. Sem marcar, o sistema bloqueia/cancela e mostra o motivo»).
        #
        #   As duas coisas continuam verdadeiras e explicam o desenho: o ato
        #   NAO se apaga — ele foi gravado, entrou na cadeia e fica na ficha
        #   marcado como cancelado, com o motivo escrito (senao a cadeia
        #   teria um buraco e o livro mentiria); e a chamada do selador NUNCA
        #   acontece dentro da transacao, porque vinte segundos segurando o
        #   BEGIN IMMEDIATE poriam a casa inteira no busy_timeout.
        # VARIOS SELOS NO MESMO ATO — Beatriz 23/09/2026. Antes só o
        # primeiro codigo_tj ia ao aparelho; os demais iam só no fecho de
        # emolumentos. Agora cada unidade da fila vira selo de verdade.
        # Preferir multi-selo (com quantidade) quando preenchido; o merge
        # antigo com «if c not in» descartava a 2a unidade do mesmo codigo.
        if tem_multi_selo:
            fila_selos = list(_codigos_de_selo_do_form(request.form))
        else:
            fila_selos = list(codigos_escolhidos) if codigos_escolhidos else (
                [codigo_tj] if codigo_tj else [])
        saiu_do_selo = _selar_itens_do_ato_do_ri(
            ato_id=ato_id, tipo=tipo, numero=numero, matricula=m,
            base_calculo=base_calculo, codigos_tj=fila_selos,
            descricao_natureza=(request.form.get("natureza_titulo") or ""),
            protocolo=request.form.get("protocolo"),
            partes=list(zip(request.form.getlist("parte_nome"),
                            request.form.getlist("parte_documento"))),
            selo_a_mao=request.form.get("selo_texto"),
            isento=isento, motivo_isencao=motivo_isencao)
        recado_do_selo = saiu_do_selo["recado"]

        # O SELO RECUSADO SUSPENDE O ATO, E ELE VOLTA A SER MINUTA —
        # 16/09/2026, ordem do oficial: «selo recusado suspende ato (fica
        # salvo como minuta para lavrar de novo)».
        #
        #   ISTO INVERTE A REGRA QUE ESTAVA AQUI, e a inversao e dele. O que
        #   estava escrito — «selo recusado nao derruba ato que ja existe» —
        #   nasceu em agosto de um bom motivo (balcao parado e pior que selo
        #   atrasado), e o que ele produziu esta medido: os AV-04, AV-05 e
        #   AV-06 da 3.110 nasceram lavrados e sem selo, entraram na corrente
        #   de hash, um deles encerrou a ficha, e desfazer aquilo custou tres
        #   ferramentas e dois dias.
        #
        #   E ISTO NAO E O CANCELAMENTO DE 15/09, que ele tambem recusou. Ali
        #   o ato FICAVA no livro marcado como cancelado — «ato cancelado nao
        #   se descancela sozinho». Aqui ele **nao chega a ficar**: volta a
        #   ser minuta, com o teor, a qualificacao e as PARTES, e se lavra de
        #   novo quando o aparelho voltar. Nada do trabalho se perde; o que
        #   nao acontece e o ato meio pronto no livro.
        #
        #   O QUE MUDA NO BALCAO, e ele sabe: **um ato so existe depois de o
        #   selo sair**. Com o selador fora do ar nao se lavra — e nao ha
        #   caixa de «lavrar mesmo assim»: ela saiu em 16/09 pelo relato #77.
        #
        #   E TODO SELO QUE NAO SAI SUSPENDE, desde o item 1 de 16/09/2026.
        #   Ate ali a suspensao exigia que o aparelho apontado tivesse
        #   RECUSADO; a casa sem selador configurado lavrava sem selo. Sao a
        #   mesma coisa no livro, e as duas se corrigem.
        #
        #   O QUE CONTINUA LAVRANDO e so o que quem atende nao tem como
        #   corrigir — o ato de ACERVO sem item de custa, dispensado por ele
        #   no mesmo dia. Suspende-lo poria aquele ato num laco sem saida, e a
        #   ficha nunca receberia o proprio livro.
        motivo_selo = _motivo_da_falha_do_selo(recado_do_selo)
        if motivo_selo and saiu_do_selo["suspende"]:
            try:
                with db.transaction() as con:
                    CNIB.soltar_do_ato(con, ato_id)
                    voltou = RIMIN.voltar_do_ato(
                        con, ato_id, agora=db.now(),
                        por=_quem_mexeu_na_minuta(), motivo=motivo_selo)
                    # A UNIDADE DO PROTOCOLO VOLTA JUNTO — senao o cliente
                    # paga cinco averbacoes e o sistema oferece quatro. Quem
                    # sabe devolver e `caixa_protocolo`; aqui so se diz
                    # quais itens este ato tinha consumido, que sao os
                    # mesmos que a tela marcou.
                    for item_id in ids_protocolo_item:
                        CXPROT.devolver_item(con, int(item_id), quantas=1)
            except (RIMIN.MinutaError, sqlite3.Error) as erro:
                # SUSPENDER FALHOU: o ato FICA, e a tela diz as duas coisas.
                # Sumir com o ato aqui seria o pior dos mundos — nem lavrado,
                # nem guardado.
                # A MARCA DIZ AS DUAS FALHAS, e e por isso que ela tem nome
                # proprio desde 16/09/2026 (item 2, ordem dele). Ela se
                # chamava `..._POR_DECISAO`, e aqui ninguem decidiu nada: o
                # selo nao saiu E o ato nao pode voltar para minuta.
                audit("RI_ATO_LAVRADO_SEM_SELO_SUSPENSAO_FALHOU", "RI_ATO",
                      ato_id,
                      {"matricula": m["numero"], "ato": f"{tipo}-{numero}",
                       "hash": h, "motivo": motivo_selo,
                       "suspensao_falhou": str(erro)})
                flash(f"O selo não saiu ({motivo_selo}) e o ato NÃO pôde ser "
                      f"suspenso: {erro} Ele continua lavrado e aparece na "
                      f"lista de atos sem selo.", "danger")
                return redirect(url_for("ri_ficha", matricula_id=matricula_id))

            audit("RI_ATO_SUSPENSO_SEM_SELO", "RI_ATO", ato_id,
                  {"matricula": m["numero"], "ato": voltou["rotulo"],
                   "hash": h, "motivo": motivo_selo,
                   "minuta_id": voltou["minuta_id"],
                   "partes_guardadas": voltou["partes"],
                   "minuta_reaproveitada": voltou["reaproveitou"]})
            # A FRASE DIZ QUAL DAS DUAS COISAS CORRIGIR, e as duas pedem
            # providencias diferentes de quem esta no balcao: aparelho que
            # recusou se resolve corrigindo o ato e lavrando de novo; aparelho
            # que ninguem apontou se resolve em Administrativo → Selador, e
            # quem faz isso nao e quem atende.
            if not _o_selador_esta_pronto():
                motivo_selo = (
                    f"{motivo_selo} O selador ainda não foi apontado nesta "
                    "instalação — o endereço e a credencial se informam em "
                    "Administrativo → Selador.")
            flash(f"O selo não saiu: {motivo_selo} O ato {voltou['rotulo']} "
                  f"NÃO foi lavrado — o texto"
                  + (f" e as {voltou['partes']} partes" if voltou["partes"]
                     else "")
                  + " ficaram guardados na minuta, em «Minutas a revisar e "
                    "lavrar». Corrija o que faltou e lavre de novo.",
                  "warning")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id,
                                    minuta=voltou["minuta_id"]))

        # QUEM TRANSMITIU SAI DO QUADRO DE TITULARES — LD03, 21/10/2026, e SÓ
        # AGORA, com o ato de pé. Na transação do ato, a suspensão de cima
        # apagaria as partes novas (`voltar_do_ato`) e deixaria o vendedor já
        # fora: a matrícula ficaria sem dono nenhum. A regra é de
        # `ri_correcoes`, ao lado da que diz quem é titular.
        #
        # E O QUE DÁ ERRADO AQUI NÃO VIRA 500 — LD10, 21/10/2026 (ressalva da
        # revisão do LD03). Esta transação é a segunda: quando ela abre, o ato
        # já está no livro, com número, hash e selo. Um erro aqui (a trava da
        # ficha que não veio, a conexão que caiu) virava a tela de erro com o
        # R-1 lavrado e o vendedor ainda titular — e quem lavrou ia achar que
        # nada tinha saído. Agora o quadro fica como estava (a transação volta
        # inteira), o ato fica de pé, e a pendência vai para a auditoria e
        # para o recado, com o caminho do conserto.
        #
        # SÓ O ERRO DO BANCO VIRA RECADO — LD13, 21/10/2026 (ressalva da
        # revisão do LD10). O LD10 apanhava `Exception`, e o defeito de
        # programação (o `TypeError` de amanhã em `titulares_que_transmitiram`)
        # virava um recado e uma linha de auditoria, sem rastro no log de erro.
        # Agora o recado é para o que o banco recusou (`ERROS_DO_BANCO`: a
        # trava da ficha que não veio, a conexão que caiu), e o traceback vai
        # ao log também — a auditoria guarda só a frase. O resto sobe para a
        # tela de erro, que o anota com o traceback. A auditoria de dentro do
        # `except` não pode trazer de volta o 500 que ele evita: o banco que
        # recusou o quadro pode recusar a linha dela também.
        quadro = {"sairam": [], "a_conferir": []}
        quadro_falhou = None
        try:
            with db.transaction() as con:
                quadro = RC.titulares_que_transmitiram(
                    con, matricula_id, ato_id, partes_do_ato)
        except ERROS_DO_BANCO as erro:
            quadro_falhou = str(erro) or erro.__class__.__name__
            app.logger.error(
                "Lavratura do %s-%s da matrícula %s: o ato ficou de pé e o "
                "quadro de titulares não foi atualizado.", tipo, numero,
                m["numero"], exc_info=erro)
            try:
                audit("RI_TITULARES_NAO_ATUALIZADOS", "RI_ATO", ato_id,
                      {"matricula": m["numero"], "ato": f"{tipo}-{numero}",
                       "erro": quadro_falhou,
                       "transmitentes": [p["nome"] for p in partes_do_ato
                                         if RC.e_transmitente(p["papel"])]})
            except Exception as falha_do_rastro:  # noqa: BLE001 — o ato já está lavrado
                app.logger.error(
                    "A auditoria RI_TITULARES_NAO_ATUALIZADOS do ato %s não foi "
                    "gravada.", ato_id, exc_info=falha_do_rastro)
        # O HOMÔNIMO NÃO SAI, E A TELA E A AUDITORIA DIZEM — LD10: o
        # transmitente que o documento não identifica fica no quadro, e quem
        # decide qual linha é a dele é gente, em «Corrigir».
        if quadro["a_conferir"]:
            audit("RI_TITULARES_A_CONFERIR", "RI_ATO", ato_id,
                  {"matricula": m["numero"], "ato": f"{tipo}-{numero}",
                   "sairam": quadro["sairam"], "a_conferir": quadro["a_conferir"]})
        sairam_da_titularidade = quadro["sairam"]
        recado_dos_titulares = (
            f" {', '.join(sairam_da_titularidade)} deixou(aram) de figurar "
            f"como titular(es) atual(is) — a transmissão foi lançada neste "
            f"ato. Se foi de parte ideal, ponha de volta em Partes → "
            f"Corrigir (titular), com o motivo."
            if sairam_da_titularidade else "")
        if quadro["a_conferir"]:
            recado_dos_titulares += (" Quadro de titulares a conferir: "
                                     + " ".join(quadro["a_conferir"]))
        if quadro_falhou:
            recado_dos_titulares += (
                f" O ato ficou lavrado, mas o quadro de titulares NÃO foi "
                f"atualizado ({quadro_falhou}): quem transmitiu continua como "
                f"titular atual. Tire-o em Partes → Corrigir (titular), com o "
                f"motivo.")

        motivo_selo = _motivo_da_falha_do_selo(recado_do_selo)
        if motivo_selo:
            # CHEGA AQUI SO O QUE NAO SE SUSPENDE — hoje, o ato de ACERVO sem
            # item de custa. A marca se chamava `..._POR_DECISAO` e ninguem
            # decidiu nada: falta uma coisa no cadastro, e e isso que ela diz
            # desde 16/09/2026 (item 2, ordem dele).
            audit("RI_ATO_LAVRADO_SEM_SELO_FALTA_NO_CADASTRO", "RI_ATO",
                  ato_id,
                  {"matricula": m["numero"], "ato": f"{tipo}-{numero}",
                   "hash": h, "motivo": motivo_selo,
                   "minuta_id": minuta["id"] if minuta else None,
                   "encerrou_a_ficha": encerra or None})

        audit("RI_ATO_LAVRADO", "RI_ATO", ato_id,
              {"matricula": m["numero"], "ato": f"{tipo}-{numero}", "hash": h,
               "selo": recado_do_selo.strip() or None,
               "minuta_id": minuta["id"] if minuta else None,
               "encerrou_a_ficha": encerra or None,
               "motivo_encerramento": encerra_motivo or None,
               "cnib": {"fonte": consulta_cnib["fonte"],
                        "base_ate": consulta_cnib["base_ate"],
                        "protocolo": consulta_cnib["protocolo_consulta"],
                        "resultado": consulta_cnib["resultado"]}})
        if encerra:
            audit("RI_MATRICULA_ENCERRADA", "RI_MATRICULA", matricula_id,
                  {"numero": m["numero"], "motivo": encerra_motivo,
                   "destino": encerra_destino,
                   "averbacao": f"{tipo}-{numero:02d}",
                   "lavrado_pela_tela_de_atos": True})
        # SELO DE ARQUIVAMENTO OPCIONAL — depois do selo do ato, e so se o
        # ato ficou lavrado (nao suspenso). Falha de arquivamento NAO derruba
        # o ato: estado claro "ato ok / arquivamento pendente".
        recado_do_arquivamento = ""
        if gerar_arquivamento and folhas_arquivamento:
            # So pede se o ato tem selo (ou ficou sem selo por falta de cadastro
            # de acervo, que nao suspende). Se suspendeu, ja retornou acima.
            partes_arq = list(zip(request.form.getlist("parte_nome"),
                                  request.form.getlist("parte_documento")))
            # Numero do selo do ato recem-gravado (para restaurar selo_texto).
            with db.connect() as _c_arq:
                _row_arq = banco(_c_arq).um(
                    "SELECT selo_texto FROM ri_atos WHERE id=%s",
                    (ato_id,))
                selo_ato_atual = (_row_arq["selo_texto"] if _row_arq else None)
            arq = _selar_arquivamento_do_ri(
                ato_id=ato_id, folhas=folhas_arquivamento,
                selo_do_ato=selo_ato_atual, partes=partes_arq,
                isento=isento, motivo_isencao=motivo_isencao)
            if arq.get("ok"):
                recado_do_arquivamento = arq["recado"]
                audit("RI_ATO_ARQUIVAMENTO_SELADO", "RI_ATO", ato_id,
                      {"matricula": m["numero"], "ato": f"{tipo}-{numero}",
                       "selo": arq["numero"], "folhas": arq["folhas"]})
            else:
                recado_do_arquivamento = (
                    f" Arquivamento PENDENTE ({folhas_arquivamento} folha(s)): "
                    f"{arq.get('motivo')}. O ato ficou lavrado; use "
                    f"«Selar arquivamento» na ficha para tentar de novo.")
                audit("RI_ATO_ARQUIVAMENTO_PENDENTE", "RI_ATO", ato_id,
                      {"matricula": m["numero"], "ato": f"{tipo}-{numero}",
                       "folhas": folhas_arquivamento,
                       "motivo": arq.get("motivo")})

        flash(f"{tipo}-{numero} lavrado. O ato entrou na cadeia de integridade e "
              f"não pode mais ser editado — correções se fazem por averbação."
              f"{' A minuta que estava para revisão saiu da fila.' if minuta else ''}"
              + (f" A matrícula {m['numero']} foi ENCERRADA por este ato, e "
                 f"nenhuma averbação adicional foi lavrada — não é mais "
                 f"possível lavrar atos nela." if encerra else "")
              + f"{recado_da_prenotacao(amarrado)}{recado_do_selo}{recado_do_arquivamento}"
              + recado_dos_titulares
              + CNIB.recado_da_consulta(consulta_cnib),
              "warning" if ("SEM SELO" in recado_do_selo
                            or "PENDENTE" in recado_do_arquivamento
                            or consulta_cnib["resultado"] == CNIB.POSITIVO
                            or quadro["a_conferir"] or quadro_falhou)
              else "success")
        return redirect(url_for("ri_ficha", matricula_id=matricula_id))

    @app.route("/registro-imoveis/<int:matricula_id>/minuta", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_minuta_criar(matricula_id):
        """Guarda uma minuta digitada na ficha, SEM lavrar.

        `RIMIN.criar` existia e nada a chamava — o defeito pago seis vezes:
        função pronta, tela nenhuma. A origem é `MANUAL` porque alguém
        escreveu aqui, e não veio de importação nem de ato desfeito.

        ELA NÃO LAVRA. A minuta entra `A_REVISAR` e cai no mesmo painel da
        ficha. Quem a transforma em ato é a rota de sempre.
        """
        if not q1("SELECT id FROM ri_matriculas WHERE id=%s", (matricula_id,)):
            abort(404)
        voltar = redirect(url_for("ri_ficha", matricula_id=matricula_id))
        try:
            with db.transaction() as con:
                minuta_id = RIMIN.criar(
                    con, matricula_id=matricula_id,
                    tipo=request.form.get("tipo") or "",
                    teor=request.form.get("teor") or "",
                    numero_pretendido=request.form.get("numero") or None,
                    data_pretendida=request.form.get("data_ato") or None,
                    natureza_titulo=request.form.get("natureza_titulo") or None,
                    protocolo=request.form.get("protocolo") or None,
                    origem=RIMIN.MANUAL,
                    agora=db.now(), usuario=_quem_mexeu_na_minuta())
        except RIMIN.MinutaError as e:
            flash(str(e), "danger")
            return voltar
        audit("RI_MINUTA_CRIADA", "RI_MINUTA", minuta_id,
              {"matricula_id": matricula_id, "origem": RIMIN.MANUAL})
        flash("Minuta na fila de revisão. Nenhum ato foi lavrado — "
              "ela espera «Revisar e lavrar».", "success")
        return voltar

    @app.route("/registro-imoveis/minuta/<int:minuta_id>/guardar",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_minuta_guardar(minuta_id):
        """Guarda a revisão da minuta SEM lavrar.

        REVISAR PODE LEVAR MAIS DE UMA SENTADA — 15/09/2026. Sem esta rota, a
        correção de uma vírgula só existia dentro do formulário de lavrar: quem
        saísse da tela perdia o trabalho, e no dia seguinte ou redigitava ou
        lavrava com o erro dentro. **Ato lavrado não se edita** — o conserto
        seria uma averbação.

        ELA É DO BALCÃO, como lavrar: escrever o ato é o trabalho de quem
        atende. O que é do oficial é descartar e encerrar.
        """
        with db.connect() as _c:
            m0 = RIMIN.uma(_c, minuta_id)
        if not m0:
            abort(404)
        matricula_id = int(m0["matricula_id"])
        voltar = redirect(url_for("ri_ficha", matricula_id=matricula_id,
                                  minuta=minuta_id))
        try:
            with db.transaction() as con:
                RIMIN.atualizar(
                    con, minuta_id,
                    teor=request.form.get("teor") or "",
                    tipo=request.form.get("tipo"),
                    numero_pretendido=request.form.get("numero"),
                    data_pretendida=request.form.get("data_ato"),
                    natureza_titulo=request.form.get("natureza_titulo"),
                    protocolo=request.form.get("protocolo"),
                    prenotacao=request.form.get("prenotacao"),
                    partes=_partes_da_revisao(request.form),
                    agora=db.now(), usuario=_quem_mexeu_na_minuta())
        except RIMIN.MinutaError as e:
            flash(str(e), "danger")
            return voltar
        audit("RI_MINUTA_REVISADA", "RI_MINUTA", minuta_id,
              {"matricula_id": matricula_id})
        flash("Revisão guardada. A minuta continua esperando lavratura — "
              "nenhum ato foi lavrado, nenhum número foi tomado e nenhum selo "
              "foi pedido.", "success")
        return voltar

    @app.route("/registro-imoveis/minuta/<int:minuta_id>/descartar",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER")  # F12: oficial/gerente; não o balcão
    def ri_descartar_minuta(minuta_id):
        """Tira a minuta da fila sem lavrar. EXIGE MOTIVO ESCRITO.

        DESCARTAR E DECISAO, e decisao sem motivo escrito e decisao que ninguem
        confere depois — a mesma regua da dispensa no usucapiao e da reabertura
        da matricula. E a minuta **nao some**: fica na tabela com o motivo,
        porque a pergunta que aparece meses depois e «e aquela averbacao que
        estava para sair?».

        E DO OFICIAL, e nao do balcao: quem revisa e lavra e quem atende
        (`ri_lavrar_ato` aceita USER), mas dizer que um texto pronto nao vai
        virar ato e a mesma decisao de nao praticar o ato.
        """
        with db.connect() as _c:
            m0 = RIMIN.uma(_c, minuta_id)
        if not m0:
            abort(404)
        matricula_id = int(m0["matricula_id"])
        try:
            with db.transaction() as con:
                RIMIN.descartar(con, minuta_id,
                                motivo=request.form.get("motivo") or "",
                                agora=db.now(),
                                usuario=_quem_mexeu_na_minuta())
        except RIMIN.MinutaError as e:
            flash(str(e), "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))
        audit("RI_MINUTA_DESCARTADA", "RI_MINUTA", minuta_id,
              {"matricula_id": matricula_id,
               "motivo": (request.form.get("motivo") or "").strip()})
        flash("Minuta descartada. Ela sai da fila de revisão e continua "
              "guardada com o motivo, para quem perguntar depois.", "success")
        return redirect(url_for("ri_ficha", matricula_id=matricula_id))

    @app.route("/registro-imoveis/<int:matricula_id>/selar-abertura",
               methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def ri_selar_abertura(matricula_id):
        """Sela a ABERTURA de uma matricula que ja existe. FALA COM A REDE.

        PEDIDO DO OFICIAL EM 16/09/2026: «como emito e coloco o selo de
        abertura de matricula nessa 4016».

        O BURACO QUE ELA FECHA, e ele era total. Medido em 16/09: das **1.982**
        matriculas desta casa, **zero** tem `selo_abertura_texto`. A coluna
        existe desde sempre; a unica linha que a escrevia e o INSERT de
        `ri_nova_matricula`, lendo um campo de formulario que **nenhuma tela
        oferece** — `grep` nos modelos nao acha um. Ela era LIDA para o `.odt`
        da ficha e nunca escrita por ninguem. Nao faltava um botao: faltava o
        caminho inteiro.

        O CAMINHO E O ITEM SAO MEDIDOS, E NAO ESCOLHIDOS. O item `16.2`
        («Matricula de imoveis no Registro Geral») saiu 41 vezes por
        `/selo/imovel/lote/subdivisao`, e o 16.2 e o **unico** item daquele
        caminho; o envelope tem forma propria — `naturezaTitulo` **127.0** e
        nao 126.0, sem `registroAverbacao` e sem `descricaoNatureza`. Ver
        `ato_selado.envelope_da_abertura_da_matricula`.

        ELA PERGUNTA A PRENOTACAO, E NAO A ADIVINHA. O envelope leva o numero
        da prenotacao dentro, e na 4.016 havia **duas candidatas**: o
        documento de abertura diz **11.559** (que existe, esta aberta e nao
        tem protocolo de caixa ligado) e o item 16.2 ainda nao usado esta no
        caixa da prenotacao **11571**. Escolher por conta propria seria
        assinar por quem protocolou — «onde o erro custa dinheiro do cliente,
        quem responde e a pessoa».

        DOIS SELOS PARA A MESMA ABERTURA E O DINHEIRO DA SERVENTIA SAINDO
        DUAS VEZES: ficha que ja tem selo de abertura e recusada, dizendo qual
        e. E **ela nao lavra ato, nao numera e nao toca no teor** — a abertura
        nao e ato de `ri_atos`, e por isso nenhuma corrente de hash e mexida.
        """
        import selo_robo as SR
        if SR.exige_humano_para_selar():
            abort(403)
        m = q1("SELECT * FROM ri_matriculas WHERE id=%s", (matricula_id,))
        if not m:
            abort(404)
        voltar = redirect(url_for("ri_ficha", matricula_id=matricula_id))

        if (str(m["tipo_ficha"] or "").strip().upper() == "ACERVO"
                or matricula_de_acervo(m["numero"])):
            flash(f"A matrícula {m['numero']} é de acervo: a abertura segue "
                  f"o conteúdo importado e não recebe selo de abertura do "
                  f"sistema.", "warning")
            return voltar

        if str(m["selo_abertura_texto"] or "").strip():
            flash(f"A matrícula {m['numero']} já tem selo de abertura: "
                  f"{m['selo_abertura_texto']}. Dois selos para a mesma "
                  f"abertura é o dinheiro da serventia saindo duas vezes.",
                  "warning")
            return voltar

        codigo_tj = (request.form.get("codigo_tj") or "").strip() or None
        prenotacao = (request.form.get("prenotacao") or "").strip() or None
        folha = (request.form.get("folha") or "").strip() or None
        isento, motivo_isencao = ler_isencao_do_form(request.form)
        motivo_isencao = motivo_isencao or ""
        selo_a_mao = (request.form.get("selo_abertura_texto") or "").strip()
        emolumentos = (request.form.get("emolumentos_abertura") or "").strip()

        # A RECUSA E AQUI, COM O CLIENTE NA FRENTE — a mesma razao da rota que
        # lavra: o envelope tambem recusaria, mas la a resposta vem da rede.
        if isento and not motivo_isencao:
            flash("Abertura gratuita precisa do motivo escrito — é ele que "
                  "sai dentro do selo e que a correição lê.", "danger")
            return voltar
        if not selo_a_mao and not codigo_tj:
            flash("Para selar a abertura, escolha o item da tabela de custas "
                  "— o padrão é o 16.2, «Matrícula de imóveis no Registro "
                  "Geral», que é o que esta casa usou 41 vezes.", "danger")
            return voltar
        # AS PARTES SAO O QUE O ENVELOPE PEDE, e a recusa e antes da rede:
        # foi exatamente isto que derrubou o selo da AV-05 em 15/09 — «Os
        # nomes das partes devem ser informados», e a resposta veio do
        # aparelho depois de o ato existir.
        partes = [{"nome": r["nome"], "documento": r["documento_numero"]}
                  for r in q("""SELECT nome, documento_numero FROM ri_partes
                                 WHERE matricula_id=%s AND ato_id IS NULL
                                 ORDER BY id""", (matricula_id,))]
        if not selo_a_mao and not partes:
            flash("Para selar a abertura, a ficha precisa de quem é o dono do "
                  "imóvel: o selo exige os nomes das partes, e esta matrícula "
                  "não tem nenhuma cadastrada.", "danger")
            return voltar
        # O PROTOCOLO QUE PAGA O SELO (22/10/2026, trava do selo pago).
        if not selo_a_mao:
            recusa = _atender_o_protocolo_escolhido(request.form)
            if recusa:
                flash(recusa, "danger")
                return voltar

        # O QUE FOI INFORMADO FICA NA FICHA, E ANTES DA REDE — se o aparelho
        # nao responder, a relacao de emolumentos digitada nao se perde.
        if emolumentos:
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE ri_matriculas SET emolumentos_abertura=%s
                        WHERE id=%s""", (emolumentos, matricula_id))

        if selo_a_mao:
            # O SELO DIGITADO A MAO PASSA PELO RAZAO, e nao so pela coluna —
            # `registrar_selo_obtido_a_mao` le o codigo, confere o CNS contra
            # o da serventia e recusa selo repetido dizendo onde ele ja esta.
            import selo_no_papel as SNP
            codigo = str((SNP.ler(selo_a_mao) or {}).get("codigo") or "").strip()
            try:
                if codigo:
                    with db.transaction() as con:
                        AS.registrar_selo_obtido_a_mao(
                            con, codigo, tabela="ri_matriculas",
                            ato_id=matricula_id, atribuicao="IMOVEL",
                            agora=datetime.now().isoformat(timespec="seconds"),
                            cns=db.get_setting("ri_cns", ""),
                            usuario=app.extensions["usuario_nome"](),
                            texto=selo_a_mao)
            except AS.AtoError as erro:
                flash(f"O selo digitado não entrou: {erro}", "danger")
                return voltar
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE ri_matriculas SET selo_abertura_texto=%s
                        WHERE id=%s""", (selo_a_mao, matricula_id))
            audit("RI_ABERTURA_SELADA_A_MAO", "RI_MATRICULA", matricula_id,
                  {"matricula": m["numero"],
                   "selo": codigo or selo_a_mao[:40],
                   "no_razao": bool(codigo)})
            flash(f"Selo de abertura gravado na matrícula {m['numero']}."
                  + ("" if codigo else " O código não foi reconhecido no texto "
                     "colado, então ele não entrou no razão dos selos — "
                     "confira a etiqueta."), "success")
            return voltar

        versao = AS.versao_da_tabela_de_custas(
            AS.CAMINHO_DA_ABERTURA,
            db.get_setting("selo_tabela_custas_em", ""))
        if not versao:
            flash("O selo não saiu: falta dizer de que data é a tabela de "
                  "custas em vigor, em Administrativo / Configuracoes.",
                  "danger")
            return voltar
        try:
            envelope = AS.envelope_da_abertura_da_matricula(
                matricula=m["numero"],
                escrevente=app.extensions["usuario_nome"](),
                versao_tabela=versao,
                # O LIVRO E O VOLUME DA MATRICULA ('2', '2-Q'), e nao o `1A`
                # do livro de protocolo — a mesma regra do selo do ato.
                livro=m["livro"], codigo_tj=codigo_tj,
                protocolo=prenotacao, folha=folha, partes=partes,
                isento=isento, motivo_isencao=motivo_isencao or None)
        except AS.AtoError as erro:
            flash(f"O selo da abertura não saiu: {erro}", "danger")
            return voltar

        r = AS.selar_o_ato_lavrado(
            db, Path(app.config["DATA_DIR"]), tabela="ri_matriculas",
            ato_id=matricula_id, tipo="ABERTURA", atribuicao="IMOVEL",
            agora=datetime.now().isoformat(timespec="seconds"),
            cns=db.get_setting("ri_cns", ""),
            usuario=app.extensions["usuario_nome"](), dados=envelope,
            caminho=AS.CAMINHO_DA_ABERTURA,
            referencia=f"ri_matriculas:{int(matricula_id)}")

        audit("RI_ABERTURA_SELADA", "RI_MATRICULA", matricula_id,
              {"matricula": m["numero"], "codigo_tj": codigo_tj,
               "prenotacao": prenotacao,
               "selo": r.get("numero") or None,
               "motivo": None if r["selado"] else r.get("motivo")})
        if not r["selado"]:
            # A ABERTURA NAO SE DESFAZ PORQUE O SELO NAO SAIU: a ficha existe,
            # tem teor e tem dono. E a regra escrita desde agosto — balcao
            # parado e pior que selo atrasado —, e aqui ela e mais forte
            # ainda, porque a matricula ja estava aberta antes deste clique.
            flash(f"O selo da abertura NÃO saiu: {r['motivo']} A matrícula "
                  f"{m['numero']} continua aberta; corrija e tente de novo.",
                  "warning")
        else:
            flash(f"Abertura da matrícula {m['numero']} selada: "
                  f"{r['numero']}.", "success")
        return voltar


    @app.route("/registro-imoveis/protocolo/<int:protocolo_id>/selar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_selar_prenotacao(protocolo_id):
        """Sela prenotacao pendente — so humano. Robo recebe 403."""
        import selo_robo as SR
        if SR.exige_humano_para_selar():
            abort(403)
        p = q1("SELECT * FROM ri_protocolos WHERE id=%s", (protocolo_id,))
        if not p:
            abort(404)
        if (p["selo_prenotacao"] or "").strip():
            flash(f"Prenotação {p['numero']} já tem selo: {p['selo_prenotacao']}.",
                  "warning")
            return redirect(url_for("ri_protocolo_ver", protocolo_id=protocolo_id))
        recusa = _atender_o_protocolo_escolhido(request.form)
        if recusa:
            flash(recusa, "danger")
            return redirect(url_for("ri_protocolo_ver", protocolo_id=protocolo_id))
        selado = _selar_a_prenotacao(protocolo_id, p["numero"], request.form,
                                     gravado=p)
        motivo = _motivo_da_falha_do_selo(selado)
        if motivo:
            flash(f"Não selou a prenotação: {motivo}", "danger")
        else:
            audit("RI_PRENOTACAO_SELADA", "RI_PROTOCOLO", protocolo_id,
                  {"via": "botao_selar"})
            flash(f"Prenotação {p['numero']} selada.{selado}", "success")
        return redirect(url_for("ri_protocolo_ver", protocolo_id=protocolo_id))

    @app.route("/registro-imoveis/ato/<int:ato_id>/selar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_selar_ato(ato_id):
        """Sela um ato do RI QUE JA ESTA LAVRADO. FALA COM A REDE.

        PEDIDO DO OFICIAL EM 15/09/2026, sobre as minutas importadas: «tres
        atos devem ficar em pe, quero revisar no sistema e poder lavrar
        efetivamente (selando) depois».

        O BURACO QUE ELA FECHA. O selo do RI so existia DENTRO da lavratura —
        `_selar_o_ato_do_ri` era chamado numa linha so, na rota que lavra. Ato
        que nascesse sem selo (a maquina fora do ar, ou a minuta importada que
        entrou como ato) nao tinha por onde ser selado depois: a tela «Selos»
        e razao, lista o que JA tem selo. Medido em 15/09: os AV-04, AV-05 e
        AV-06 da matricula 3.110, com `selo_texto` vazio e nenhum botao.

        ELA PERGUNTA TRES COISAS, E NAO ADIVINHA NENHUMA. O envelope exige item
        da tabela de custas, natureza do titulo e valor declarado (e o valor e
        quem escolhe o caminho com-valor ou sem-valor). Medido no banco vivo:
        `codigo_tj` e `base_calculo_centavos` estao preenchidos em **zero dos
        1.248** atos, e `natureza_titulo` em **tres**. Nao ha de onde puxar —
        logo se pergunta, e o que for informado FICA GRAVADO no ato: selo que
        sai declarando o que a ficha nao registra e carimbo sem lastro.

        E ELA FUNCIONA COM A MATRICULA ENCERRADA, de proposito. Selar nao lavra
        ato, nao toma numero e **nao entra na corrente de hash** — `hash_ato`
        recebe numero da matricula, tipo, numero, data, teor e hash anterior, e
        o selo nao esta entre eles. Barrar aqui seria trancar justamente o selo
        do ato que fechou o livro, que e o caso que fez isto nascer.

        DOIS SELOS PARA O MESMO ATO E O DINHEIRO DA SERVENTIA SAINDO DUAS
        VEZES: ato que ja tem selo e recusado, dizendo qual e.
        """
        import selo_robo as SR
        if SR.exige_humano_para_selar():
            abort(403)
        a = q1("SELECT * FROM ri_atos WHERE id=%s", (ato_id,))
        if not a:
            abort(404)
        m = q1("SELECT * FROM ri_matriculas WHERE id=%s", (a["matricula_id"],))
        if not m:
            abort(404)
        voltar = redirect(url_for("ri_ficha", matricula_id=a["matricula_id"]))
        rotulo = f"{a['tipo']}-{a['numero']:02d}"

        # COMPLETAR MULTI-SELO PARCIAL — Beatriz 24/09/2026 (AV-01/4001):
        # lavrou 16.22.8.1 ok + 16.5 x2 falhou («fora da faixa»). Bloquear
        # sempre que selo_texto existe impedia selar o que faltava pelo fluxo
        # oficial. Se a fila pedida ja esta toda no razao, ai sim recusa.
        codigos_pedido_guard = _codigos_de_selo_do_form(request.form)
        if str(a["selo_texto"] or "").strip():
            faltam_guard = _fila_de_selos_faltando(int(ato_id), codigos_pedido_guard)
            with db.connect() as con:
                n_no_razao = banco(con).valor(
                    "SELECT COUNT(*) AS n FROM sd_selos WHERE tabela='ri_atos' "
                    "AND ato_id=%s AND cancelado_em IS NULL",
                    (int(ato_id),))
            # Selo so na coluna, sem linha no razao: caminho antigo/ manual —
            # recusa re-selar. Com linhas no razao e fila faltando, completa
            # multi-selo parcial (AV-01/4001, Beatriz 24/09/2026).
            if not faltam_guard or n_no_razao == 0:
                flash(f"O ato {rotulo} já tem selo: {a['selo_texto']}. Dois selos "
                      f"para o mesmo ato é o dinheiro da serventia saindo duas "
                      f"vezes.", "warning")
                return voltar
        if a["cancelado"]:
            flash(f"O ato {rotulo} está cancelado — não se sela ato desfeito.",
                  "danger")
            return voltar
        # HOTFIX-2026-10-09-08: ato do acervo / com selo no razao ou no teor —
        # so ADMIN/MANAGER, e so com «Selar mesmo assim» confirmado.
        if not str(a["selo_texto"] or "").strip():
            with db.connect() as con:
                _nr = banco(con).valor(
                    "SELECT COUNT(*) AS n FROM sd_selos WHERE tabela='ri_atos' "
                    "AND ato_id=%s AND cancelado_em IS NULL", (int(ato_id),))
            _js = motivo_ja_selado(a, _nr)
            if _js:
                _uid = session.get("user_id")
                _u = db.get_user(int(_uid)) if _uid else None
                _papel = ((_u["role"] if _u else "") or "").upper()
                if _papel not in ("ADMIN", "MANAGER") or request.form.get("confirmar_ressele") != "1":
                    flash(f"O ato {rotulo} já consta como selado ({_js[1]}). Selar de "
                          f"novo é selo em duplicidade. Só administrador ou gerente, "
                          f"por «Selar mesmo assim» com a confirmação marcada.", "warning")
                    return voltar
                audit("RI_ATO_RESSELE_CONFIRMADO", "RI_ATO", ato_id,
                      {"matricula": m["numero"], "ato": rotulo, "motivo": _js[0]})

        natureza = (request.form.get("natureza_titulo") or "").strip()
        codigos_tj = _codigos_de_selo_do_form(request.form)
        selo_texto_antes = str(a["selo_texto"] or "").strip()
        if selo_texto_antes and codigos_tj:
            codigos_tj = _fila_de_selos_faltando(int(ato_id), codigos_tj)
        codigo_tj = codigos_tj[0] if codigos_tj else None
        base_calculo = centavos(request.form.get("base_calculo"))
        isento, motivo_isencao = ler_isencao_do_form(request.form)
        motivo_isencao = motivo_isencao or ""
        selo_a_mao = (request.form.get("selo_texto") or "").strip()
        emolumentos = (request.form.get("emolumentos") or "").strip()

        # A RECUSA E AQUI, COM O CLIENTE NA FRENTE — a mesma razao da rota de
        # lavrar: o envelope tambem recusaria, mas la a resposta vem da rede e
        # o motivo chega mastigado.
        if isento and not motivo_isencao:
            flash("Ato gratuito precisa do motivo escrito — é ele que sai "
                  "dentro do selo e que a correição lê.", "danger")
            return voltar
        if not selo_a_mao and not natureza:
            flash("Para selar, informe a natureza do título: o selo a exige e "
                  "este ato não a tem gravada.", "danger")
            return voltar
        if not selo_a_mao and not codigos_tj:
            flash("Para selar, escolha o item da tabela de custas — ele não "
                  "sai do tipo do ato, e por isso a tela pergunta. Pode "
                  "informar vários itens (ex.: 16.22.8.1 + 16.5 × 2).", "danger")
            return voltar

        # O QUE FOI INFORMADO FICA NO ATO, e antes de falar com a rede: se o
        # aparelho nao responder, a qualificacao digitada nao se perde e a
        # proxima tentativa ja abre preenchida.
        with db.transaction() as con:
            banco(con).escrever(
                """UPDATE ri_atos SET natureza_titulo=COALESCE(%s, natureza_titulo),
                       codigo_tj=COALESCE(%s, codigo_tj),
                       base_calculo_centavos=COALESCE(%s, base_calculo_centavos),
                       isento=%s, motivo_isencao=%s
                     WHERE id=%s""",
                (natureza or None, codigo_tj, base_calculo or None,
                 1 if isento else 0, motivo_isencao or None, ato_id))

        if selo_a_mao:
            # O SELO DIGITADO A MAO PASSA PELO RAZAO, e nao so pela coluna do
            # ato. `registrar_selo_obtido_a_mao` le o codigo, confere o CNS
            # contra o da serventia e recusa selo repetido dizendo em que ato
            # ele ja esta — as tres coisas que a coluna sozinha nao faz.
            #
            #   DECLARADO, E NAO CONSERTADO POR CIMA: a rota que LAVRA ainda
            #   grava `selo_texto` direto, sem razao. Sao duas versoes da mesma
            #   regra, e a de la e da lavratura diaria do balcao — unificar as
            #   duas e mudanca para ser medida e testada a parte, nao efeito
            #   colateral desta tela.
            import selo_no_papel as SNP
            codigo = str((SNP.ler(selo_a_mao) or {}).get("codigo") or "").strip()
            try:
                if codigo:
                    with db.transaction() as con:
                        AS.registrar_selo_obtido_a_mao(
                            con, codigo, tabela="ri_atos", ato_id=ato_id,
                            atribuicao="IMOVEL",
                            agora=datetime.now().isoformat(timespec="seconds"),
                            cns=db.get_setting("ri_cns", ""),
                            usuario=app.extensions["usuario_nome"](),
                            texto=selo_a_mao)
            except AS.AtoError as erro:
                flash(f"O selo digitado não entrou: {erro}", "danger")
                return voltar
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE ri_atos SET selo_texto=%s,
                           emolumentos=COALESCE(%s, emolumentos) WHERE id=%s""",
                    (selo_a_mao, emolumentos or None, ato_id))
            audit("RI_ATO_SELADO_A_MAO", "RI_ATO", ato_id,
                  {"matricula": m["numero"], "ato": rotulo,
                   "selo": codigo or selo_a_mao[:40],
                   "no_razao": bool(codigo)})
            flash(f"Selo gravado no ato {rotulo}."
                  + ("" if codigo else " O código não foi reconhecido no texto "
                     "colado, então ele não entrou no razão dos selos — "
                     "confira a etiqueta."), "success")
            return voltar

        partes = [(r["nome"], r["documento_numero"]) for r in q(
            "SELECT nome, documento_numero FROM ri_partes WHERE ato_id=%s ORDER BY id",
            (ato_id,))]
        saiu = _selar_itens_do_ato_do_ri(
            ato_id=ato_id, tipo=a["tipo"], numero=a["numero"], matricula=m,
            base_calculo=base_calculo, codigos_tj=codigos_tj,
            descricao_natureza=natureza, protocolo=a["protocolo"],
            partes=partes, selo_a_mao=None,
            isento=isento, motivo_isencao=motivo_isencao or None)

        # Completar multi-selo nao pode apagar o primeiro carimbo gravado
        # em selo_texto (vincular_ao_ato sobrescreve). Igual ao arquivamento.
        if selo_texto_antes:
            with db.transaction() as con:
                banco(con).escrever(
                    "UPDATE ri_atos SET selo_texto=%s WHERE id=%s",
                    (selo_texto_antes, int(ato_id)))

        # ELA DEVOLVE DICIONARIO DESDE 16/09/2026, E ESTA ROTA LIA TEXTO —
        # defeito meu, achado pelo teste que existe exatamente para isto
        # (`test_o_que_foi_informado_fica_gravado_mesmo_sem_o_selo_sair`).
        #
        #   No mesmo dia `_selar_o_ato_do_ri` passou a dizer DUAS coisas — a
        #   frase e se o aparelho chegou a ser consultado —, porque suspender
        #   ato por causa da palavra da mensagem estava suspendendo o que
        #   relavrar nao resolve. Eu acertei a rota que LAVRA e nao olhei a
        #   que SELA DEPOIS: aqui `recado.strip()` estouraria em
        #   AttributeError na cara de quem acabou de pedir o selo de um ato
        #   que ficou sem ele — e o ato ja existe, logo o erro apareceria
        #   DEPOIS de a chamada ter saido para o aparelho.
        #
        #   `suspende` nao se le aqui de proposito: esta rota nunca suspende
        #   nada — o ato ja esta no livro, e o que falta e so o selo. (O campo
        #   se chamava `da_rede` ate 16/09/2026; ver `_selar_o_ato_do_ri`.)
        frase = saiu["recado"]
        audit("RI_ATO_SELADO", "RI_ATO", ato_id,
              {"matricula": m["numero"], "ato": rotulo,
               "codigo_tj": codigo_tj, "selo": frase.strip() or None})
        if "SEM SELO" in frase:
            # A frase de `_selar_o_ato_do_ri` fala de lavratura, porque foi
            # escrita para ela. Aqui o ato ja existe — o que nao saiu foi o
            # selo, e a tela nao pode dizer que o ato nao foi lavrado.
            flash("O selo NÃO saiu: " + frase.split("SEM SELO:", 1)[-1].strip()
                  + f" O ato {rotulo} continua lavrado e aparece na lista de "
                  f"atos sem selo.", "warning")
            if request.form.get("gerar_arquivamento") == "1":  # HOTFIX-2026-10-09-07
                flash("O arquivamento não foi pedido, porque o selo do ato não "
                      "saiu.", "warning")
        else:
            flash(f"Ato {rotulo} selado.{frase}", "success")
            # HOTFIX-2026-10-09-07 — arquivamento (16.39) pedido no próprio
            # «Selar este ato», depois do selo do ato e com a gratuidade dele.
            # Mesmo caminho de `ri_selar_arquivamento`; falha não desfaz nada.
            if request.form.get("gerar_arquivamento") == "1":
                try:
                    _folhas = int((request.form.get("folhas_arquivamento") or "0").strip() or 0)
                except ValueError:
                    _folhas = 0
                _a2 = q1("SELECT * FROM ri_atos WHERE id=%s", (ato_id,))
                if _folhas < 1:
                    flash("Arquivamento não pedido: informe as folhas (>= 1). "
                          "Use «Selar arquivamento» no ato.", "warning")
                elif str(_a2["selo_arquivamento"] or "").strip():
                    flash(f"O ato {rotulo} já tem selo de arquivamento: "
                          f"{_a2['selo_arquivamento']}.", "warning")
                else:
                    arq = _selar_arquivamento_do_ri(
                        ato_id=ato_id, folhas=_folhas,
                        selo_do_ato=_a2["selo_texto"], partes=partes,
                        isento=bool(_a2["isento"]),
                        motivo_isencao=_a2["motivo_isencao"])
                    if arq.get("ok"):
                        audit("RI_ATO_ARQUIVAMENTO_SELADO", "RI_ATO", ato_id,
                              {"matricula": m["numero"], "ato": rotulo,
                               "selo": arq["numero"], "folhas": arq["folhas"],
                               "junto_do_selar": True})
                        flash(f"Arquivamento do ato {rotulo} selado.{arq['recado']}",
                              "success")
                    else:
                        audit("RI_ATO_ARQUIVAMENTO_PENDENTE", "RI_ATO", ato_id,
                              {"matricula": m["numero"], "ato": rotulo,
                               "folhas": _folhas, "motivo": arq.get("motivo"),
                               "junto_do_selar": True})
                        flash(f"Arquivamento NAO saiu no ato {rotulo}: "
                              f"{arq.get('motivo')}. O selo do ato permanece; use "
                              f"«Selar arquivamento» quando o aparelho responder.",
                              "warning")
        return voltar


    @app.route("/registro-imoveis/ato/<int:ato_id>/selar-arquivamento",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_selar_arquivamento(ato_id):
        """Sela o arquivamento (16.39) de um ato RI ja lavrado.

        Para quando a lavratura gerou o ato/selo e o arquivamento ficou
        pendente, ou quando o escrevente nao marcou na hora e quer gerar
        depois. Nao mexe no selo do ato; nao suspende nada.
        """
        import selo_robo as SR
        if SR.exige_humano_para_selar():
            abort(403)
        a = q1("SELECT * FROM ri_atos WHERE id=%s", (ato_id,))
        if not a:
            abort(404)
        m = q1("SELECT * FROM ri_matriculas WHERE id=%s", (a["matricula_id"],))
        if not m:
            abort(404)
        voltar = redirect(url_for("ri_ficha", matricula_id=a["matricula_id"]))
        rotulo = f"{a['tipo']}-{a['numero']:02d}"
        if a["cancelado"]:
            flash(f"O ato {rotulo} esta cancelado - nao se sela arquivamento "
                  f"de ato desfeito.", "danger")
            return voltar
        if str(a["selo_arquivamento"] or "").strip():
            flash(f"O ato {rotulo} ja tem selo de arquivamento: "
                  f"{a['selo_arquivamento']}.", "warning")
            return voltar
        bruto = (request.form.get("folhas_arquivamento") or "").strip()
        try:
            folhas = int(bruto or 0)
        except ValueError:
            folhas = 0
        if folhas < 1:
            flash("Informe a quantidade de folhas (>= 1) para o arquivamento.",
                  "danger")
            return voltar
        partes = [(r["nome"], r["documento_numero"]) for r in q(
            "SELECT nome, documento_numero FROM ri_partes WHERE ato_id=%s ORDER BY id",
            (ato_id,))]
        recusa = _atender_o_protocolo_escolhido(request.form)
        if recusa:
            flash(recusa, "danger")
            return voltar
        arq = _selar_arquivamento_do_ri(
            ato_id=ato_id, folhas=folhas,
            selo_do_ato=a["selo_texto"], partes=partes,
            isento=bool(a["isento"]),
            motivo_isencao=a["motivo_isencao"])
        if arq.get("ok"):
            audit("RI_ATO_ARQUIVAMENTO_SELADO", "RI_ATO", ato_id,
                  {"matricula": m["numero"], "ato": rotulo,
                   "selo": arq["numero"], "folhas": arq["folhas"],
                   "depois": True})
            flash(f"Arquivamento do ato {rotulo} selado.{arq['recado']}",
                  "success")
        else:
            audit("RI_ATO_ARQUIVAMENTO_PENDENTE", "RI_ATO", ato_id,
                  {"matricula": m["numero"], "ato": rotulo,
                   "folhas": folhas, "motivo": arq.get("motivo"),
                   "depois": True})
            flash(f"Arquivamento NAO saiu no ato {rotulo}: {arq.get('motivo')}. "
                  f"O selo do ato permanece; tente de novo quando o aparelho "
                  f"responder.", "warning")
        return voltar

    # ------------------------------------------ modelos de atos do RI

    @app.route("/registro-imoveis/modelos-atos")
    @login_required
    def ri_modelos_atos():
        """Catálogo dos modelos de ato, com requisitos e fundamentação."""
        tipo = (request.args.get("tipo") or "").strip().upper()
        busca = normalizar_busca(request.args.get("busca") or "")
        lista = MODELOS_ATOS
        if tipo in ("R", "AV"):
            lista = [m for m in lista if m["tipo"] == tipo]
        if busca:
            lista = [m for m in lista
                     if busca in normalizar_busca(
                         m["nome"] + " " + m["natureza"] + " " + m["fundamentacao"])]
        # Vindo da ficha, o catálogo já sabe em qual matrícula o ato será lavrado.
        mid = request.args.get("matricula")
        alvo = q1("SELECT id, numero FROM ri_matriculas WHERE id=%s", (mid,)) if mid else None
        return render_template("ri_modelos_atos.html", modelos=lista, tipo=tipo,
                               busca=request.args.get("busca") or "",
                               total=len(MODELOS_ATOS),
                               matricula_id=(alvo["id"] if alvo else None),
                               matricula_numero=(alvo["numero"] if alvo else None))

    def _contexto_modelo(m, modelo, prenotacao=None):
        """Parte fixa do ato: o que o sistema já sabe da matrícula.

        `prenotacao` é a que a tela do modelo escolheu (LD03): com ela, a frase
        do protocolo sai do título que se está lavrando, e não só da
        prenotação que já está amarrada à matrícula — a que abriu a ficha só
        se amarra no primeiro ato, e a frase saía «[INFORMAR O PROTOCOLO]».
        """
        proximo = int((q1("SELECT MAX(numero) n FROM ri_atos WHERE matricula_id=%s",
                          (m["id"],)) or {"n": 0})["n"] or 0) + 1
        partes = q("""SELECT nome, documento_tipo, documento_numero, qualificacao
                      FROM ri_partes WHERE matricula_id=%s AND proprietario_ativo=1
                      ORDER BY nome, id""", (m["id"],))
        protocolo = prenotacao or q1("""SELECT numero, data_prenotacao FROM ri_protocolos
                          WHERE matricula_id=%s AND situacao='ABERTO'
                          ORDER BY numero DESC, id DESC LIMIT 1""", (m["id"],))

        def descreve(p):
            t = [p["nome"]]
            if p["qualificacao"]:
                t.append(p["qualificacao"])
            if p["documento_numero"]:
                t.append(f"{p['documento_tipo'] or 'documento'} {p['documento_numero']}")
            return ", ".join(t)

        prop = "; ".join(descreve(p) for p in partes) or "[QUALIFICAR AS PARTES]"
        # AS FRASES DA PARTE FIXA MORAM NA BASE — LF06B (`RI_MINUTA_PROTOCOLO`,
        # o mesmo da CNIB, e `RI_MINUTA_IMOVEL`/`_AREA`). Quando cada uma entra,
        # e o [MARCADOR] do que o sistema nao sabe, continuam aqui.
        import ri_frases
        with db.connect() as _c_frases:
            protocolo_frase = (
                ri_frases.frase("RI_MINUTA_PROTOCOLO", _c_frases,
                                numero=protocolo["numero"],
                                data=fmt_date(protocolo["data_prenotacao"]))
                if protocolo else "[INFORMAR O PROTOCOLO].")
            area_frase = ri_frases.frase(
                "RI_MINUTA_IMOVEL", _c_frases,
                imovel=m["logradouro"] or "[DESCREVER O IMÓVEL]",
                area=(ri_frases.frase("RI_MINUTA_IMOVEL_AREA", _c_frases,
                                      valor=m["area_valor"],
                                      unidade=m["area_unidade"] or "")
                      if m["area_valor"] else ""))
        return proximo, {
            "rotulo": rotulo_ato(modelo["tipo"], proximo, m["numero"]),
            "matricula": m["numero"],
            "transmitentes": prop,
            "adquirentes": "[QUALIFICAR O(S) ADQUIRENTE(S) — " + QUALIF_RESUMO + "]",
            "proprietarios_frase": prop,
            "protocolo_frase": protocolo_frase,
            "area_frase": area_frase,
        }

    def _titulo_da_tela_do_modelo(m, form) -> dict:
        """A prenotação, o protocolo geral e os itens da tela do modelo. Só LÊ.

        É O QUE A TELA NÃO PERGUNTAVA — LD03, 21/10/2026 (o defeito t do LT03):
        «Enviar para a lavratura» mandava só o texto, e a lavratura recusa ato
        sem item de custa desde 15/09/2026.

          - A PRENOTAÇÃO: a escolhida na tela; na primeira vez, a aberta já
            amarrada à matrícula e, sem ela, a do protocolo geral que quem está
            logado atende («Estou atendendo este protocolo»). A que abriu a
            ficha só se amarra a ela no primeiro ato, e por isso a segunda.
            «— sem prenotação —» escolhido fica sem: escolher é da tela.
          - O PROTOCOLO GERAL: `_caixa_do_titulo`, a régua do cancelamento.
          - OS ITENS: os que têm saldo, marcados por padrão como na ficha; o
            que a tela desmarcou fica desmarcado (`itens_da_tela` diz que a
            lista veio no formulário).
        """
        colunas = "id, numero, data_prenotacao, natureza_titulo, apresentante"
        with db.connect() as con:
            bd = banco(con)
            abertas = [dict(p) for p in CXPROT.prenotacoes_abertas(con, limite=80)]
            escolhida = numero_digitado(form.get("prenotacao_id"))
            prenotacao = None
            if escolhida is not None:
                prenotacao = bd.um(f"""SELECT {colunas} FROM ri_protocolos
                                        WHERE id=%s AND situacao='ABERTO'""",
                                   (escolhida,))
            elif "prenotacao_id" not in form:
                prenotacao = bd.um(f"""SELECT {colunas} FROM ri_protocolos
                                        WHERE matricula_id=%s AND situacao='ABERTO'
                                        ORDER BY numero DESC, id DESC LIMIT 1""",
                                   (m["id"],))
                atendendo = (None if prenotacao else CXPROT.em_atendimento(
                    bd, app.extensions["usuario_nome"]()))
                if atendendo and atendendo.get("ri_protocolo_id"):
                    prenotacao = bd.um(f"""SELECT {colunas} FROM ri_protocolos
                                            WHERE id=%s AND situacao='ABERTO'""",
                                       (int(atendendo["ri_protocolo_id"]),))
            caixa = _caixa_do_titulo(con, prenotacao["id"] if prenotacao else None)
            itens = CXPROT.itens_disponiveis(con, caixa["id"]) if caixa else []
        if prenotacao and all(p["id"] != prenotacao["id"] for p in abertas):
            abertas.insert(0, dict(prenotacao))
        if form.get("itens_da_tela") == "1":
            # LD13: o «²» passava pelo `isdigit()` e caía no `int()`.
            marcados = {n for n in map(numero_digitado, form.getlist("protocolo_item_id"))
                        if n is not None}
        else:
            marcados = {int(i["id"]) for i in itens}
        return {"abertas": abertas, "prenotacao": prenotacao, "caixa": caixa,
                "itens": itens, "marcados": marcados}

    def _guardar_a_minuta_do_modelo(con, m, modelo, texto: str, titulo: dict,
                                    partes: list[dict], minuta_id,
                                    envio: str) -> int:
        """O texto da tela do modelo vira minuta antes de ir à lavratura. ESCREVE.

        POR QUE MINUTA — LD03, 21/10/2026: a recusa da lavratura voltava para
        a ficha crua, e o texto preenchido campo a campo se perdia (o recado
        ainda dizia «nada se perdeu»). Quem veio de minuta volta para a MESMA
        minuta, com o texto e as partes (`ri_lavrar_ato`, `minuta_pedida`), e
        a minuta que não se lavrou fica na fila da ficha — «Minutas a revisar
        e lavrar». E o mesmo «Enviar» duas vezes não cria duas: a tela
        devolve o número, e ela se atualiza.

        O DUPLO «ENVIAR» TAMBÉM NÃO — LD10, 21/10/2026 (ressalva da revisão do
        LD03). O número (`minuta_guardada`) só chega no envio que vem DEPOIS de
        a tela voltar; o clique duplo manda os dois sem ele, e cada um criava a
        sua minuta. A tela leva agora a marca do envio (`envio`, sorteada
        quando ela abre), e a marca entra na `origem_chave`: sob a trava da
        ficha, o segundo envio da MESMA tela acha a minuta do primeiro e a
        atualiza. A marca é da tela, e não do modelo: a mesma ficha pode ter
        duas minutas do mesmo modelo (dois cancelamentos de ônus), e o envio
        de uma não pode escrever por cima da outra.

        E A MINUTA SE PRENDE ANTES DE SE CONFERIR A SITUAÇÃO (`FOR UPDATE`):
        lida solta, a minuta que outra aba está lavrando ainda parece «a
        revisar», e o texto desta tela cairia por cima do que foi ao livro —
        a procedência do ato passaria a dizer outra coisa.

        UMA A REVISAR POR MARCA — LD13, 21/10/2026 (ressalva da revisão do
        LD10). A marca pode estar em mais de uma minuta da ficha: a lavrada ou
        descartada e a que a mesma tela mandou depois. A busca pela marca
        procura a que está A REVISAR, e não a mais nova: com uma descartada
        mais nova (a corrida da suspensão do selo devolve a primeira à fila
        depois de a outra aba ter criado a sua), a mais nova criava uma
        segunda a revisar, e a fila mostrava duas com o mesmo texto. Sem
        índice único, de propósito: a suspensão (`ri_minuta.voltar_do_ato`)
        devolve a minuta lavrada à fila, e um índice a faria falhar — o ato
        ficaria no livro sem selo, que é pior que a minuta repetida. Quem
        garante aqui é a trava da ficha, que põe um envio atrás do outro.
        """
        protocolo = str(titulo["prenotacao"]["numero"]) if titulo["prenotacao"] else ""
        quem = _quem_mexeu_na_minuta()
        origem_chave = f"modelo:{modelo['codigo']}:{envio}"
        bd = banco(con)
        bd.travar(f"ri_minutas.modelo:{int(m['id'])}")
        bd._escrita()
        atual = None
        guardada = numero_digitado(minuta_id)
        if guardada is not None:
            atual = bd.um("SELECT * FROM ri_minutas WHERE id=%s FOR UPDATE",
                          (guardada,))
        if not atual or atual["matricula_id"] != m["id"] \
                or atual["situacao"] != RIMIN.A_REVISAR:
            atual = bd.um("""SELECT * FROM ri_minutas
                              WHERE matricula_id=%s AND origem_chave=%s AND situacao=%s
                              ORDER BY id DESC LIMIT 1 FOR UPDATE""",
                          (m["id"], origem_chave, RIMIN.A_REVISAR))
        if atual and atual["situacao"] == RIMIN.A_REVISAR:
            RIMIN.atualizar(bd, int(atual["id"]), teor=texto, agora=db.now(),
                            tipo=modelo["tipo"],
                            natureza_titulo=modelo["natureza"],
                            protocolo=protocolo, partes=partes, usuario=quem)
            return int(atual["id"])
        nova = RIMIN.criar(
            bd, matricula_id=m["id"], tipo=modelo["tipo"], teor=texto,
            agora=db.now(), natureza_titulo=modelo["natureza"],
            protocolo=protocolo or None, modelo_codigo=modelo["codigo"],
            origem=RIMIN.MANUAL, origem_chave=origem_chave,
            observacao="Preenchida na tela «Preencher o modelo».", usuario=quem)
        RIMIN.guardar_partes(bd, nova, partes)
        return nova

    @app.route("/registro-imoveis/<int:matricula_id>/preencher/<codigo>",
               methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_preencher_modelo(matricula_id, codigo):
        """Preenchimento do modelo em duas formas, sobre os mesmos dados.

        Abas — um campo por marcador, agrupado por assunto.
        Documento — o texto do ato com os marcadores editáveis no lugar.

        As duas escrevem nos mesmos valores; trocar de aba não perde nada.

        E «ENVIAR PARA A LAVRATURA» LEVA O ATO INTEIRO — LD03, 21/10/2026
        («corrija tudo»; o LT03 achou). Ia para `/atos` só tipo, natureza,
        modelo, data e teor: sem a prenotação, sem o item da tabela e sem as
        partes, e a lavratura recusava pelo item (CN-MA art. 130, § 2º). Agora
        a tela pergunta o título (`_titulo_da_tela_do_modelo`), as partes, o
        valor declarado e a qualificação do adquirente — o que a parte fixa
        não sabe —, e o texto vira minuta antes de ir. Quem lavra continua
        sendo a rota de sempre: uma segunda porta para lavrar seria uma
        segunda versão da regra que numera, sela e cobra.

        O CAMPO DO MODELO EM BRANCO NÃO VAI, nem com «Lavrar mesmo assim»: a
        lavratura o recusa desde o mesmo lote (`por_preencher_do_modelo`), e a
        marca que confirmava ficaria prometendo o que não acontece. Ela fica
        para o colchete que o escrevente escreveu de propósito.
        """
        modelo = modelo_por_codigo(codigo)
        m = q1("SELECT * FROM ri_matriculas WHERE id=%s", (matricula_id,))
        if not modelo or not m:
            abort(404)
        if m["encerrada"]:
            flash("Matrícula encerrada não recebe novo ato.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        campos = campos_do_modelo(modelo)
        valores = {c["chave"]: (request.form.get("c_" + c["chave"]) or "").strip()
                   for c in campos}
        titulo = _titulo_da_tela_do_modelo(m, request.form)
        numero, fixo = _contexto_modelo(m, modelo, prenotacao=titulo["prenotacao"])
        # O ADQUIRENTE SÓ O TÍTULO DIZ — a parte fixa escreve o marcador
        # dele, e até aqui a tela não tinha onde preenchê-lo: o registro saía
        # da tela com «[QUALIFICAR O(S) ADQUIRENTE(S) …]» no texto.
        adquirentes = (request.form.get("adquirentes") or "").strip()
        if adquirentes:
            fixo["adquirentes"] = adquirentes

        # Marcadores trocados primeiro; depois o Jinja resolve a parte fixa.
        corpo = preencher_modelo(modelo, valores)
        try:
            html = render_modelo(corpo, fixo)
        except Exception as erro:
            flash(f"O modelo tem um erro: {SEGWEB.erro_do_modelo(erro, 'ri_modelo')}", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        texto = re.sub(r"<[^>]+>", "", html)
        texto = re.sub(r"[ \t]+", " ", texto).strip()
        # Campo em branco e escolha nao feita. Clausula opcional nao entra:
        # nao marcar tambem e uma decisao.
        pendentes = pendencias_modelo(texto)
        # O que a lavratura recusa: os campos DO MODELO (e da parte fixa).
        bloqueiam = por_preencher_do_modelo(texto, modelo["codigo"])
        partes = _partes_da_tela(request.form)
        tela = {
            "m": m, "modelo": modelo, "abas": abas_do_modelo(modelo),
            "valores": valores, "texto": texto, "pendentes": pendentes,
            "bloqueiam": bloqueiam, "numero": numero,
            "hoje": date.today().isoformat(), "titulo": titulo, "partes": partes,
            "adquirentes": adquirentes,
            "pede_adquirentes": "adquirentes" in modelo["corpo"],
            "base_calculo": (request.form.get("base_calculo") or "").strip(),
            # O NÚMERO DA MINUTA QUE ESTA TELA GUARDOU, para o segundo «Enviar»
            # atualizá-la. Tem nome próprio: `minuta_id` é o campo de quem
            # LAVRA a minuta, e só `ri_lavrar_ato` o lê
            # (`test_so_a_rota_de_lavrar_aceita_minuta`).
            "minuta_guardada": (request.form.get("minuta_guardada") or "").strip(),
            # A MARCA DESTA TELA (LD10): sorteada quando ela abre e repetida
            # em cada envio dela — o clique duplo chega antes do número da
            # minuta, e é por ela que o segundo acha o primeiro.
            "envio": _marca_do_envio(request.form.get("envio")),
            "PAPEIS_RI": RC.PAPEIS, "enviar": False,
        }

        if request.method == "POST" and request.form.get("acao") == "lavrar":
            if bloqueiam:
                flash(f"Ainda há {len(bloqueiam)} campo(s) do modelo por "
                      f"preencher — {'; '.join(bloqueiam[:6])}"
                      f"{' …' if len(bloqueiam) > 6 else ''}. O livro não "
                      f"recebe campo do modelo em branco: preencha e envie de "
                      f"novo.", "warning")
            elif pendentes and request.form.get("confirmar_pendencias") != "1":
                flash(f"Ainda há {len(pendentes)} campo(s) por preencher. "
                      f"Confirme se quiser lavrar assim mesmo.", "warning")
            else:
                try:
                    with db.transaction() as con:
                        tela["minuta_guardada"] = str(_guardar_a_minuta_do_modelo(
                            con, m, modelo, texto, titulo, partes,
                            tela["minuta_guardada"], tela["envio"]))
                except RIMIN.MinutaError as erro:
                    flash(f"{erro} Nada foi enviado.", "danger")
                else:
                    tela["enviar"] = True

        return render_template("ri_preencher.html", **tela)

    @app.route("/registro-imoveis/<int:matricula_id>/modelo/<codigo>")
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_aplicar_modelo(matricula_id, codigo):
        """Devolve o teor do modelo já preenchido com o que o sistema sabe.

        O que o sistema NÃO sabe fica entre [colchetes] para preenchimento
        manual. Preencher automaticamente o que não se tem seria inventar
        conteúdo de ato registral.
        """
        modelo = modelo_por_codigo(codigo)
        m = q1("SELECT * FROM ri_matriculas WHERE id=%s", (matricula_id,))
        if not modelo or not m:
            abort(404)

        proximo = int((q1("SELECT MAX(numero) n FROM ri_atos WHERE matricula_id=%s",
                          (matricula_id,)) or {"n": 0})["n"] or 0) + 1
        partes = q("""SELECT nome, documento_tipo, documento_numero, qualificacao
                      FROM ri_partes WHERE matricula_id=%s AND proprietario_ativo=1
                      ORDER BY nome, id""", (matricula_id,))
        protocolo = q1("""SELECT numero, data_prenotacao FROM ri_protocolos
                          WHERE matricula_id=%s AND situacao='ABERTO'
                          ORDER BY numero DESC, id DESC LIMIT 1""", (matricula_id,))

        def descreve(p):
            partes_txt = [p["nome"]]
            if p["qualificacao"]:
                partes_txt.append(p["qualificacao"])
            if p["documento_numero"]:
                partes_txt.append(f"{p['documento_tipo'] or 'documento'} "
                                  f"{p['documento_numero']}")
            return ", ".join(partes_txt)

        proprietarios = "; ".join(descreve(p) for p in partes) or "[QUALIFICAR AS PARTES]"
        # AS MESMAS FRASES DE `_contexto_modelo`, lidas da base (LF06B). O
        # marcador do imovel sem logradouro e outro aqui («[DESCREVER]») — era
        # assim antes, e o teor sugerido nao muda nesta passada.
        import ri_frases
        with db.connect() as _c_frases:
            protocolo_frase = (
                ri_frases.frase("RI_MINUTA_PROTOCOLO", _c_frases,
                                numero=protocolo["numero"],
                                data=fmt_date(protocolo["data_prenotacao"]))
                if protocolo else "[INFORMAR O PROTOCOLO].")
            area_frase = ri_frases.frase(
                "RI_MINUTA_IMOVEL", _c_frases,
                imovel=m["logradouro"] or "[DESCREVER]",
                area=(ri_frases.frase("RI_MINUTA_IMOVEL_AREA", _c_frases,
                                      valor=m["area_valor"],
                                      unidade=m["area_unidade"] or "")
                      if m["area_valor"] else ""))
        contexto = {
            "rotulo": rotulo_ato(modelo["tipo"], proximo, m["numero"]),
            "matricula": m["numero"],
            "transmitentes": proprietarios,
            "adquirentes": "[QUALIFICAR O(S) ADQUIRENTE(S) — " + QUALIF_RESUMO + "]",
            "proprietarios_frase": proprietarios,
            "protocolo_frase": protocolo_frase,
            "area_frase": area_frase,
        }
        try:
            texto = render_modelo(modelo["corpo"], contexto)
        except Exception as erro:
            return Response(f"Erro no modelo: {SEGWEB.erro_do_modelo(erro, 'ri_minuta')}",
                            mimetype="text/plain", status=500)

        # Texto puro para cair na caixa de teor da lavratura.
        limpo = re.sub(r"<[^>]+>", "", texto)
        limpo = re.sub(r"[ \t]+", " ", limpo).strip()
        return Response(json.dumps({
            "codigo": modelo["codigo"], "nome": modelo["nome"], "tipo": modelo["tipo"],
            "natureza": modelo["natureza"], "fundamentacao": modelo["fundamentacao"],
            "requisitos": modelo["requisitos"], "teor": limpo,
        }, ensure_ascii=False), mimetype="application/json")

    # --------------------------------------------- edição cadastral

    # Campos do cadastro do imovel. Note o que NAO esta aqui: numero, livro,
    # teor e qualquer coisa ligada a ato. Corrigir descricao de imovel e
    # manutencao cadastral; mexer em ato lavrado seria outra coisa, e nao se faz.
    CAMPOS_CADASTRAIS = {
        "logradouro": "Logradouro / denominação",
        "numero_predial": "Número",
        "complemento_endereco": "Complemento",
        "bairro": "Bairro",
        "cidade": "Cidade",
        "uf": "UF",
        "cep": "CEP",
        "rural_urbano": "Localização",
        "area_valor": "Área",
        "area_unidade": "Unidade da área",
        "descricao_perimetro": "Descrição do perímetro",
        "confrontacoes": "Confrontações",
        "registro_anterior": "Registro anterior",
        "observacao": "Observação",
        "car": "CAR",
        "nirf": "NIRF",
        "incra": "INCRA",
        "cib": "CIB",
        "sigef": "SIGEF",
        "ccir": "CCIR",
        "cmc": "CMC",
        "inscricao_municipal": "Inscrição municipal",
        "iptu": "IPTU",
        "folha": "Folha",
        "cnm": "CNM",
    }

    _RECADO_ALTERADA_POR_OUTRA_PESSOA = (
        "Esta matrícula foi alterada por outra pessoa depois que você abriu a "
        "tela de retificação. Nada foi gravado — abra a tela de novo, confira "
        "o que mudou e refaça a correção.")

    def _versao_do_cadastro(linha) -> str:
        """A versão do cadastro: o que a tela mostra, e quando mudou por último.

        Vai escondida no formulário (`versao_edicao`) e volta no POST; se a
        ficha mudou no meio, a gravação é recusada em vez de sobrescrever.
        """
        import hashlib
        import json as _json
        chaves = (list(CAMPOS_CADASTRAIS)
                  + ["aberta_nome", "aberta_titulo", "aberta_tratamento",
                     "encerrada", "atualizado_em"])
        valores = [None if linha.get(c) is None else str(linha.get(c))
                   for c in chaves]
        return hashlib.sha256(_json.dumps(valores, ensure_ascii=False)
                              .encode("utf-8")).hexdigest()[:20]

    @app.route("/registro-imoveis/<int:matricula_id>/editar", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_editar_matricula(matricula_id):
        m = q1("SELECT * FROM ri_matriculas WHERE id=%s", (matricula_id,))
        if not m:
            abort(404)
        m = dict(m)
        # A VERSAO DO CADASTRO QUE A TELA MOSTROU — tests/
        # test_ri_retificacao_cadastral.py (28/09/2026). Dois balcões abrindo a
        # mesma ficha: o segundo a gravar levava junto, calado, os campos
        # velhos da tela dele por cima da correção do primeiro.
        versao_atual = _versao_do_cadastro(m)
        if matricula_de_acervo(m["numero"]):
            m["tipo_ficha"] = "ACERVO"

        if request.method == "GET":
            return render_template("ri_editar.html", m=m,
                                   campos=CAMPOS_CADASTRAIS,
                                   versao_edicao=versao_atual,
                                   delegatarios=quem_pode_abrir_matricula())

        if m["encerrada"]:
            flash("Matrícula encerrada não recebe alteração cadastral.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        versao_da_tela = request.form.get("versao_edicao")
        if versao_da_tela is not None and versao_da_tela != versao_atual:
            flash(_RECADO_ALTERADA_POR_OUTRA_PESSOA, "danger")
            return redirect(url_for("ri_editar_matricula",
                                    matricula_id=matricula_id))

        mudancas: dict[str, dict] = {}
        valores: dict[str, str | None] = {}
        for campo in CAMPOS_CADASTRAIS:
            # CAMPO QUE NAO VEIO NAO SE APAGA. Vazio no formulário é o
            # operador esvaziando (e grava None); AUSENTE do POST é quem não
            # mexeu nele — sem esta linha, um POST parcial zerava o resto do
            # cadastro.
            if campo not in request.form:
                continue
            novo = (request.form.get(campo) or "").strip() or None
            antigo = m[campo]
            if (antigo or None) != novo:
                mudancas[campo] = {"de": antigo, "para": novo}
                valores[campo] = novo

        # QUEM ABRIU A MATRICULA — 16/09/2026, pedido do oficial: «precisa
        # constar o usuario que esta abrindo a matricula».
        #
        #   A COLUNA EXISTE DESDE ONTEM E ESTA VAZIA EM TODA A CASA. Medido na
        #   producao: `aberta_nome` em branco em **1.982 de 1.982** fichas.
        #   Ela so se preenche em `ri_nova_matricula`; o acervo e as
        #   importacoes — que sao tudo o que ha hoje — nao a tem, e por isso a
        #   linha de assinatura da ficha sai sem nome nenhum.
        #
        #   E NAO SE DEDUZ. O nome de quem imprime esta a mao (`usuario_nome`)
        #   e seria o preenchimento obvio: poria no papel que ABRIU a ficha
        #   quem apenas mandou imprimir, anos depois. E o delegatario titular
        #   de hoje nao abriu as fichas de 1977. **Papel que afirma a pessoa
        #   errada e pior que papel com a linha em branco** — quem assina
        #   escreve quem e.
        #
        #   OS TRES CAMPOS VIAJAM JUNTOS, e por isso nao entram em
        #   `CAMPOS_CADASTRAIS`: eles sao UM fato — a pessoa —, e o titulo sai
        #   do cadastro dela, que ja o guarda. Deduzir o artigo da ultima
        #   letra da funcao acertaria «Substituta» e erraria «Auxiliar», sem
        #   avisar qual foi qual.
        #
        #   E A LISTA TEM OS ESCREVENTES DESDE 16/09/2026, por ordem dele:
        #   «e preciso que seja possivel escolher um escrevente para constar
        #   como responsavel por abrir a matricula». Quem abre ficha no balcao
        #   todo dia nao e o delegatario. Ver `quem_pode_abrir_matricula`.
        quem_abriu = (request.form.get("aberta_nome") or "").strip() or None
        if m["tipo_ficha"] != "ACERVO" and (m["aberta_nome"] or None) != quem_abriu:
            linha_dele = None
            if quem_abriu:
                linha_dele = next(
                    (x for x in quem_pode_abrir_matricula()
                     if x["nome"] == quem_abriu), None)
                if not linha_dele:
                    flash(f"«{quem_abriu}» não está no cadastro desta "
                          f"serventia — quem abriu a matrícula se escolhe da "
                          f"lista (delegatários e escreventes), e não se "
                          f"digita. Pessoa nova entra em Administrativo → "
                          f"Usuários, com a função dela.",
                          "danger")
                    return redirect(url_for("ri_editar_matricula",
                                            matricula_id=matricula_id))
            mudancas["aberta_nome"] = {"de": m["aberta_nome"],
                                       "para": quem_abriu}
            valores["aberta_nome"] = quem_abriu
            valores["aberta_titulo"] = (linha_dele["titulo"] if linha_dele
                                        else None)
            valores["aberta_tratamento"] = (linha_dele["tratamento"]
                                            if linha_dele else None)

        rural_depois = valores.get("rural_urbano", m.get("rural_urbano"))
        cib_depois = valores.get("cib", m.get("cib"))
        if _exige_cib(rural_depois, tipo_ficha=m.get("tipo_ficha")) and not _cib_dispensado(
                m.get("numero"), db.get_setting("cib_dispensado_matriculas", "")):
            if not _cib_valido(cib_depois):
                flash(_mensagem_cib_obrigatorio(), "danger")
                return redirect(url_for("ri_editar_matricula",
                                        matricula_id=matricula_id))

        if not mudancas:
            flash("Nada foi alterado.", "warning")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        motivo = (request.form.get("motivo") or "").strip()
        if len(motivo) < 10:
            # A mesma régua da reabertura e do fechamento de problema: «erro»
            # não diz a quem conferir depois por que o cadastro mudou.
            flash("Escreva o motivo da retificação cadastral com pelo menos "
                  "10 caracteres — ele fica na auditoria, ao lado do valor "
                  "anterior e do novo.", "danger")
            return redirect(url_for("ri_editar_matricula", matricula_id=matricula_id))

        atribuicoes = ", ".join(f"{c}=%s" for c in valores)
        conflito = False
        with db.transaction() as con:
            # A conferência da versão se refaz DENTRO da transação: entre a
            # leitura lá de cima e o BEGIN IMMEDIATE outro balcão pode ter
            # gravado. Havendo conflito, nada é escrito.
            bd = banco(con)
            bd._escrita()
            agora_linha = bd.um("SELECT * FROM ri_matriculas WHERE id=%s FOR UPDATE",
                                (matricula_id,))
            if (versao_da_tela is not None and agora_linha is not None
                    and _versao_do_cadastro(dict(agora_linha)) != versao_da_tela):
                conflito = True
            else:
                bd.escrever(
                    f"""UPDATE ri_matriculas SET {atribuicoes}, imovel_norm=%s,
                        atualizado_em=%s WHERE id=%s""",
                    list(valores.values())
                    + [normalizar_busca(" ".join(str(
                        valores.get(c, m[c]) or "") for c in
                        ("logradouro", "bairro", "cidade", "descricao_perimetro"))),
                       db.now(), matricula_id],
                )
        if conflito:
            flash(_RECADO_ALTERADA_POR_OUTRA_PESSOA, "danger")
            return redirect(url_for("ri_editar_matricula",
                                    matricula_id=matricula_id))

        # A auditoria guarda de-para campo a campo: sem isso, "alterou o
        # cadastro" nao diz nada a quem for conferir depois.
        audit("RI_MATRICULA_EDITADA", "RI_MATRICULA", matricula_id,
              {"numero": m["numero"], "motivo": motivo, "mudancas": mudancas})
        flash(f"{len(mudancas)} campo(s) alterado(s). A mudança ficou registrada "
              f"na auditoria, com valor anterior e novo.", "success")
        return redirect(url_for("ri_ficha", matricula_id=matricula_id))

    # ------------------------------------- cancelamento e encerramento

    def _caixa_do_titulo(con, prenotacao_id) -> dict | None:
        """O protocolo geral de onde sai o item do ato deste título. Só LÊ.

        DUAS FONTES, NESTA ORDEM, e nenhuma é adivinhação (LD03, 21/10/2026):

          1. o protocolo geral ligado à prenotação (`cx_protocolos.
             ri_protocolo_id`), se não estiver encerrado — e PAGO conta: é o
             estado de quem já pagou e espera o ato. (`RITEOR.
             caixa_ligado_a_prenotacao` olha só ABERTO e A_PAGAR, que é a
             lista do que se ESCOLHE; aqui é o título que se está lavrando.)
          2. o que quem está logado diz estar atendendo («Estou atendendo este
             protocolo», LX16) — o mesmo lugar onde a trava do selo procura o
             pagamento. Mas não o de OUTRO título: se ele está ligado a outra
             prenotação, não é deste ato.
        """
        bd = banco(con)
        prenotacao = (int(prenotacao_id)
                      if str(prenotacao_id or "").strip().isdigit() else None)
        if prenotacao is not None and bd.tem_coluna("cx_protocolos", "ri_protocolo_id"):
            ligado = bd.um(
                """SELECT * FROM cx_protocolos
                    WHERE ri_protocolo_id=%s AND situacao NOT IN (%s, %s)
                    ORDER BY id DESC LIMIT 1""",
                (prenotacao, CXPROT.ENTREGUE, CXPROT.CANCELADO))
            if ligado:
                return ligado
        atendendo = CXPROT.em_atendimento(bd, app.extensions["usuario_nome"]())
        if not atendendo or CXPROT.esta_encerrado(atendendo.get("situacao")):
            return None
        de_outro = atendendo.get("ri_protocolo_id")
        if prenotacao is not None and de_outro and int(de_outro) != prenotacao:
            return None
        return atendendo

    def _item_do_cancelamento(form, protocolo_escrito: str) -> dict:
        """O item de custa da averbação de cancelamento, e de onde ele sai. Só LÊ.

        A AVERBAÇÃO DE CANCELAMENTO É ATO COMO QUALQUER OUTRO, e o selo dela
        pede o item da tabela, como o da lavratura comum (`falta_para_selar`).
        A tela pergunta; quando não se informou, ele sai do título:

          1. os itens marcados (`protocolo_id` + `protocolo_item_id`), como na
             lavratura;
          2. o código digitado (`codigo_tj`) — o selo procura o pagamento no
             protocolo em atendimento (a trava do LX16);
          3. o protocolo geral do título (`_caixa_do_titulo`), e SÓ se ele
             tiver UM item com saldo. Com dois, escolher seria adivinhar qual
             serviço o cliente pagou — a régua de `caixa_protocolo.
             itens_para_o_selo` — e a tela pergunta.

        Devolve `{"codigos", "itens", "recado"}`: `codigos` é a fila do selo
        (um por item), `itens` os ids que o cancelamento gasta (uma unidade
        cada) e `recado` o que falta escolher quando o título não decide.
        """
        # LD13: o «²» e os 5.000 dígitos passavam pelo `isdigit()` e caíam no
        # `int()`; o que não é número fica de fora, como o texto já ficava.
        ids = {n for n in map(numero_digitado, form.getlist("protocolo_item_id"))
               if n is not None}
        protocolo_id = numero_digitado(form.get("protocolo_id"))
        codigo = (form.get("codigo_tj") or "").strip()
        with db.connect() as con:
            if ids and protocolo_id is not None:
                marcados = [i for i in CXPROT.itens_disponiveis(con, protocolo_id)
                            if int(i["id"]) in ids]
                if marcados:
                    return {"codigos": [str(i["codigo_ato"]).strip() for i in marcados],
                            "itens": [int(i["id"]) for i in marcados], "recado": ""}
            if codigo:
                return {"codigos": [codigo], "itens": [], "recado": ""}
            prenotacao = None
            numero = numero_digitado(protocolo_escrito)
            if numero is not None:
                prenotacao = banco(con).um(
                    """SELECT id FROM ri_protocolos WHERE numero=%s
                        ORDER BY id DESC LIMIT 1""", (numero,))
            caixa = _caixa_do_titulo(con, prenotacao["id"] if prenotacao else None)
            disponiveis = CXPROT.itens_disponiveis(con, caixa["id"]) if caixa else []
        if len(disponiveis) == 1:
            unico = disponiveis[0]
            return {"codigos": [str(unico["codigo_ato"]).strip()],
                    "itens": [int(unico["id"])], "recado": ""}
        if disponiveis:
            return {"codigos": [], "itens": [], "recado": (
                f"O protocolo {caixa['numero']} tem {len(disponiveis)} itens com "
                f"saldo ({', '.join(str(i['codigo_ato']) for i in disponiveis)}): "
                f"escolha o desta averbação em «Item da tabela de custas» — "
                f"escolher por você seria adivinhar qual serviço o cliente pagou.")}
        return {"codigos": [], "itens": [], "recado": ""}

    def _desfazer_o_cancelamento(con, *, novo_id: int, alvo_id: int,
                                 itens: list[int]) -> None:
        """Desfaz a averbação de cancelamento cujo selo não saiu. ESCREVE.

        É A SUSPENSÃO DA LAVRATURA COMUM («selo recusado suspende ato», ordem
        do oficial em 16/09/2026; «nenhum ato fica de pé sem selo», relato
        #77), com uma diferença: o cancelamento NÃO volta a ser minuta. O teor
        dele é a frase do motivo sobre o rótulo do ato, e relavrá-lo pela
        minuta lavraria a averbação sem marcar o ato cancelado — o livro diria
        uma coisa e a ficha outra. Ele se desfaz inteiro: o ato volta a valer,
        o lançamento dos indicadores sai, a prenotação se solta (a chave
        estrangeira não deixaria apagar a averbação com ela amarrada) e a
        unidade do protocolo volta.

        AS TRÊS RECUSAS de `ri_minuta.voltar_do_ato`, pela mesma razão: ato
        com selo não se desfaz (selo pago amarrado a ato que some é selo
        órfão), só a cauda da corrente de hash, e dinheiro no caixa sai por
        estorno. Sob a trava da numeração, a mesma do cancelamento: nenhum ato
        entra na ficha no meio.
        """
        bd = banco(con)
        bd.travar("ri_atos.numero")
        bd._escrita()
        av = bd.um("SELECT * FROM ri_atos WHERE id=%s FOR UPDATE", (int(novo_id),))
        if not av:
            raise CancelamentoNaoSeDesfaz(
                "a averbação de cancelamento não existe mais.")
        rotulo_av = f"AV-{int(av['numero']):02d}"
        com_selo = str(av["selo_texto"] or "").strip()
        if not com_selo and bd.tem_tabela("sd_selos"):
            com_selo = int(bd.valor(
                """SELECT COUNT(*) AS n FROM sd_selos WHERE tabela='ri_atos'
                    AND ato_id=%s AND cancelado_em IS NULL""", (int(novo_id),)))
        if com_selo:
            raise CancelamentoNaoSeDesfaz(
                f"a {rotulo_av} já tem selo — selo pago amarrado a ato que deixa "
                f"de existir é selo órfão.")
        if int(bd.valor("""SELECT COUNT(*) AS n FROM ri_atos
                            WHERE matricula_id=%s AND id>%s""",
                        (av["matricula_id"], int(novo_id)))):
            raise CancelamentoNaoSeDesfaz(
                f"a {rotulo_av} não é mais o último ato da ficha — tirá-la do "
                f"meio quebraria a corrente de hash.")
        if bd.tem_tabela("cx_lancamentos") and int(bd.valor(
                """SELECT COUNT(*) AS n FROM cx_lancamentos
                    WHERE origem='ATO' AND origem_chave ILIKE %s""",
                (f"ri_atos:{int(novo_id)}:%",))):
            raise CancelamentoNaoSeDesfaz(
                f"a {rotulo_av} tem lançamento no caixa — dinheiro que entrou "
                f"sai por estorno.")
        bd.escrever("UPDATE ri_protocolos SET ato_id=NULL WHERE ato_id=%s",
                    (int(novo_id),))
        bd.escrever("""UPDATE ri_atos SET cancelado=0, cancelado_por_ato_id=NULL
                        WHERE id=%s AND cancelado_por_ato_id=%s""",
                    (int(alvo_id), int(novo_id)))
        if bd.tem_tabela("ri_indicador_lancamentos"):
            bd.escrever("""DELETE FROM ri_indicador_lancamentos
                            WHERE averbacao_id=%s AND origem='CANCELAMENTO'""",
                        (int(novo_id),))
        for item_id in itens:
            CXPROT.devolver_item(con, int(item_id), quantas=1)
        if bd.tem_tabela("cx_item_do_ato"):
            bd.escrever("""DELETE FROM cx_item_do_ato
                            WHERE tabela='ri_atos' AND ato_id=%s""", (int(novo_id),))
        bd.escrever("DELETE FROM ri_atos WHERE id=%s", (int(novo_id),))

    @app.route("/registro-imoveis/atos/<int:ato_id>/cancelar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_cancelar_ato(ato_id):
        """Cancela um ato lavrando uma AVERBAÇÃO de cancelamento.

        O ato original permanece intacto na ficha, apenas marcado. Em registro
        publico nao se apaga assento: o cancelamento e ele proprio um ato, com
        numero, data e teor - e assim que a historia do imovel continua legivel.

        E ELA NASCE SELADA — LD03, 21/10/2026 («corrija tudo»; o LT03 achou).
        Até aqui a averbação de cancelamento era o único ato do Livro 2 que se
        lavrava sem pedir o selo nem o item da tabela: ficava de pé no livro,
        sem selo, até alguém usar «Selar este ato». Nenhum ato se conclui sem o
        selo (CN-MA art. 130, § 2º), e a lavratura comum já cumpria isso
        (relato #77). Agora é o mesmo caminho dela: o que a tela sabe se recusa
        antes (`falta_para_selar`), o item sai do título (`_item_do_cancelamento`)
        e se gasta na transação do ato, o selo é pedido fora dela, e o selo que
        não sai desfaz o cancelamento inteiro (`_desfazer_o_cancelamento`) — o
        ato volta a valer e o fundamento digitado volta no recado.

        A FICHA DE ACERVO segue a regra da lavratura comum (decisão do oficial,
        16/09/2026): sem item de custa, o cancelamento fica lavrado e o recado
        diz que saiu sem selo.
        """
        alvo = q1("SELECT * FROM ri_atos WHERE id=%s", (ato_id,))
        if not alvo:
            abort(404)
        if alvo["cancelado"]:
            flash("Este ato já está cancelado.", "warning")
            return redirect(url_for("ri_ficha", matricula_id=alvo["matricula_id"]))

        m = q1("SELECT * FROM ri_matriculas WHERE id=%s", (alvo["matricula_id"],))
        motivo = (request.form.get("motivo") or "").strip()
        if not motivo:
            flash("Informe o fundamento do cancelamento.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=alvo["matricula_id"]))

        rotulo = rotulo_ato(alvo["tipo"], alvo["numero"], m["numero"])
        data_ato = (request.form.get("data_ato") or "").strip() or db.now()[:10]
        # O TEXTO MORA NA BASE — LF06B (`RI_CANCELAMENTO_DO_ATO`); o rotulo e
        # o fundamento sao daqui. Vai ao livro e congela no hash do ato.
        import ri_frases
        with db.connect() as _c_frases:
            teor = ri_frases.frase("RI_CANCELAMENTO_DO_ATO", _c_frases,
                                   rotulo=rotulo, motivo=motivo)

        # O QUE A TELA SABE SE RECUSA AQUI, COM O ATO AINDA VALENDO — a régua
        # da lavratura comum (`falta_para_selar`): natureza, item da tabela,
        # gratuidade com o motivo escrito. A natureza que o selo leva é a que
        # a ficha sempre gravou nesta averbação, salvo a tela dizer outra.
        protocolo_escrito = (request.form.get("protocolo") or "").strip()
        natureza = ((request.form.get("natureza_titulo") or "").strip()
                    or "Cancelamento de ato")
        isento, motivo_isencao = ler_isencao_do_form(request.form)
        motivo_isencao = motivo_isencao or ""
        e_acervo = (m["tipo_ficha"] == "ACERVO" or matricula_de_acervo(m["numero"]))
        cobranca = _item_do_cancelamento(request.form, protocolo_escrito)
        codigo_tj = cobranca["codigos"][0] if cobranca["codigos"] else None
        impedimento = cobranca["recado"] or falta_para_selar(
            natureza=natureza, codigo_tj=codigo_tj, isento=isento,
            motivo_isencao=motivo_isencao, selo_a_mao=None, e_acervo=e_acervo)
        if impedimento:
            flash(f"{impedimento} O cancelamento NÃO foi lavrado — {rotulo} "
                  f"continua valendo e nada mudou na ficha.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=m["id"]))
        with db.connect() as _cx:
            emolumentos = RITEOR.frase_emolumentos_curta(
                RITEOR.calcular_itens(_cx, cobranca["codigos"], base_calculo=None))

        with db.transaction() as con:
            bd = banco(con)
            bd.travar("ri_atos.numero")
            # O ALVO SE CONFERE DE NOVO, PRESO — a conferência lá de cima foi
            # lida fora da transação. Dois cliques em «Cancelar o ato por
            # averbação» (ou duas abas) passariam os dois por ela e lavrariam
            # duas averbações para o mesmo ato, com dois selos e duas unidades
            # do protocolo. A trava da numeração põe um atrás do outro; o
            # segundo acha o ato já cancelado e para aqui.
            bd._escrita()
            preso = bd.um("SELECT cancelado FROM ri_atos WHERE id=%s FOR UPDATE",
                          (ato_id,))
            if not preso or preso["cancelado"]:
                flash("Este ato já está cancelado.", "warning")
                # A exceção desfaz a transação, e o Flask devolve o redirect.
                abort(redirect(url_for("ri_ficha", matricula_id=m["id"])))
            ultimo = bd.valor("SELECT MAX(numero) AS n FROM ri_atos WHERE matricula_id=%s",
                              (m["id"],))
            numero = int((ultimo or 0)) + 1
            anterior = bd.um("""SELECT hash_ato FROM ri_atos WHERE matricula_id=%s
                                ORDER BY id DESC LIMIT 1""", (m["id"],))
            hash_anterior = anterior["hash_ato"] if anterior else None
            h = hash_ato(m["numero"], "AV", numero, data_ato, teor, hash_anterior)
            novo_id = bd.escrever(
                """INSERT INTO ri_atos
                   (matricula_id, tipo, numero, data_ato, natureza_titulo, protocolo,
                    teor, teor_formato, cancelado, acervo, origem,
                    codigo_tj, isento, motivo_isencao, emolumentos,
                    lavrado_nome, lavrado_titulo, lavrado_tratamento,
                    hash_ato, hash_anterior, lavrado_em)
                   VALUES (%s, 'AV', %s, %s, %s, %s, %s, 'texto', 0, 0,
                           'MANUAL', %s,%s,%s,%s, %s,%s,%s, %s, %s, %s)
                   RETURNING id""",
                (m["id"], numero, data_ato, natureza, protocolo_escrito or None,
                 teor, codigo_tj, 1 if isento else 0, motivo_isencao or None,
                 emolumentos, *quem_pratica_o_ato(), h, hash_anterior, db.now()),
            )[0]["id"]
            novo_id = int(novo_id)
            # A UNIDADE DO PROTOCOLO SE GASTA AQUI, NA TRANSAÇÃO DO ATO, como
            # na lavratura comum: é o item ligado ao ato que a trava do selo
            # acha primeiro (`ato_selado.cobrir_o_selo`), e ela não gasta outra.
            # A lista foi lida sem prender; se a unidade acabou no meio, nada
            # se lavra — cancelamento sem o item seria selo sem pagamento.
            for item_id in cobranca["itens"]:
                if not CXPROT.consumir_item(con, item_id, ato_id=novo_id,
                                            tabela="ri_atos", agora=db.now()):
                    flash("O item do protocolo acabou enquanto o cancelamento "
                          "era lavrado (outro ato o usou). O cancelamento NÃO "
                          f"foi lavrado — {rotulo} continua valendo.", "danger")
                    abort(redirect(url_for("ri_ficha", matricula_id=m["id"])))
            # A AVERBAÇÃO DE CANCELAMENTO TAMBÉM CONSOME PRENOTAÇÃO, e ela é
            # ato como qualquer outro: entrou por título prenotado, ocupa lugar
            # no livro e tem prioridade.
            #   DEFEITO ACHADO PELO TESTE DE QUEM ASSINA, EM 15/09/2026: aqui
            #   estava `matricula_id=matricula_id`, e nesta rota o parametro se
            #   chama `ato_id` — `matricula_id` NAO existe. Era `NameError`
            #   dentro da transacao, e a transacao voltava atras: **cancelar um
            #   ato no RI dava erro 500 e nao cancelava nada**. O botao esta na
            #   ficha desde a correcao do selo que nao saiu; e o caminho nunca
            #   chegou ao fim. Conferido no `.cgu` anterior: o defeito ja estava
            #   la, nao nasceu desta passada.
            amarrado = amarrar_prenotacao(
                bd, request.form.get("protocolo"),
                matricula_id=m["id"], ato_id=novo_id)
            # O ato original nao e apagado nem reescrito: so recebe a marca e o
            # ponteiro para a averbacao que o cancelou.
            bd.escrever("UPDATE ri_atos SET cancelado=1, cancelado_por_ato_id=%s WHERE id=%s",
                        (novo_id, ato_id))
            # Indicadores (Livros 4 e 5): lancamento proprio de cancelamento,
            # alem da averbacao no Livro 2 (pedido 18/09/2026).
            RILANC.registrar_cancelamento_livro2(
                con, matricula=m, ato_alvo=alvo, averbacao_id=novo_id,
                averbacao_numero=numero, motivo=motivo,
                usuario=_usuario_atual(), agora=db.now(),
                data_lancamento=data_ato)

        # O SELO SAI AGORA, FORA DA TRANSAÇÃO — o mesmo desenho da lavratura
        # comum: a chamada ao selador leva até 20 s, e dentro da transação ela
        # seguraria a trava da numeração da casa inteira esse tempo todo.
        saiu_do_selo = _selar_itens_do_ato_do_ri(
            ato_id=novo_id, tipo="AV", numero=numero, matricula=m,
            base_calculo=None, codigos_tj=cobranca["codigos"],
            descricao_natureza=natureza, protocolo=protocolo_escrito,
            partes=[], selo_a_mao=None, isento=isento,
            motivo_isencao=motivo_isencao or None)
        recado_do_selo = saiu_do_selo["recado"]
        motivo_selo = _motivo_da_falha_do_selo(recado_do_selo)
        if motivo_selo and saiu_do_selo["suspende"]:
            try:
                with db.transaction() as con:
                    _desfazer_o_cancelamento(con, novo_id=novo_id, alvo_id=ato_id,
                                             itens=cobranca["itens"])
            except (CancelamentoNaoSeDesfaz, sqlite3.Error) as erro:
                # DESFAZER FALHOU: a averbação FICA, e a tela diz as duas
                # coisas — sumir com ela aqui seria o pior dos mundos.
                audit("RI_CANCELAMENTO_SEM_SELO_NAO_DESFEITO", "RI_ATO", novo_id,
                      {"matricula": m["numero"], "ato_cancelado": rotulo,
                       "averbacao": f"AV-{numero:02d}", "motivo": motivo_selo,
                       "desfazer_falhou": str(erro)})
                flash(f"O selo não saiu ({motivo_selo}) e o cancelamento NÃO "
                      f"pôde ser desfeito: {erro} A AV-{numero:02d} continua "
                      f"lavrada e aparece na lista de atos sem selo.", "danger")
                return redirect(url_for("ri_ficha", matricula_id=m["id"]))
            audit("RI_CANCELAMENTO_DESFEITO_SEM_SELO", "RI_ATO", ato_id,
                  {"matricula": m["numero"], "ato_cancelado": rotulo,
                   "averbacao": f"AV-{numero:02d}", "hash": h,
                   "motivo_do_selo": motivo_selo, "fundamento": motivo,
                   "itens_devolvidos": cobranca["itens"]})
            flash(f"O selo não saiu: {motivo_selo} O cancelamento NÃO foi "
                  f"lavrado — {rotulo} continua valendo e nada mudou na ficha. "
                  f"O fundamento digitado foi «{motivo}»: corrija o que faltou "
                  f"e cancele de novo.", "warning")
            return redirect(url_for("ri_ficha", matricula_id=m["id"]))

        # AS FOLHAS DO ATO CANCELADO VOLTAM AO ESTOQUE SÓ COM O CANCELAMENTO DE
        # PÉ — devolver antes e desfazer depois deixaria folha em branco no
        # estoque e o ato valendo. `recuperar_do_ato` é idempotente, e a
        # conferência de cada abertura (`recuperar_cancelados_existentes`)
        # acerta o que uma queda aqui deixar para trás.
        with db.transaction() as con:
            folhas_recuperadas = PP.recuperar_do_ato(
                con, tabela="ri_atos", ato_id=ato_id, agora=db.now(),
                usuario=_usuario_atual(), motivo=motivo)

        audit("RI_ATO_CANCELADO", "RI_ATO", ato_id,
              {"matricula": m["numero"], "ato_cancelado": rotulo,
               "averbacao": f"AV-{numero:02d}", "motivo": motivo,
               "selo": recado_do_selo.strip() or None,
               **folhas_recuperadas})
        recado_folha = (
            f" Folha(s) {', '.join(folhas_recuperadas['codigos'])} "
            f"devolvida(s) ao estoque."
            if folhas_recuperadas["codigos"] else "")
        flash(f"{rotulo} cancelado pela averbação AV-{numero:02d}. "
              f"O ato original permanece na ficha, marcado como cancelado."
              f"{recado_folha}{recado_da_prenotacao(amarrado)}{recado_do_selo}",
              "warning" if "SEM SELO" in recado_do_selo else "success")
        return redirect(url_for("ri_ficha", matricula_id=m["id"]))

    def _dados_sv() -> dict:
        return dados_serventia(db.get_settings)

    def _hoje_por_extenso() -> str:
        return data_por_extenso(date.today())

    def _usuario_atual() -> str | None:
        """O login de quem esta operando, para assinar a ata.

        Vem da sessao pelo mesmo caminho que a auditoria usa. Nao se deduz por
        cargo nem por configuracao: quem lanca a ata e quem esta logado.
        """
        from flask import session
        uid = session.get("user_id")
        if not uid:
            return None
        u = db.get_user(int(uid))
        return (u["username"] if u else None)

    # --------------------------------------- correcoes administrativas
    #
    # Tres coisas que nao tinham conserto em tela nenhuma e apareceram no
    # primeiro dia de operacao real, 18/08/2026: numero de matricula repetido,
    # papel de parte trocado e ato lavrado em teste. Nenhuma delas mexe em teor
    # — teor lavrado se corrige por averbacao retificadora, e so.

    @app.route("/registro-imoveis/<int:matricula_id>/renumerar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_renumerar_matricula(matricula_id):
        """Troca o numero da matricula e refaz a cadeia de integridade.

        O hash de cada ato inclui o numero da matricula, entao renumerar
        invalida a cadeia por construcao. Recalcular e o certo — e os dois
        hashes, o velho e o novo, ficam na auditoria, para que a troca seja
        auditavel e nao um apagamento silencioso.
        """
        try:
            with db.transaction() as con:
                saida = RC.renumerar_matricula(
                    con, matricula_id,
                    request.form.get("novo_numero"),
                    motivo=(request.form.get("motivo") or ""),
                    agora=db.now())
        except RC.CorrecaoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        audit("RI_MATRICULA_RENUMERADA", "RI_MATRICULA", matricula_id,
              {"de": saida["de"], "para": saida["para"], "motivo": saida["motivo"],
               "livro": saida["livro"], "serie": saida["serie"], "atos": saida["atos"]})
        flash(f"Matrícula {saida['de']} passou a ser a {saida['para']}. "
              f"A cadeia de integridade dos {len(saida['atos'])} ato(s) foi refeita com o "
              f"número novo, e os dois hashes de cada ato ficaram na auditoria.", "success")
        return redirect(url_for("ri_ficha", matricula_id=matricula_id))

    @app.route("/registro-imoveis/<int:matricula_id>/parte-abertura", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_incluir_parte_abertura(matricula_id):
        """Inclui o dono da ABERTURA (ato_id NULL) antes de selar.

        PEDIDO 23/09/2026 (Beatriz, 4018/4019): a ficha importa ou nasce sem
        ri_partes de abertura; o painel Partes nao deixa acrescentar; e
        ri_selar_abertura recusa sem dono. So entra se a abertura ainda nao
        tem selo.
        """
        m = q1("SELECT * FROM ri_matriculas WHERE id=%s", (matricula_id,))
        if not m:
            abort(404)
        voltar = redirect(url_for("ri_ficha", matricula_id=matricula_id))
        if str(m["selo_abertura_texto"] or "").strip():
            flash(f"A matrícula {m['numero']} já tem selo de abertura "
                  f"({m['selo_abertura_texto']}): o dono da abertura não "
                  f"se troca por este caminho — use Corrigir na linha, com "
                  f"motivo escrito.", "warning")
            return voltar
        nome = (request.form.get("nome") or "").strip()
        if not nome:
            flash("Para cadastrar o proprietário da abertura, informe o nome.",
                  "danger")
            return voltar
        doc = so_digitos(request.form.get("documento") or "")
        tipo = ("CPF" if len(doc) == 11
                else "CNPJ" if len(doc) == 14
                else (request.form.get("documento_tipo") or None))
        papel = (request.form.get("papel") or "proprietario").strip() or "proprietario"
        with db.transaction() as con:
            banco(con).escrever(
                """INSERT INTO ri_partes
                   (matricula_id, ato_id, nome, nome_norm, documento_tipo,
                    documento_numero, documento_valido, papel, qualificacao,
                    proprietario, proprietario_ativo, origem, origem_chave)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (matricula_id, None, nome, normalizar_busca(nome),
                 tipo, doc or None,
                 1 if doc and valida_cpf_cnpj(doc) else (0 if doc else None),
                 papel, (request.form.get("qualificacao") or "").strip() or None,
                 1, 1, "MANUAL", "parte_abertura_antes_selo"),
            )
        audit("RI_PARTE_ABERTURA_INCLUIDA", "RI_MATRICULA", matricula_id,
              {"matricula": m["numero"], "nome": nome, "documento": doc or None})
        flash(f"Proprietário da abertura cadastrado: {nome}. "
              f"Agora dá para selar a abertura em Identificação.", "success")
        return voltar

    @app.route("/registro-imoveis/partes/<int:parte_id>/corrigir", methods=["POST"])

    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_corrigir_parte(parte_id):
        """Corrige nome, documento, qualificacao e papel de uma parte.

        Nao e edicao de ato: e qualificacao. O papel decide quem e titular
        atual, e titular errado deixa a certidao de propriedade em branco.
        """
        p = q1("SELECT matricula_id FROM ri_partes WHERE id=%s", (parte_id,))
        if not p:
            abort(404)
        titular = request.form.get("titular")
        try:
            with db.transaction() as con:
                saida = RC.corrigir_parte(
                    con, parte_id,
                    motivo=(request.form.get("motivo") or ""),
                    agora=db.now(),
                    nome=request.form.get("nome"),
                    documento=request.form.get("documento"),
                    qualificacao=request.form.get("qualificacao"),
                    papel=request.form.get("papel"),
                    titular=None if titular in (None, "", "papel") else titular == "1")
        except RC.CorrecaoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_ficha", matricula_id=p["matricula_id"]))

        audit("RI_PARTE_CORRIGIDA", "RI_PARTE", parte_id,
              {"matricula_id": saida["matricula_id"], "ato_id": saida["ato_id"],
               "nome": saida["nome"], "motivo": saida["motivo"],
               "mudancas": saida["mudancas"]})
        campos = ", ".join(saida["mudancas"])
        flash(f"{saida['nome']}: {campos} corrigido(s). O valor anterior ficou na "
              f"auditoria. O teor do ato não foi tocado.", "success")
        return redirect(url_for("ri_ficha", matricula_id=saida["matricula_id"]))

    # ------------------------------------------------------------ expurgo

    @app.route("/registro-imoveis/atos/<int:ato_id>/expurgar", methods=["GET", "POST"])
    @roles_required("ADMIN")
    def ri_expurgar_ato(ato_id):
        """Remove ato lavrado em teste de sistema, com ata de ocorrencia.

        Nao e o cancelamento: ver o cabecalho de ri_expurgo.py. So ADMIN, e so
        depois de a tela mostrar exatamente o que vai sair.
        """
        with db.connect() as con:
            try:
                dados = EXP.levantar(con, ato_id)
            except EXP.ExpurgoError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("ri_matriculas"))

        if request.method == "GET":
            return render_template("ri_expurgo.html", **dados)

        confirmacao = (request.form.get("confirmacao") or "").strip().upper()
        if confirmacao != "EXPURGAR":
            flash('Para confirmar, escreva EXPURGAR no campo de confirmação. '
                  'Ato removido não volta.', "danger")
            return render_template("ri_expurgo.html", **dados)

        try:
            with db.transaction() as con:
                saida = EXP.expurgar(
                    con, ato_id, sv=_dados_sv(), agora=db.now(),
                    data_extenso=_hoje_por_extenso(),
                    motivo=(request.form.get("motivo") or ""),
                    selo_cancelado=request.form.get("selo_cancelado"),
                    usuario=_usuario_atual())
                CNIB.soltar_do_ato(con, ato_id)
        except EXP.ExpurgoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_expurgar_ato", ato_id=ato_id))

        audit("RI_ATO_EXPURGADO", "RI_ATO", ato_id,
              {"matricula": saida["matricula_numero"], "ato": saida["rotulo"],
               "expurgo_id": saida["expurgo_id"],
               "selo_no_sistema": saida["selo_no_sistema"],
               "selo_cancelado": saida["selo_cancelado"]})
        flash(f"{saida['rotulo']} expurgado. A ata de ocorrência nº "
              f"{saida['expurgo_id']} guarda o teor íntegro, o selo e o fundamento. "
              f"Imprima-a e arquive.", "warning")
        return redirect(url_for("ri_expurgos"))

    @app.route("/registro-imoveis/expurgos")
    @roles_required("ADMIN", "MANAGER", "AUDITOR")
    def ri_expurgos():
        """As atas de ocorrencia. E aqui que passa a morar o que saiu da ficha."""
        rows = q("""SELECT e.*, m.id matricula_atual
                    FROM ri_expurgos e
                    LEFT JOIN ri_matriculas m ON m.id = e.matricula_id
                    ORDER BY e.id DESC""")
        return render_template("ri_expurgos.html", rows=rows)

    @app.route("/registro-imoveis/expurgos/<int:expurgo_id>/ata.odt")
    @roles_required("ADMIN", "MANAGER", "AUDITOR")
    def ri_expurgo_ata(expurgo_id):
        e = q1("SELECT * FROM ri_expurgos WHERE id=%s", (expurgo_id,))
        if not e:
            abort(404)
        arquivo = gerar_odt(texto_para_odf(e["ata"]),
                            titulo=f"Ata de ocorrência {expurgo_id}")
        audit("RI_EXPURGO_ATA_IMPRESSA", "RI_EXPURGO", expurgo_id,
              {"ato": e["ato_rotulo"]})
        return Response(arquivo, mimetype="application/vnd.oasis.opendocument.text",
                        headers={"Content-Disposition":
                                 f'attachment; filename="ata-expurgo-{expurgo_id}.odt"'})

    @app.route("/registro-imoveis/<int:matricula_id>/encerrar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_encerrar_matricula(matricula_id):
        """Encerra a matricula, lavrando a averbacao de encerramento.

        Encerramento tambem e ato: fica registrado na ficha com numero e teor,
        e nao apenas como um campo mudado no banco.
        """
        m = q1("SELECT * FROM ri_matriculas WHERE id=%s", (matricula_id,))
        if not m:
            abort(404)
        if m["encerrada"]:
            flash("Esta matrícula já está encerrada.", "warning")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        # VOLTAR A FECHAR O QUE JA FOI FECHADO NAO LAVRA ATO NOVO — 15/09/2026.
        #
        #   Reabrir NAO apaga o ato de encerramento: ele continua no livro e na
        #   corrente de hash (ver `ri_reabrir_matricula`, logo abaixo). Se o
        #   re-encerramento lavrasse outro, a ficha ficaria com DOIS
        #   «ENCERRAMENTO DESTA MATRICULA», e quem a lesse depois nao saberia
        #   qual dos dois vale — numa ficha que ja foi transportada para outra.
        #
        #   E A REGRA LE AS DUAS COLUNAS DA PROPRIA MATRICULA, e nao a natureza
        #   dos atos: medido em 15/09/2026, `natureza_titulo='Encerramento de
        #   matrícula'` existe em **zero** atos deste banco — os encerramentos
        #   reais desta casa vieram do acervo e das minutas importadas, sem
        #   essa marca. Procurar por ela acharia nada e lavraria o ato dobrado.
        if m["reaberta_em"] and m["data_encerramento"]:
            with db.transaction() as con:
                bd = banco(con)
                bd.escrever(
                    """UPDATE ri_matriculas SET encerrada=1, situacao='ENCERRADA',
                       reaberta_em=NULL, reaberta_por=NULL, motivo_reabertura=NULL,
                       atualizado_em=%s WHERE id=%s""",
                    (db.now(), matricula_id))
                bd.escrever(
                    "UPDATE ri_partes SET proprietario_ativo=0 WHERE matricula_id=%s",
                    (matricula_id,))
            audit("RI_MATRICULA_REENCERRADA", "RI_MATRICULA", matricula_id,
                  {"numero": m["numero"], "encerrada_em": m["data_encerramento"]})
            flash(f"Matrícula {m['numero']} fechada de novo, pelo encerramento "
                  f"que já estava no livro ({fmt_date(m['data_encerramento'])}). "
                  f"Nenhum ato novo foi lavrado.", "success")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        motivo = (request.form.get("motivo") or "").strip()
        destino = (request.form.get("destino") or "").strip()
        if not motivo:
            flash("Informe o motivo do encerramento.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        data_ato = (request.form.get("data_encerramento") or "").strip() or db.now()[:10]
        # O TEXTO MORA NA BASE — LF06B (`RI_ENCERRAMENTO_DIRETO` e, com
        # destino informado, `RI_ENCERRAMENTO_DIRETO_DESTINO`); a regra de
        # quando o destino entra e daqui. Vai ao livro e congela.
        import ri_frases
        with db.connect() as _c_frases:
            teor = (ri_frases.frase("RI_ENCERRAMENTO_DIRETO", _c_frases, motivo=motivo)
                    + (" " + ri_frases.frase("RI_ENCERRAMENTO_DIRETO_DESTINO", _c_frases,
                                             destino=destino) if destino else ""))

        with db.transaction() as con:
            bd = banco(con)
            bd.travar("ri_atos.numero")
            ultimo = bd.valor("SELECT MAX(numero) AS n FROM ri_atos WHERE matricula_id=%s",
                              (matricula_id,))
            numero = int((ultimo or 0)) + 1
            anterior = bd.um("""SELECT hash_ato FROM ri_atos WHERE matricula_id=%s
                                ORDER BY id DESC LIMIT 1""", (matricula_id,))
            hash_anterior = anterior["hash_ato"] if anterior else None
            h = hash_ato(m["numero"], "AV", numero, data_ato, teor, hash_anterior)
            bd.escrever(
                """INSERT INTO ri_atos
                   (matricula_id, tipo, numero, data_ato, natureza_titulo, teor,
                    teor_formato, cancelado, acervo, origem,
                    lavrado_nome, lavrado_titulo, lavrado_tratamento,
                    hash_ato, hash_anterior, lavrado_em)
                   VALUES (%s, 'AV', %s, %s, 'Encerramento de matrícula', %s, 'texto',
                           0, 0, 'MANUAL', %s,%s,%s, %s, %s, %s)""",
                (matricula_id, numero, data_ato, teor, *quem_pratica_o_ato(),
                 h, hash_anterior, db.now()),
            )
            # AS MARCAS DO ENCERRAMENTO MORAM NUM LUGAR SÓ. Esta rota e a de
            # lavrar (quando o ato lavrado É o encerramento) chamam a mesma
            # função — duas cópias divergiriam no primeiro conserto.
            _marcar_a_ficha_encerrada(bd, matricula_id, motivo=motivo,
                                      destino=destino, data_ato=data_ato)

        audit("RI_MATRICULA_ENCERRADA", "RI_MATRICULA", matricula_id,
              {"numero": m["numero"], "motivo": motivo, "destino": destino,
               "averbacao": f"AV-{numero:02d}"})
        flash(f"Matrícula {m['numero']} encerrada pela averbação AV-{numero:02d}. "
              f"Não é mais possível lavrar atos nela.", "success")
        return redirect(url_for("ri_ficha", matricula_id=matricula_id))

    @app.route("/registro-imoveis/<int:matricula_id>/reabrir", methods=["POST"])
    # REABRIR E DO OFICIAL — volta a ADMIN/MANAGER em 14/10/2026. O «USER»
    # entrou na 3.6.160 (21/09) numa troca em lote de perfis do RI, sem ordem
    # registrada, e deixou a rota mais larga que a tela (o botao em
    # ri_ficha.html continua so para ADMIN/MANAGER). A guarda e no servidor.
    @roles_required("ADMIN", "MANAGER")
    def ri_reabrir_matricula(matricula_id):
        """Desfaz o encerramento da ficha. NAO apaga o ato de encerramento.

        PEDIDO DO OFICIAL EM 15/09/2026 — «faça o reabrir matrícula». O
        encerramento era caminho de ida sem volta: havia rota para encerrar e
        nenhuma para reabrir, e a ficha esconde atras de «nao encerrada» as
        quatro coisas do balcao — lavrar registro ou averbacao, lavrar a
        partir de modelo, editar cadastro e cancelar ato.

        O CASO QUE A FEZ NASCER, e ele diz por que isto nao e conveniencia:
        a matricula 3.110 foi encerrada em 14/09 pela AV-06 que veio das
        minutas importadas, e os **tres atos daquele dia ficaram sem selo**.
        Com a ficha fechada nao ha por onde sela-los — o encerramento tranca
        justamente o ato que o fecha.

        O QUE ELA NAO FAZ, E POR QUE
            **Nao apaga nem cancela o ato de encerramento.** Ele esta no livro
            e na corrente de hash; apaga-lo seria reescrever a historia, que e
            o que a corrente existe para impedir. Desfazer o ato no livro e
            outra coisa, e ja tem caminho proprio: cancelar por averbacao.

            **Nao devolve a titularidade ativa.** O encerramento zera
            `proprietario_ativo` de todas as partes, e o sistema nao tem como
            saber qual delas volta a ser a dona — quem sabe e quem le o livro.
            A tela diz isso em vez de escolher por conta propria.

        O MOTIVO E ESCRITO, como no encerrar e na dispensa do usucapiao: quem
        abrir esta ficha daqui a dois anos vai ver um ato de encerramento no
        meio dela e a matricula aberta, e precisa saber por que.
        """
        m = q1("SELECT * FROM ri_matriculas WHERE id=%s", (matricula_id,))
        if not m:
            abort(404)
        voltar = redirect(url_for("ri_ficha", matricula_id=matricula_id))
        if not m["encerrada"]:
            flash("Esta matrícula não está encerrada — não há o que reabrir.",
                  "warning")
            return voltar

        motivo = (request.form.get("motivo") or "").strip()
        if len(motivo) < 10:
            flash("Escreva o motivo da reabertura com pelo menos dez letras. "
                  "«ok» não explica nada a quem ler a ficha depois.", "danger")
            return voltar

        agora = db.now()
        quem = app.extensions["usuario_nome"]()
        with db.transaction() as con:
            banco(con).escrever(
                """UPDATE ri_matriculas SET encerrada=0, situacao='ATIVO',
                   reaberta_em=%s, reaberta_por=%s, motivo_reabertura=%s,
                   atualizado_em=%s WHERE id=%s""",
                (agora, quem, motivo, agora, matricula_id))

        audit("RI_MATRICULA_REABERTA", "RI_MATRICULA", matricula_id,
              {"numero": m["numero"], "motivo": motivo,
               "encerrada_em": m["data_encerramento"],
               "motivo_encerramento": m["motivo_encerramento"]})
        flash(f"Matrícula {m['numero']} reaberta. O ato de encerramento "
              f"continua no livro — o que mudou é que a ficha volta a aceitar "
              f"atos. A titularidade ativa não volta sozinha: confira as "
              f"partes antes de lavrar.", "success")
        return voltar

    # --------------------------------------------------- nova matricula

    @app.route("/registro-imoveis/nova", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_nova_matricula():
        # MATRICULA NOVA NAO ESCOLHE VOLUME — decisao do oficial em 27/08/2026:
        # «nao faz sentido livro 2-S se estamos com sistema de fichas».
        #
        #   Ele tem razao, e a medicao mostra o tamanho: ha **20 volumes** de
        #   Livro 2 no banco, com os numeros ENTRELACADOS entre eles — o 2S vai
        #   de 8 a 4013, o 2A de 1 a 713, o 2C de 209 a 2667. Nao sao vinte
        #   series: e UMA sequencia da serventia, repartida em livros de papel
        #   conforme foram sendo escritos.
        #
        #   O volume e onde a FICHA DE PAPEL foi arquivada. Ficha nova nao vai
        #   para volume nenhum: ela nasce no sistema.
        #
        #   E a escolha era pior que inutil: vinte opcoes que devolvem todas o
        #   MESMO numero (4014, conferido uma a uma), com a unica diferenca de
        #   carimbar na matricula nova o nome de um livro fechado ha decadas.
        #
        # O VOLUME HISTORICO FICA. As 1.701 matriculas do acervo continuam
        # dizendo em que volume a ficha esta guardada — isso e informacao real,
        # e quem for a estante precisa dela.
        # O QUE VEIO DE ARQUIVO — relato #31, segunda metade. So no GET, e
        # consumido de uma vez: se ficasse na sessao, a matricula do proximo
        # cliente abriria com o imovel do anterior.
        do_arquivo = None
        if request.method == "GET":
            guardado = session.pop(IMPP.NA_SESSAO, None)
            if guardado and guardado.get("formulario") == "ri_nova_matricula":
                do_arquivo = guardado

        livro = SERIE_DA_MATRICULA
        proximo = None
        if request.method == "GET":
            # **A FRONTEIRA E A DELE, E VALE SEMPRE** — «numeros menores
            # que 4.015 sao acervo», informado pela serventia em 17/09/2026.
            #
            #   FICA DECLARADO o que ela produz numa INSTALACAO NOVA, onde o
            #   primeiro numero e 1: a tela apresenta toda matricula como
            #   ficha de acervo, e o primeiro ato e recusado pedindo o numero
            #   «conforme o livro fisico». Nesta casa nao acontece — o proximo
            #   e 4019 —, e o 4015 e numero desta serventia. E pergunta para
            #   ele, e nao conserto de quem programa.
            with db.connect() as con:
                proximo = RC.proximo_numero(con, livro)
            # HOTFIX-2026-10-13-06: reabrir o rascunho salvo (?rascunho_id=N).
            form_ini = do_arquivo["valores"] if do_arquivo else request.form
            rascunho_id = request.args.get("rascunho_id", type=int)
            if rascunho_id and not do_arquivo:
                import rascunho_de_tela as _RASCT
                try:
                    with db.connect() as _c:
                        _r = _RASCT.ler(_c, rascunho_id)
                    if _r.get("tela") != "ri_nova_matricula":
                        flash("Este rascunho não é de matrícula nova.", "danger")
                        rascunho_id = None
                    else:
                        form_ini = _r.get("dados") or {}
                        flash(f"Aberto do rascunho #{rascunho_id}. Confira os dados "
                              f"e o número ({proximo}) antes de gravar.", "info")
                except _RASCT.RascunhoError as _e:
                    flash(str(_e), "danger")
                    rascunho_id = None
            return render_template("ri_nova.html", livro=livro,
                                   proximo=proximo,
                                   e_acervo=matricula_de_acervo(proximo),
                                   do_arquivo=do_arquivo,
                                   rascunho_id=rascunho_id,
                                   form=form_ini)

        # O QR COLADO SAIU DA TELA — 14/09/2026, ordem do oficial. Medido antes
        # de tirar: das 1.701 matrículas, **zero** têm selo de abertura, e
        # nenhuma tem QR. As colunas ficam no esquema, e a ficha continua
        # mostrando o que houver nelas; o que saiu foi o campo de entrada.
        with db.transaction() as con:
            # O numero vem da SERIE, nao do volume. Contar por volume abriu a
            # matricula 4011 em 18/08/2026 quando a serventia ja tinha a 4013 no
            # volume 2S: numero de matricula nao se repete na serventia.
            bd = banco(con)
            bd.travar("ri_numeracao.livro")
            numero = RC.proximo_numero(con, livro)
            e_acervo = matricula_de_acervo(numero)
            pessoa_da_abertura = ((None, None, None) if e_acervo
                                  else quem_pratica_o_ato())
            if not bd.um("SELECT 1 AS um FROM ri_numeracao WHERE livro=%s", (livro,)):
                bd.escrever(
                    """INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso, fixado_em, observacao)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (livro, numero, numero - 1, db.now(),
                     "Livro aberto ao cadastrar a primeira matrícula"),
                )
            ocupada = RC.numero_em_uso(con, livro, numero)
            if ocupada:
                flash(f"O número {numero} já existe no Livro {ocupada['livro']}. "
                      f"Ajuste a numeração antes de continuar.", "danger")
                return render_template("ri_nova.html", livro=livro, proximo=numero,
                                       e_acervo=matricula_de_acervo(numero),
                                       do_arquivo=None, form=request.form,
                                       rascunho_id=request.form.get("_rascunho_id_tela", type=int))  # HOTFIX-2026-10-13-06

            _rural = (request.form.get("rural_urbano") or "").strip() or None
            _cib = (request.form.get("cib") or "").strip() or None
            # HOTFIX-2026-10-13-06: CIB so de zeros = vazio nas matriculas dispensadas.
            if (_cib and not _cib_normalizado(_cib).strip("0")
                    and _cib_dispensado(numero, db.get_setting("cib_dispensado_matriculas", ""))):
                _cib = None
            if (_exige_cib(_rural) and not _cib_valido(_cib)
                    and not _cib_dispensado(numero, db.get_setting("cib_dispensado_matriculas", ""))):
                flash(_mensagem_cib_obrigatorio(), "danger")
                return render_template("ri_nova.html", livro=livro, proximo=numero,
                                       e_acervo=matricula_de_acervo(numero),
                                       do_arquivo=None, form=request.form,
                                       rascunho_id=request.form.get("_rascunho_id_tela", type=int))  # HOTFIX-2026-10-13-06

            novo_id = bd.escrever(
                """INSERT INTO ri_matriculas
                   (numero, complemento, livro, livro_norm, folha, data_abertura,
                    selo_abertura_texto, selo_abertura_qr, selo_abertura_qr_mime,
                    selo_abertura_qr_2, selo_abertura_qr_2_mime, emolumentos_abertura,
                    tipo_ficha, situacao, conferido, rural_urbano, logradouro, numero_predial,
                    bairro, cidade, uf, cep, area_valor, area_unidade, descricao_perimetro,
                    confrontacoes, inscricao_municipal,
                    registro_anterior, teor, teor_formato, cnm, cib, origem, criado_em,
                    criado_por, aberta_nome, aberta_titulo, aberta_tratamento)
                   VALUES (%(numero)s,'',%(livro)s,%(livro_norm)s,%(folha)s,%(data_abertura)s,
                    %(selo_texto)s,%(qr1)s,%(mime1)s,%(qr2)s,%(mime2)s,%(emolumentos)s,
                    %(tipo_ficha)s,'ATIVA',%(conferido)s,%(rural_urbano)s,%(logradouro)s,%(numero_predial)s,
                    %(bairro)s,%(cidade)s,%(uf)s,%(cep)s,%(area_valor)s,%(area_unidade)s,%(descricao_perimetro)s,
                    %(confrontacoes)s,%(inscricao_municipal)s,
                    %(registro_anterior)s,%(teor)s,'texto',%(cnm)s,%(cib)s,'MANUAL',%(criado_em)s,NULL,
                    %(aberta_nome)s,%(aberta_titulo)s,%(aberta_tratamento)s)
                   RETURNING id""",
                {
                 # QUEM ABRIU A MATRICULA, CONGELADO AQUI — pedido do oficial
                 # em 16/09/2026: «precisa ter espaco pra quem abriu a
                 # matricula assinar».
                 #
                 #   `criado_por` continua NULL de proposito: ele e um `id` de
                 #   usuario, e o papel nao imprime `id`. O que o papel
                 #   precisa e o NOME, o TITULO e o TRATAMENTO no dia da
                 #   abertura — os mesmos tres que `ri_atos` congela na
                 #   lavratura, e pela mesma razao: se a funcao de quem
                 #   assinou mudar amanha, esta ficha continua dizendo o que
                 #   dizia hoje.
                 #
                 #   MEDIDO ANTES: `criado_por` estava NULL em **1.982 de
                 #   1.982** — esta linha gravava `NULL` escrito, e nenhuma
                 #   ficha desta casa jamais soube quem a abriu.
                 **dict(zip(("aberta_nome", "aberta_titulo",
                             "aberta_tratamento"), pessoa_da_abertura)),
                 "numero": str(numero), "livro": livro, "livro_norm": norm_livro(livro),
                 "tipo_ficha": "ACERVO" if e_acervo else "ESTRUTURADA",
                 "conferido": 0 if e_acervo else 1,
                 "folha": (request.form.get("folha") or "").strip() or None,
                 "data_abertura": (request.form.get("data_abertura") or "").strip() or db.now()[:10],
                 # A abertura de acervo nao ganha selo do sistema. Mesmo que
                 # um cliente antigo ainda envie o campo escondido, ele e
                 # ignorado abaixo de 4.015.
                 "selo_texto": (None if e_acervo else
                                 (request.form.get("selo_abertura_texto") or "").strip()
                                 or None),
                 "qr1": None, "mime1": None, "qr2": None, "mime2": None,
                 "emolumentos": (request.form.get("emolumentos_abertura") or "").strip() or None,
                 "rural_urbano": (request.form.get("rural_urbano") or "").strip() or None,
                 "logradouro": (request.form.get("logradouro") or "").strip() or None,
                 "numero_predial": (request.form.get("numero_predial") or "").strip() or None,
                 "bairro": (request.form.get("bairro") or "").strip() or None,
                 "cidade": (request.form.get("cidade") or "").strip() or None,
                 "uf": (request.form.get("uf") or "").strip() or None,
                 "cep": (request.form.get("cep") or "").strip() or None,
                 "area_valor": (request.form.get("area_valor") or "").strip() or None,
                 "area_unidade": (request.form.get("area_unidade") or "").strip() or None,
                 "descricao_perimetro": (request.form.get("descricao_perimetro") or "").strip() or None,
                 # LT03 (20/10/2026): a tela passou a pedir as confrontações —
                 # LRP art. 176, § 1º, II, 3. A coluna já existia e a ficha já
                 # a imprimia; faltava quem a gravasse na abertura.
                 "confrontacoes": (request.form.get("confrontacoes") or "").strip() or None,
                 # e a designação cadastral (LRP art. 176, § 1º, II, 3, b).
                 "inscricao_municipal": (request.form.get("inscricao_municipal") or "").strip() or None,
                 "registro_anterior": (request.form.get("registro_anterior") or "").strip() or None,
                 "teor": (request.form.get("teor") or "").strip() or None,
                 # O CÓDIGO NACIONAL DA MATRÍCULA — débito do backlog.
                 #
                 #   Medido em 28/08/2026: das 1.701 matrículas, **45 não têm
                 #   CNM**, e **duas delas foram lavradas por este sistema**.
                 #   Toda matrícula nova nascia sem o seu código nacional.
                 #
                 #   E aqui gerar é legítimo, ao contrário da matrícula de 32
                 #   dígitos do RCPN: o verificador do CNM é ISO 7064 MOD 97-10
                 #   — a conta do IBAN — e ela reproduz **1.656 dos 1.656** CNM
                 #   que esta casa já emitiu. Não é palpite; é reproduzir o que
                 #   já existe.
                 #
                 #   SEM CNS NÃO SAI CNM, e a matrícula sai assim mesmo: o
                 #   código é identificação, e não pode impedir a abertura.
                 "cnm": _cnm_da_matricula(livro, numero),
                 "cib": _cib_normalizado(_cib) or None,
                 "criado_em": db.now()},
            )[0]["id"]
            novo_id = int(novo_id)
            # PROPRIETARIO DA ABERTURA — 23/09/2026 (Beatriz 4018/4019).
            # Sem isto a ficha nasce sem ri_partes com ato_id IS NULL e
            # ri_selar_abertura recusa. Acervo nao pede: abertura historica.
            if not e_acervo:
                prop_nome = (request.form.get("proprietario_nome") or "").strip()
                if prop_nome:
                    prop_doc = so_digitos(request.form.get("proprietario_documento") or "")
                    prop_tipo = ("CPF" if len(prop_doc) == 11
                                 else "CNPJ" if len(prop_doc) == 14 else None)
                    bd.escrever(
                        """INSERT INTO ri_partes
                           (matricula_id, ato_id, nome, nome_norm, documento_tipo,
                            documento_numero, documento_valido, papel, qualificacao,
                            proprietario, proprietario_ativo, origem, origem_chave)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (novo_id, None, prop_nome, normalizar_busca(prop_nome),
                         prop_tipo, prop_doc or None,
                         1 if prop_doc and valida_cpf_cnpj(prop_doc) else
                         (0 if prop_doc else None),
                         # A QUALIFICAÇÃO DO DONO DA ABERTURA — LT03, 20/10/2026:
                         # LRP art. 176, § 1º, II, 4, e CN-MA art. 479, I. Era
                         # `None` escrito, e a ficha saía só com nome e CPF.
                         "proprietario",
                         (request.form.get("proprietario_qualificacao") or "").strip() or None,
                         1, 1, "MANUAL",
                         "abertura_nova_matricula"),
                    )
            # Avanca a serie inteira: todos os volumes passam a apontar para o
            # numero seguinte, senao o proximo volume repetiria este numero.
            RC.sincronizar_numeracao(con, livro, db.now())

        audit("RI_MATRICULA_ABERTA", "RI_MATRICULA", novo_id,
              {"numero": numero, "livro": livro,
               "tipo_ficha": "ACERVO" if e_acervo else "ESTRUTURADA"})
        flash(f"Matrícula {numero} aberta no livro {livro}. "
              f"O próximo número do livro passou a ser {numero + 1}.", "success")
        return redirect(url_for("ri_ficha", matricula_id=novo_id))

    # ------------------------------------------------------ importacao

    # ------------------------------------------- ficha modelo e LibreOffice

    def contexto_ficha(matricula_id: int, para_odt: bool = True) -> dict:
        m = q1("SELECT * FROM ri_matriculas WHERE id=%s", (matricula_id,))
        if not m:
            abort(404)
        m = dict(m)
        if matricula_de_acervo(m["numero"]):
            m["tipo_ficha"] = "ACERVO"
        atos = q("""SELECT * FROM ri_atos WHERE matricula_id=%s
                    ORDER BY numero, tipo""", (matricula_id,))
        # O ATO QUE O TEOR JA CONTA NAO SE REPETE NO PAPEL — e o que decide
        # isso e o TEOR IR AO PAPEL, e nao o tipo da ficha.
        #
        #   Este contexto serve a dois papeis, e eles nao imprimem a mesma
        #   coisa:
        #
        #     A FICHA (`para_odt=True`) imprime o teor **so quando ela e
        #     ACERVO** — decisao de 16/09/2026, com teste proprio em
        #     `tests/test_ri_assinatura_da_abertura.py`. Na ficha estruturada
        #     o teor NAO sai, entao tirar da lista o ato que ele conta o
        #     apagaria do papel — e ato que some do papel e pior que ato
        #     repetido: o teor escondido nao esta la para contar por ele.
        #
        #     A CERTIDAO (`para_odt=False`) imprime o teor **sempre que ele
        #     existe** — e o relato #79, de 17/09/2026: a 4.016 saiu com 674
        #     caracteres, so a introducao e o fecho, porque a guarda do molde
        #     perguntava o tipo da ficha. Aqui a regra vale inteira.
        #
        #   A CONTA E UMA SO — `atos_fora_do_teor` —, feita uma vez e usada
        #   pelos dois papeis. Escreve-la de novo no outro lado divergiria no
        #   primeiro conserto, e e ela que decide se um ato APARECE.
        # HOTFIX-2026-10-13-09 (escrevente, 13/10/2026, mat. 4023): ficha
        # ESTRUTURADA com descricao preenchida imprimia so os campos (IMOVEL:
        # descricao...) e deixava o teor de fora. As matriculas listadas em
        # `settings.ri_ficha_teor_no_papel` imprimem o TEOR inteiro na ficha.
        if (para_odt and (m.get("teor") or "").strip()
                and _cib_dispensado(m["numero"], db.get_setting("ri_ficha_teor_no_papel", ""))):
            m["tipo_ficha"] = "ACERVO"
            m["_teor_no_papel"] = True  # HOTFIX-2026-10-15-01: nao e acervo, o selo de abertura sai
        teor_vai_ao_papel = (m["tipo_ficha"] == "ACERVO") or not para_odt
        atos_para_o_papel = (NUMT.atos_fora_do_teor(m["teor"], atos, matricula=m)
                             if teor_vai_ao_papel else atos)
        partes = q("SELECT * FROM ri_partes WHERE matricula_id=%s ORDER BY id", (matricula_id,))
        s = db.get_settings()

        # O CARIMBO LE A ETIQUETA DO RAZAO, E NAO A COLUNA DO ATO — correcao de
        # 15/09/2026: «o relatorio de emolumentos deve ir junto com o carimbo do
        # selo e qr code».
        #
        #   A COLUNA SE CHAMA `selo_texto` E RECEBE O NUMERO. Medido no ato
        #   3737: `ri_atos.selo_texto` tem `AVESVD000000IFWIQRMJW7CGUA95`, 28
        #   caracteres — e so. Quem grava e `ato_selado.vincular_ao_ato`, com
        #   `str(numero)`. A etiqueta inteira, com data, ato, partes e **todos
        #   os fundos**, mora em `sd_selos.texto`.
        #
        #   A CONSEQUENCIA ERA QUE O CARIMBO NUNCA MOSTRAVA OS EMOLUMENTOS:
        #   `valores_para_o_carimbo(selo_texto)` devolve **vazio** (medido),
        #   porque nao ha valor nenhum num codigo de 28 caracteres; com o texto
        #   do razao devolve `Total R$ 134,43 Emol R$ 120,03 FERC R$ 3,60 FEMP
        #   R$ 4,80 FADEP R$ 4,80 FERRFIS R$ 1,20`. **E isso valia para todo
        #   ato do RI selado automaticamente**, e nao so para este.
        #
        #   NAO SE MEXEU EM `vincular_ao_ato`: ela grava o numero em cinco
        #   tabelas de cinco atribuicoes, e mudar o que ela escreve mexeria no
        #   cartao de autografo e na prenotacao junto. Quem tem de ler a fonte
        #   certa e quem DESENHA o carimbo — e a fonte e o razao.
        #
        #   A CHAVE E `tabela` MAIS `ato_id`: por `ato_id` sozinho vem selo de
        #   outra atribuicao (medido em 15/09 — tres reconhecimentos de firma
        #   de 2022 responderam por ids de `ri_atos`).
        # VARIOS SELOS POR ATO — Beatriz 24/09/2026 (certidão mat. 4001):
        # o razão guarda 16.22.8.1 + 16.5 x2 no mesmo ato; a ficha HTML já
        # lia a lista, mas este contexto (certidão + .odt) ficava só com o
        # PRIMEIRO via setdefault. Agora a lista inteira vai ao carimbo.
        selo_do_ato: dict[int, list[str]] = {}
        if atos:
            lugares = ",".join(["%s"] * len(atos))
            # HOTFIX-2026-10-07-04/selos (Beatriz 08/10/2026, mat. 4019): selo
            # CANCELADO no razão não vai ao carimbo (R-01 saía com 2 selos de
            # registro), e o 16.39 do ato não se repete como «averbação 2/2»
            # — ele já sai no carimbo próprio de arquivamento.
            _arq_do_ato = {int(a["id"]): str(a["selo_arquivamento"] or "").strip()
                           for a in atos}
            for r in q(f"""SELECT ato_id, numero, texto FROM sd_selos
                            WHERE tabela='ri_atos' AND ato_id IN ({lugares})
                              AND cancelado_em IS NULL
                            ORDER BY id""",
                       [int(a["id"]) for a in atos]):
                _arq = _arq_do_ato.get(int(r["ato_id"]))
                if _arq and str(r["numero"] or "").strip() == _arq:
                    continue
                txt = str(r["texto"] or "").strip()
                if txt:
                    selo_do_ato.setdefault(int(r["ato_id"]), []).append(txt)

        # O SELO DA ABERTURA, DO RAZAO — 16/09/2026. Mesma chave e mesma
        # razao do ato: a coluna da ficha guarda o numero, e a etiqueta com
        # os valores mora em `sd_selos`.
        _abertura = q1(
            """SELECT texto, numero, qr_token FROM sd_selos
                WHERE tabela='ri_matriculas' AND ato_id=%s
                ORDER BY obtido_em DESC, id DESC LIMIT 1""", (matricula_id,))
        selo_da_abertura = dict(_abertura) if _abertura else {}

        def etiqueta_da_abertura() -> str | None:
            """A etiqueta do selo da abertura. So le."""
            return (str(selo_da_abertura.get("texto") or "").strip()
                    or m["selo_abertura_texto"])

        def etiquetas_do_ato(a) -> list[str]:
            """As etiquetas que o carimbo imprime (todas do razão). Só lê.

            O razão primeiro (lista completa); a coluna do ato como reserva —
            e ela é o que os atos do acervo têm, porque para eles nunca houve
            razão. Um ato com 16.22.8.1 + 16.5×2 devolve três etiquetas.
            """
            do_razao = list(selo_do_ato.get(int(a["id"])) or [])
            if do_razao:
                return do_razao
            um = str(a["selo_texto"] or "").strip()
            return [um] if um else []


        # SELO DA PRENOTACAO DO PROTOCOLO — 22/09/2026.
        # Um protocolo pode gerar varios atos; em cada um, o carimbo leva o
        # selo da prenotacao + o selo do ato lavrado.
        _prenot_por_digito: dict[str, str] = {}
        _nums_proto = []
        for _a in atos:
            _n = str(_a["protocolo"] or "").strip()
            _d = "".join(ch for ch in _n if ch.isdigit()) if _n else ""
            if _d:
                _nums_proto.append(_d)
        if _nums_proto:
            _lug = ",".join(["%s"] * len(_nums_proto))
            for _r in q(
                f"""SELECT CAST(numero AS TEXT) numero, selo_prenotacao
                      FROM ri_protocolos
                     WHERE REPLACE(CAST(numero AS TEXT), '.', '') IN ({_lug})
                        OR CAST(numero AS TEXT) IN ({_lug})
                     ORDER BY id""",
                _nums_proto + _nums_proto,
            ):
                _d = "".join(
                    ch for ch in str(_r["numero"] or "") if ch.isdigit())
                if _d and _r["selo_prenotacao"]:
                    _prenot_por_digito.setdefault(_d, _r["selo_prenotacao"])
            _selos = list({v for v in _prenot_por_digito.values() if v})
            _etiq: dict[str, str] = {}
            if _selos:
                _lug = ",".join(["%s"] * len(_selos))
                for _r in q(
                    f"""SELECT numero, texto FROM sd_selos
                         WHERE numero IN ({_lug}) ORDER BY obtido_em, id""",
                    _selos,
                ):
                    _etiq.setdefault(_r["numero"], _r["texto"])
            for _d, _num in list(_prenot_por_digito.items()):
                _prenot_por_digito[_d] = (
                    str(_etiq.get(_num) or "").strip() or _num)

        def etiqueta_da_prenotacao(a) -> str | None:
            """Etiqueta do selo de prenotacao do protocolo do ato. So le."""
            _n = str(a["protocolo"] or "").strip()
            _d = "".join(ch for ch in _n if ch.isdigit()) if _n else ""
            if not _d:
                return None
            return _prenot_por_digito.get(_d)

        # QR dos carimbos do ODT: o dict e preenchido por
        # carimbo_compacto_odf e entregue em _imagens_selo.
        # Sem ele, NameError ao imprimir a ficha (aj_problemas #94,
        # matricula 1197 / 22/09/2026).
        imagens_selo: dict = {}

        def carimbos_do_ato(a) -> str:
            """Prenotacao (se houver) + selo do ato + arquivamento. Pedido 22/09/2026.

            22/09/2026 - ficha RI: um odf() para prenotacao+ato: dois selo_convertido geravam @@ODFn@@@@ODFm@@
            no mesmo <p> do modelo; tabela do carimbo sumia no LibreOffice.
            23/09/2026 - arquivamento 16.39 opcional (Beatriz).
            """
            def _etiqueta_arquivamento(ato):
                arq_num = str(ato["selo_arquivamento"] or "").strip()
                if not arq_num:
                    return None, None
                arq_et = None
                with db.connect() as _c:
                    arq_et = banco(_c).um(
                        """SELECT texto FROM sd_selos WHERE numero=%s
                            ORDER BY obtido_em DESC LIMIT 1""",
                        (arq_num,))
                arq_txt = (str((arq_et["texto"] if arq_et else "") or "").strip()
                           or arq_num)
                try:
                    folhas_arq = ato["folhas_arquivamento"]
                except (KeyError, IndexError, TypeError):
                    folhas_arq = None
                rot_arq = "SELO DE ARQUIVAMENTO"
                if folhas_arq:
                    rot_arq = f"SELO DE ARQUIVAMENTO ({folhas_arq} fl.)"
                return arq_txt, rot_arq

            if para_odt:
                brutos = []
                pre = etiqueta_da_prenotacao(a)
                if pre:
                    brutos.append(carimbo_compacto_odf(
                        pre, rotulo='SELO DE PRENOTAÇÃO',
                        imagens=imagens_selo))
                etiquetas = etiquetas_do_ato(a)
                # HOTFIX-2026-10-09-06: rotulo pelo prefixo do selo.
                for et, rotulo in selos_do_ato_rotulados(a["tipo"], etiquetas):
                    brutos.append(carimbo_compacto_odf(
                        et, rotulo=rotulo, imagens=imagens_selo))
                arq_txt, rot_arq = _etiqueta_arquivamento(a)
                if arq_txt:
                    brutos.append(carimbo_compacto_odf(
                        arq_txt, rotulo=rot_arq, imagens=imagens_selo))
                return odf("".join(brutos)) if brutos else ""
            partes = []
            pre = etiqueta_da_prenotacao(a)
            if pre:
                partes.append(selo_convertido(
                    pre, rotulo='SELO DE PRENOTAÇÃO'))
            etiquetas = etiquetas_do_ato(a)
            # HOTFIX-2026-10-09-06: rotulo pelo prefixo do selo.
            for et, rotulo in selos_do_ato_rotulados(a["tipo"], etiquetas):
                partes.append(selo_convertido(et, rotulo=rotulo))
            arq_txt, rot_arq = _etiqueta_arquivamento(a)
            if arq_txt:
                partes.append(selo_convertido(arq_txt, rotulo=rot_arq))
            return "".join(partes)




        # A CERTIDAO guarda o corpo renderizado no banco, para
        # congelar o teor da emissao: se a marca fosse gravada, a reimpressao
        # de anos depois sairia com "@@ODF0@@" no lugar do texto.
        # Restaurado 23/09/2026: o patch do arquivamento (3.6.177) apagou
        # este bloco e o def odf; NameError em contexto_ficha (aj #102).
        fragmentos: dict[str, str] = {}

        def odf(pedaco: str) -> str:
            if not pedaco or not para_odt:
                return pedaco
            chave = f"@@ODF{len(fragmentos)}@@"
            fragmentos[chave] = pedaco
            return chave

        # A CERTIDAO nao vai para .odt na hora: ela GRAVA o corpo renderizado no
        # banco, em HTML, para congelar o teor da emissao. Entregar-lhe ODF punha
        # `<text:p text:style-name="P-just">` no meio do texto certificado - foi o
        # que saiu impresso na certidao 6/2026, de 18/08/2026. Por isso a conversao
        # em si depende do destino, e nao apenas o embrulho do fragmento.

        def teor_convertido(texto, formato, sem_margem_final=False, fecho=None):
            # TEXTO CORRIDO NO PAPEL E NA CERTIDÃO — Beatriz 24/09/2026
            # (mat. 4001): teor OCR com um <p> por linha saía desorganizado
            # na certidão E na ficha. Junta o miolo e só quebra em rótulo de
            # ato / linha em branco. A risca entre atos vira P-separa-ato
            # (largura total) via html_para_odf.
            #
            # Assinatura à mão: o fecho do ato (ficha) continua anexado
            # abaixo; a certidão remove só o traço (sem_linha_de_assinatura).
            texto, formato = __import__("modelos_motor_html").corrigir_teor_f01(texto, formato)  # F01 HTML cru
            bruto_html = ((texto or "") if formato == "html"
                          else texto_para_html(texto))
            bruto_html = html_em_texto_corrido(bruto_html, m["numero"])
            if para_odt:
                bruto = html_para_odf(bruto_html)
                # A LINHA TRACADA ENTRE UM ATO E O SEGUINTE — pedido do
                # oficial em 31/08/2026. Vai no ODF já convertido: o teor
                # guardado não muda; a risca é apresentação no papel.
                # Se o HTML já trouxe separa-ato, separar_atos não empilha.
                bruto = separar_atos(bruto, m["numero"])
                if fecho:
                    bruto = anexar_fecho_ao_ato(bruto, fecho)
                elif sem_margem_final:
                    bruto = ato_sem_espaco_antes_do_fecho(bruto)
                return odf(bruto)
            return bruto_html

        def selo_convertido(selo_texto, rotulo=None):
            """O carimbo do selo no LIVRO: uma linha, sem QR e sem link.

            ORDEM DO OFICIAL EM 16/09/2026: «nao faz sentido qr code de selo e
            link de acesso a consulta de selo no livro. Vamos trabalhar numa
            etiqueta mais compacta, preferencia que ocupe apenas uma linha,
            com as outras informacoes, apenas tire qr code e link de acesso».

            O CONTEUDO NAO ENCOLHEU: numero, ato, data, hora, total,
            emolumentos e cada fundo continuam na linha. O que saiu foi o
            atalho — e o numero de 28 caracteres, que e o que responde «este
            selo e real?», esta la inteiro.

            **E ELA PERDEU UM PARAMETRO QUE NINGUEM LIA.** Ate aqui recebia
            `emolumentos`, calculado por duas funcoes de quinze linhas, e
            **nao o usava em lugar nenhum**: quem imprime os valores e a
            propria etiqueta, desde 15/09, quando o carimbo trocou de desenho.
            E «peca pronta que ninguem usa» na forma de argumento — nenhum
            varredor a veria, porque a funcao tinha chamador e o parametro
            chegava preenchido.
            """
            if para_odt:
                # QR no pacote do .odt — as imagens vão em `_imagens_selo`.
                return odf(carimbo_compacto_odf(
                    selo_texto, rotulo=rotulo or "SELO DIGITAL DO TJMA",
                    imagens=imagens_selo))
            # Tela = papel: número, emolumentos e QR (22/09/2026).
            return carimbo_compacto_html(
                selo_texto, rotulo=rotulo or "SELO DIGITAL DO TJMA")

        # Prenotações ABERTO desta matrícula — fecho da certidão
        # (Lei 6.015/1973 + Provimento CNJ 149/2023). Pedido Beatriz 23/09/2026.
        with db.connect() as _c_pren:
            _prenot_abertas = prenotacoes_abertas_da_matricula(
                _c_pren, matricula_id, m.get("numero"))
            # O TEXTO DA CLAUSULA MORA NA BASE (LF06B); a regra fica aqui.
            _clausula_prenot = clausula_html_prenotacoes_abertas(
                _prenot_abertas, fmt_date=fmt_date, con=_c_pren)
        # CABEÇALHO DO ATO COM A DATA DA PRENOTAÇÃO — HOTFIX-2026-10-07-04
        # (Beatriz, mat. 4019). O molde imprimia «PROTOCOLO Nº 11546, DE
        # 2026-09-23» (data do ATO, em ISO); o cabeçalho pede o número e a
        # data do PROTOCOLO. Fonte: a prenotação gravada no próprio ato; senão
        # o Livro 1 pelo número, com a prenotação até 365 dias antes do ato
        # (números antigos se repetem entre eras). Sem achar, None e o molde
        # volta ao comportamento antigo.
        def _data_iso_ou_br(v):
            v = str(v or "").strip()
            if not v:
                return None
            try:
                if re.match(r"^\d{4}-\d{2}-\d{2}", v):
                    return date.fromisoformat(v[:10])
                mm = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", v)
                if mm:
                    return date(int(mm.group(3)), int(mm.group(2)), int(mm.group(1)))
            except ValueError:
                return None
            return None

        def _protocolo_cab(a) -> str | None:
            bruto = str(a["protocolo"] or "").strip()
            if not bruto:
                return None
            if re.fullmatch(r"\d{4,}", bruto):
                return f"{int(bruto):,}".replace(",", ".")
            return bruto

        _data_prenot_cab: dict[int, str] = {}
        for _a in atos:
            try:
                _d_ato = _data_iso_ou_br(_a["data_ato"])
                _d_pre = _data_iso_ou_br(dict(_a).get("prenotacao"))
                if not _d_pre:
                    _dig = "".join(ch for ch in str(_a["protocolo"] or "") if ch.isdigit())
                    if _dig and _d_ato:
                        _r = q1(
                            """SELECT data_prenotacao FROM ri_protocolos
                                WHERE REPLACE(CAST(numero AS TEXT), '.', '') = %s
                                  AND date(data_prenotacao) <= %s
                                  AND date(data_prenotacao) >= %s
                                ORDER BY data_prenotacao DESC, id DESC LIMIT 1""",
                            (_dig, _d_ato.isoformat(),
                             (_d_ato - timedelta(days=365)).isoformat()))
                        if _r:
                            _d_pre = _data_iso_ou_br(_r["data_prenotacao"])
                if _d_pre:
                    _data_prenot_cab[int(_a["id"])] = (
                        f"{_d_pre.day:02d} DE {MESES[_d_pre.month - 1].upper()} "
                        f"DE {_d_pre.year}")
            except Exception:                                  # noqa: BLE001
                continue

        # Onus sao REGISTROS e AVERBACOES restritivos nao cancelados —
        # hipoteca, alienacao fiduciaria, usufruto e servidao sao R. A regra
        # (natureza estruturada antes, palavra-chave como apoio) mora em
        # `ri_onus`. E O QUE A CERTIDAO DIZ QUANDO NINGUEM ESCOLHEU (positiva
        # ou negativa, ônus e ações) mora em `ri_onus_ia.padrao_do_sistema` —
        # a escolha do balcão, com a sugestão da IA, troca isto na emissão.
        _onus = RIONUS.onus_vigentes(
            atos, rotulo=lambda a: rotulo_ato(a["tipo"], a["numero"], m["numero"]))
        # A data do ato vai POR EXTENSO na linha do ônus — a peça pronta da
        # casa, e não a data crua do banco (a lição da certidão 6/2026, 28/08).
        for _o in _onus:
            if not _o.get("data_extenso") and _o.get("data_ato"):
                try:
                    _o["data_extenso"] = data_por_extenso(
                        date.fromisoformat(str(_o["data_ato"])[:10]))
                except ValueError:
                    pass

        # AS FRASES DOS FECHOS — LF06B: lidas UMA vez por ficha (ajuste da casa
        # → padrao da base), e nao uma conexao por ato.
        import ri_frases
        with db.connect() as _c_frases:
            _fechos = ri_frases.ler(_c_frases, "RI_FECHO_DO_ATO",
                                    "RI_FECHO_DO_ATO_SEM_TITULO",
                                    "RI_FECHO_DA_ABERTURA")
        _ctx = {
            **RONIA.padrao_do_sistema(_onus),
            "_fragmentos": fragmentos,
            "m": dict(m),
            "atos": [dict(a) | {
                "teor_odf": teor_convertido(
                    teor_sem_cabecalho_do_ato(
                        a["teor"], a["tipo"], a["numero"], m["numero"]),
                    a["teor_formato"], True,
                    fecho_do_ato(
                        m["cidade"] or s.get("ri_cidade", ""),
                        m["uf"] or s.get("ri_uf", "MA"),
                        a["data_ato"], a["teor"], a["lavrado_nome"],
                        a["lavrado_titulo"], a["lavrado_tratamento"],
                        lido=_fechos)
                    if para_odt else None),
                # Certidao inteiro teor: destaca R-01/AV-02 no miolo.
                # O TEOR VAI INTEIRO — 14/10/2026. Ate aqui ele passava por
                # `teor_sem_cabecalho_do_ato`, que corta a primeira frase
                # (natureza, protocolo ou data) porque a FICHA a imprime na
                # linha `ato-cab`; a certidao nao tem essa linha, e a frase
                # sumia do papel que se chama «inteiro teor» (a data do ato
                # em `AV-28/582 — 18 de agosto de 2026.` desaparecia).
                "teor_certidao_odf": (
                    teor_convertido(a["teor"], a["teor_formato"], True, None)
                    if para_odt else
                    html_com_destaque_rotulo_ato(
                        teor_convertido(a["teor"], a["teor_formato"], True,
                                        None),
                        a["tipo"], a["numero"], m["numero"])),
                "rotulo": rotulo_ato(a["tipo"], a["numero"], m["numero"]),
                # HOTFIX-2026-10-07-04: nº com ponto e data da prenotação.
                "protocolo_cab": _protocolo_cab(a),
                "protocolo_data_cab": _data_prenot_cab.get(int(a["id"])),
                "natureza_titulo": natureza_titulo_sem_rotulo(
                    dict(a).get("natureza_titulo"), a["tipo"], a["numero"], m["numero"]),
                "selo_odf": carimbos_do_ato(a),
                "data_extenso": (data_por_extenso(date.fromisoformat(a["data_ato"]))
                                 if a["data_ato"] else None),
                # Quem praticou o ato — e ele vem DO PROPRIO ATO, gravado na
                # lavratura (relato #65: quem esta logado, e nao se escolhe).
                #
                #   CORRECAO DE 15/09/2026: aqui estava escrito que «ato do
                #   acervo resolve pelo periodo do delegatario da epoca», e o
                #   codigo NAO fazia isso — nem antes nem agora. O acervo nao
                #   precisa: em 1.197 dos 1.239 atos herdados o fecho com o
                #   nome ja esta escrito DENTRO do teor, e sai na impressao
                #   porque o teor sai. Nos 3% restantes o ato sai sem fecho,
                #   que e o certo: melhor faltar o nome do que atribuir o ato a
                #   quem nao o praticou. Deduzir por periodo acertaria as vezes
                #   e erraria as outras, sem avisar qual foi qual — ha
                #   delegatarios, substitutos, interinos e escreventes no mesmo
                #   intervalo. Comentario que afirma isto e igual a aquilo e
                #   afirmacao que ninguem verifica; este afirmava o contrario
                #   do que `fecho_do_ato` faz.
                "fecho": None if para_odt else fecho_do_ato(
                    m["cidade"] or s.get("ri_cidade", ""),
                    m["uf"] or s.get("ri_uf", "MA"),
                    a["data_ato"], a["teor"],
                    a["lavrado_nome"], a["lavrado_titulo"], a["lavrado_tratamento"],
                    lido=_fechos),
            } for a in atos_para_o_papel],
            "partes": [dict(p) for p in partes],
            "proprietarios": [dict(p) for p in partes if p["proprietario_ativo"]],
            # HOTFIX-2026-10-07-04: a ABERTURA mostra os titulares de origem
            # (partes da abertura, sem ato), e não quem é dono hoje.
            "proprietarios_abertura": [dict(p) for p in partes
                                       if p["ato_id"] is None and p["proprietario"]],
            "teor_odf": teor_convertido(m["teor"], m["teor_formato"]),
            # Identificacao da serventia num lugar so (serventia.py): o
            # timbre nao pode divergir entre ficha, certidao, nota e recibo.
            "serventia": dados_serventia(db.get_settings) | {
                "nome": s.get("unit_name") or dados_serventia(db.get_settings)["unit_name"],
                "cns": s.get("ri_cns", ""),
                "cidade": s.get("ri_cidade", ""),
                "uf": s.get("ri_uf", "MA"),
                "registrador": s.get("ri_registrador", ""),
                "substituta": s.get("ri_substituta") or dados_serventia(db.get_settings)["ri_substituta"],
                "titulo_registrador": s.get("ri_titulo_registrador", "Tabelião Registrador"),
                "titulo_substituta": s.get("ri_titulo_substituta",
                                           "Tabeliã Registradora Substituta"),
            },
            # Quem esta imprimindo — o "USUÁRIO" do cabecalho do modelo em papel.
            # Identificação da ficha, no formato do modelo em papel.
            # O acervo tem lixo nesses campos — livro "2R", folha "fichas" —
            # então o número da ficha só sai quando é número mesmo.
            "data_abertura_br": (fmt_date(m["data_abertura"]) if m["data_abertura"] else ""),
            # Sentinela trocada por campo ODF na hora de montar o .odt:
            # frente/verso da folha fisica (1, 1v, 2, 2v...) — pedido Beatriz
            # 23/09/2026. Ver ri_odt.campo_folha_do_livro_odf.
            "ficha_numero": "#FICHA#",
            "livro_ficha": (
                re.sub(r"^(\d+)[-\s]*([A-Za-z]+)$", r"\1-\2", (m["livro"] or "2").strip())
                or "2"),
            # Quem imprimiu — pela sessao. Ver `app.py`: o atributo que estava
            # aqui nunca foi definido por ninguem, e a ficha saia sempre com o
            # nome da substituta.
            "usuario_impressao": app.extensions["usuario_nome"](),
            # Fecho da abertura da matricula, quando o teor nao traz um.
            # AS DUAS PARTES DO FECHO DA ABERTURA — a frase e o espaco de
            # assinar. Antes de 16/09/2026 isto chamava `fecho_do_ato` SEM o
            # nome, e por isso devolvia `""` em toda ficha da casa: a linha
            # existia no molde e nunca imprimiu nada.
            "abertura_fecho": fecho_da_abertura(
                m["cidade"] or s.get("ri_cidade", ""),
                m["uf"] or s.get("ri_uf", "MA"),
                m["data_abertura"], m["teor"],
                m["aberta_nome"] if "aberta_nome" in m.keys() else None,
                m["aberta_titulo"] if "aberta_titulo" in m.keys() else None,
                m["aberta_tratamento"] if "aberta_tratamento" in m.keys()
                else None,
                tipo_ficha=m["tipo_ficha"], lido=_fechos)["frase"],
            "abertura_assinatura": fecho_da_abertura(
                m["cidade"] or s.get("ri_cidade", ""),
                m["uf"] or s.get("ri_uf", "MA"),
                m["data_abertura"], m["teor"],
                m["aberta_nome"] if "aberta_nome" in m.keys() else None,
                m["aberta_titulo"] if "aberta_titulo" in m.keys() else None,
                m["aberta_tratamento"] if "aberta_tratamento" in m.keys()
                else None,
                tipo_ficha=m["tipo_ficha"], lido=_fechos)["assinatura"],
            # O CARIMBO DA ABERTURA TEM O MESMO DESENHO DO ATO — e desde
            # 16/09 os dois sao uma linha so, sem QR e sem link.
            "selo_abertura_odf": ("" if (m["tipo_ficha"] == "ACERVO"
                                         and not m.get("_teor_no_papel")) else  # HOTFIX-2026-10-15-01
                                    selo_convertido(
                                        etiqueta_da_abertura(),
                                        rotulo="SELO DE ABERTURA")),
            "protocolo_atual": (q1("""SELECT numero FROM ri_protocolos
                                      WHERE matricula_id=%s ORDER BY numero DESC, id DESC LIMIT 1""",
                                   (matricula_id,)) or {"numero": None})["numero"],
            "separador": SEPARADOR_DE_ATO_HTML,
            "uf_extenso": UF_EXTENSO.get((m["uf"] or "MA").upper(), m["uf"] or ""),
            "hoje": date.today().strftime("%d/%m/%Y"),
            "hoje_extenso": data_por_extenso(date.today()),
            "onus": _onus,
            "requerente": (request.form.get("requerente") or "").strip() if request.method == "POST" else "",
            "requerente_documento": (request.form.get("requerente_documento") or "").strip() if request.method == "POST" else "",
            "finalidade": (request.form.get("finalidade") or "").strip() if request.method == "POST" else "",
            "certidao_numero": "", "certidao_ano": date.today().year,
            "prenotacoes_abertas": _prenot_abertas,
            "clausula_prenotacoes_abertas": _clausula_prenot,
            "_imagens_selo": imagens_selo,
        }
        # A CADEIA DOMINIAL DESTA MATRÍCULA SÓ, E A VINTENÁRIA DE 20 ANOS — o
        # padrão que a conferência do modelo e a remontagem enxergam. São conta
        # em memória sobre os atos que já estão aqui; as matrículas de ORIGEM e
        # os anos escolhidos no balcão entram na emissão
        # (`_contexto_da_cadeia`), e não aqui: a origem chama este mesmo
        # contexto para cada matrícula antecedente, e montá-la aqui faria uma
        # chamar a outra sem fim.
        _cadeia_atual = RIDOM.cadeia_dominial(_ctx["atos"])
        _ctx.update({
            "cadeia_dominial": _cadeia_atual,
            "cadeia_matriculas": [{
                "numero": m["numero"], "papel": "atual",
                "registro_anterior": (m.get("registro_anterior") or "").strip(),
                "atos": _cadeia_atual}],
            "origens_nao_encontradas": [],
            **_janela_da_vintenaria(_ctx["atos"],
                                    RIDOM.ANOS_PADRAO_VINTENARIA),
        })
        return _ctx

    def _janela_da_vintenaria(atos_do_papel, anos) -> dict:
        """O recorte da vintenária, já com as datas na forma do papel."""
        _pack = RIDOM.conteudo_vintenaria(atos_do_papel, anos=anos,
                                          hoje=date.today())
        return {"anos_periodo": _pack["anos"],
                "desde_periodo": fmt_date(_pack["desde"]),
                "ate_periodo": fmt_date(_pack["ate"]),
                "dominio_periodo": _pack["dominio"],
                "onus_periodo": _pack["onus"]}

    def render_modelo(corpo: str, contexto: dict) -> str:
        """Renderiza o modelo do usuario em ambiente restrito.

        SandboxedEnvironment porque o corpo e editavel pela serventia: sem ele,
        um modelo poderia alcancar atributos internos do Python a partir do
        template. Erro de sintaxe volta como mensagem, nao como tela de erro.
        """
        from jinja2.sandbox import SandboxedEnvironment
        env = SandboxedEnvironment(autoescape=False)
        html = env.from_string(corpo).render(**contexto)
        # O AJUSTE DA CASA SAI SEM O QUE EXECUTA (revisão de segurança de
        # 22/10/2026, A7): o corpo vem de `ri_modelos` ou do catálogo, que o
        # papel USER edita, e o que sai daqui vai ao navegador (`|safe`) e ao
        # Chrome que conta as folhas. O texto de fábrica sai byte a byte como
        # saía; o QR do carimbo é PNG em data-URI, que o filtro deixa.
        return MODELOS.sem_o_que_executa(corpo, html)

    # A CONFERENCIA DO RI E CONTRA UMA MATRICULA DE VERDADE, e nao contra um
    # boneco — era o que esta tela ja fazia, e e melhor: o boneco pega erro de
    # forma (chave que nao existe, `for` sem fechar) e nao pega campo que so
    # aparece em ficha com ato, com onus, com parte. Por isso ela nao se perde
    # ao os modelos passarem para a tela geral: fica registrada aqui, e a tela
    # geral a chama para os papeis do RI.
    #
    # Sem matricula nenhuma no banco ela devolve None, e a tela geral cai no
    # boneco — que e o caso da instalacao nova.
    #
    # **O MOLDE DA CERTIDAO TEM UMA REGRA A MAIS, E ELA VEM ANTES DO RENDER** —
    # problema #75, 18/09/2026. O molde precisa carregar `{{ miolo_do_tipo }}`,
    # que e a emenda por onde o texto do tipo entra: sem ela a certidao sai
    # afirmando «cujo inteiro teor segue:» e nao reproduzindo nada, e renderizar
    # o molde sozinho nao acusaria isso — `miolo_do_tipo` indefinido vira texto
    # vazio, e o Jinja nao reclama do que esta faltando, so do que esta torto.
    def _conferir_com_matricula_real(corpo: str, chave: str = ""):
        if chave and (erro := MODELOS.conferir_marcadores(chave, corpo)):
            return erro
        exemplo = q1("SELECT id FROM ri_matriculas ORDER BY id LIMIT 1")
        if not exemplo:
            return None
        contexto = contexto_ficha(exemplo["id"], para_odt=False)
        if chave == "RI_CERTIDAO":
            # **CONFERE OS TRES MIOLOS, E NAO SO O CAMINHO QUE A FICHA ABRE.**
            # O molde tem dois desenhos (o do inteiro teor, que ja traz o
            # cabecalho da ficha, e o dos outros) e o tipo escolhido decide
            # qual sai. Renderizar sem `tipo_certidao` exercitaria metade do
            # molde e aprovaria a outra — e a metade nao exercitada e
            # justamente a do inteiro teor, que e a certidao que mais se emite.
            for _tipo, _chave_do_miolo in MIOLO_DA_CERTIDAO.items():
                with db.connect() as _c:
                    _miolo = MODELOS.corpo_de(_c, _chave_do_miolo)
                try:
                    render_modelo(corpo, contexto | {
                        "tipo_certidao": _tipo,
                        "tipo_certidao_nome": TIPOS_CERTIDAO.get(_tipo, _tipo),
                        # ja renderizado: e papel, e nao modelo
                        "miolo_do_tipo": render_modelo(_miolo, contexto)})
                except Exception as erro:                  # noqa: BLE001
                    return f"{_tipo}: {type(erro).__name__}: {erro}"
            return ""
        try:
            render_modelo(corpo, contexto)
        except Exception as erro:                          # noqa: BLE001
            return f"{type(erro).__name__}: {erro}"
        return ""

    app.extensions.setdefault("conferidores_de_modelo", {})
    # OS MIOLOS ENTRAM NA LISTA: eles sao papel do catalogo como o molde, e o
    # que os confere e a mesma matricula de verdade — um deles com um `for`
    # aberto estoura na emissao, com o cliente na frente.
    for _chave in ("RI_FICHA", "RI_CABECALHO", "RI_CERTIDAO", "RI_NOTA",
                   *MIOLO_DA_CERTIDAO.values()):
        app.extensions["conferidores_de_modelo"][_chave] = (
            lambda corpo, _k=_chave: _conferir_com_matricula_real(corpo, _k))

    # SO GET, porque ela nao grava mais nada: leva para a tela geral. Deixar o
    # POST declarado seria manter aberta uma porta de escrita que nenhuma tela
    # usa — e o varredor de `test_debitos_do_balcao` recusa isso, com razao.
    @app.route("/registro-imoveis/modelos")
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_modelos():
        # OS MODELOS PASSARAM PARA A TELA GERAL — relato #28 do oficial.
        #
        # Esta tela editava `ri_modelos`, que hoje o catalogo so le como
        # LEGADO: com um ajuste gravado na tela nova, o que se editasse aqui
        # nao teria efeito nenhum e ninguem saberia por que. **Duas telas para
        # a mesma coisa, uma delas perdendo em silencio, e o defeito que esta
        # casa mais paga** — e por isso ela leva para la em vez de coexistir.
        flash("Os modelos agora ficam num lugar só, com os das outras "
              "atribuições — inclusive os quatro do Registro de Imóveis.",
              "info")
        return redirect(url_for("modelos"))

    # A TELA ANTIGA FOI APAGADA, e nao desligada. Ela editava `ri_modelos`,
    # que o catalogo hoje so le como legado: guardada como funcao sem rota,
    # seria mais uma peca pronta esperando alguem religa-la sem saber por que
    # ela existia — o que ja aconteceu cinco vezes neste projeto.
    #
    # O que ela tinha de melhor NAO se perdeu: a conferencia contra matricula
    # de verdade esta logo acima, registrada para a tela geral usar.

    @app.route("/registro-imoveis/<int:matricula_id>/ficha.odt")
    @login_required
    def ri_ficha_odt(matricula_id):
        modelo_id = request.args.get("modelo")
        # O CATALOGO DA CASA DECIDE — relato #28. O ajuste que estivesse em
        # `ri_modelos` virou ajuste do catalogo na subida (LF06A), de modo que
        # quem tivesse um ajuste ali nao o perde.
        #
        # O `?modelo=<id>` CONTINUA VALENDO, e vem antes: e como a tela
        # «Modelos de documento» do RI experimentava um modelo especifico. Ele
        # e achado PELO CAMINHO NOVO (`modelo_legado_ri`): a linha velha fica
        # desligada depois da subida, e procura-la so ativa faria a ficha cair
        # calada no modelo da casa (revisao do LF06A). Numero que nao se acha
        # AVISA e nao imprime — ficha com outro modelo no lugar do pedido e
        # pior que ficha nenhuma. Sem `?modelo=`, manda o modelo da casa.
        modelo = None
        if modelo_id:
            with db.connect() as _c:
                modelo = MODELOS.modelo_legado_ri(_c, modelo_id)
            if not modelo:
                flash(f"O modelo n.º {modelo_id} não foi encontrado entre os "
                      "modelos do Registro de Imóveis, e a ficha não foi "
                      "impressa. Imprima sem escolher modelo para usar o da "
                      "casa (Administrativo → Modelos).", "warning")
                return redirect(url_for("ri_ficha", matricula_id=matricula_id))
            corpo_modelo = modelo["corpo"]
        else:
            with db.connect() as _c:
                corpo_modelo = MODELOS.corpo_de(_c, "RI_FICHA")

        contexto = contexto_ficha(matricula_id)
        try:
            html = render_modelo(corpo_modelo, contexto)
        except Exception as erro:
            flash(f"O modelo da ficha tem um erro: {SEGWEB.erro_do_modelo(erro, 'ri_ficha')}",
                  "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        # O teor ja vem convertido para ODF no contexto; o resto do modelo e HTML.
        corpo_odf = html_para_odf(html, fragmentos=contexto.get("_fragmentos"))
        with db.connect() as _c:
            _cab = MODELOS.corpo_de(_c, "RI_CABECALHO")
        try:
            cab_odf = html_para_odf(render_modelo(_cab, contexto),
                compacto=True)
        except Exception:
            cab_odf = ""
        imagens = dict(contexto.get("_imagens_selo") or {})
        # 22/09/2026 — QR de volta no carimbo dos atos (tela e papel).
        arquivo = gerar_odt(corpo_odf, cabecalho_odf=cab_odf, imagens=imagens)
        numero = contexto["m"]["numero"]
        audit("RI_FICHA_IMPRESSA", "RI_MATRICULA", matricula_id,
              {"numero": numero, "modelo": modelo["nome"] if modelo else "padrão"})
        # A ROTA TERMINA EM `.odt` — quem abre o link espera ODF, como no termo
        # do RCPN e na ficha do Livro 3. PDF continua com `?formato=pdf`.
        pedido = request.args.get("formato")
        if pedido is None:
            pedido = "odt"
        return IMPW.resposta_do_papel(
            arquivo, nome=f"matricula-{numero}", get_setting=db.get_setting,
            formato=pedido,
            voltar_para=url_for("ri_ficha", matricula_id=matricula_id))

    # --------------------------------------- livro de selos e emolumentos

    _MOEDA = r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})"

    def _num(bruto: str) -> float:
        try:
            return float(bruto.replace(".", "").replace(",", "."))
        except (ValueError, AttributeError):
            return 0.0

    def _valores(texto) -> dict:
        """Lê Total e Emolumentos do texto do selo, PELO RÓTULO.

        O selo do TJMA vem como 'Total R$ 18.903,80 Emol R$ 12.500,00'. Pegar
        simplesmente o último número daria o Emol por acidente da ordem, e
        inverteria a leitura em qualquer selo formatado diferente. Aqui cada
        valor é buscado pelo seu rótulo, e só na ausência deles se usa o
        primeiro número encontrado.
        """
        bruto = str(texto or "")
        total = re.search(r"total\D{0,12}" + _MOEDA, bruto, re.I)
        emol = re.search(r"emol\w*\D{0,12}" + _MOEDA, bruto, re.I)
        if not (total or emol):
            solto = re.search(_MOEDA, bruto)
            valor = _num(solto.group(1)) if solto else 0.0
            return {"total": valor, "emolumentos": valor, "rotulado": False}
        return {
            "total": _num(total.group(1)) if total else 0.0,
            "emolumentos": _num(emol.group(1)) if emol else 0.0,
            "rotulado": True,
        }

    def _valor(texto) -> float:
        """Valor de emolumentos, que é o que interessa ao livro."""
        v = _valores(texto)
        return v["emolumentos"] or v["total"]

    @app.route("/registro-imoveis/selos")
    @roles_required("ADMIN", "MANAGER", "AUDITOR")
    def ri_selos():
        """Livro de selos: reúne o que está espalhado em atos, certidões e
        prenotações. Não duplica o dado — lê de onde ele já mora."""
        hoje = date.today()
        inicio = (request.args.get("inicio") or "").strip() or hoje.replace(day=1).isoformat()
        fim = (request.args.get("fim") or "").strip() or hoje.isoformat()

        linhas = q("""
            SELECT 'Ato' origem, a.data_ato data, a.selo_texto selo, a.emolumentos valor,
                   m.numero||' — '||a.tipo||'-'||a.numero referencia, m.id matricula_id
            FROM ri_atos a JOIN ri_matriculas m ON m.id = a.matricula_id
            WHERE a.selo_texto IS NOT NULL AND a.data_ato BETWEEN %s AND %s
            UNION ALL
            SELECT 'Certidão', c.data_emissao, c.selo_texto, c.emolumentos,
                   'nº '||c.numero||'/'||c.ano, c.matricula_id
            FROM ri_certidoes c
            WHERE c.selo_texto IS NOT NULL AND c.data_emissao BETWEEN %s AND %s
            UNION ALL
            SELECT 'Prenotação', p.data_prenotacao, p.selo_prenotacao, NULL,
                   'protocolo '||p.numero, p.matricula_id
            FROM ri_protocolos p
            WHERE p.selo_prenotacao IS NOT NULL AND p.data_prenotacao BETWEEN %s AND %s
            ORDER BY data DESC, referencia""",
            (inicio, fim, inicio, fim, inicio, fim))

        total = 0.0
        total_geral = 0.0
        sem_rotulo = 0
        por_origem: dict[str, dict] = {}
        for l in linhas:
            v = _valores(l["valor"])
            total += v["emolumentos"] or v["total"]
            total_geral += v["total"] or v["emolumentos"]
            if l["valor"] and not v["rotulado"]:
                sem_rotulo += 1
            d = por_origem.setdefault(l["origem"], {"qtd": 0, "valor": 0.0})
            d["qtd"] += 1
            d["valor"] += v["emolumentos"] or v["total"]

        # Selo repetido é sinal de erro de digitação ou de reaproveitamento
        # indevido — em qualquer dos casos, alguém precisa olhar.
        vistos: dict[str, list] = {}
        for l in linhas:
            chave = (l["selo"] or "").strip().split()[0] if l["selo"] else ""
            if chave:
                vistos.setdefault(chave, []).append(l)
        repetidos = {k: v for k, v in vistos.items() if len(v) > 1}

        # O QUE FICOU SEM SELO, PELA RÉGUA DA CASA — e não por uma consulta
        # escrita aqui. 14/09/2026.
        #
        #   Esta tela tinha a sua própria contagem de «sem selo», contando duas
        #   tabelas (ato e certidão) e esquecendo a prenotação. Ao lado,
        #   `ato_selado.atos_sem_selo` existia para responder exatamente isso —
        #   e **nenhuma tela do sistema a chamava**, embora oito comentários
        #   espalhados por sete módulos prometam ao operador que «o ato sem
        #   selo aparece em `atos_sem_selo`».
        #
        #   Promessa que nada cumpre é o carimbo que mente aplicado a uma rede
        #   de segurança: quem lê para de procurar. Agora a lista é ela, e sai
        #   com os atos de verdade — não com um número.
        #
        #   E NÃO LEVA JANELA DE DATA. A pergunta «o que está sem selo» não é
        #   sobre o mês que se está olhando: ato de março sem selo continua sem
        #   selo em setembro, e some da tela justamente quem mais precisa
        #   aparecer.
        with db.connect() as _c:
            sem_selo_lista = {
                "Ato": AS.atos_sem_selo(_c, "ri_atos"),
                "Certidão": AS.atos_sem_selo(_c, "ri_certidoes"),
                "Prenotação": AS.atos_sem_selo(_c, "ri_protocolos"),
            }
        sem_selo = {"atos": len(sem_selo_lista["Ato"]),
                    "certidoes": len(sem_selo_lista["Certidão"]),
                    "prenotacoes": len(sem_selo_lista["Prenotação"])}

        return render_template("ri_selos.html", linhas=linhas, total=total,
                               por_origem=por_origem, repetidos=repetidos,
                               sem_selo=sem_selo, sem_selo_lista=sem_selo_lista,
                               inicio=inicio, fim=fim,
                               valores=_valores, total_geral=total_geral,
                               sem_rotulo=sem_rotulo)

    # ------------------------------------------------- nota devolutiva

    @app.route("/registro-imoveis/protocolo/<int:protocolo_id>/nota", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_nota_devolutiva(protocolo_id):
        """Qualificacao negativa do titulo, vinculada ao protocolo.

        Fica no protocolo e nao na matricula porque e a prenotacao que corre
        enquanto o interessado cumpre as exigencias. Reingressando no prazo, o
        titulo aproveita o mesmo numero de ordem (Codigo TJMA, art. 44).
        """
        p = q1("SELECT * FROM ri_protocolos WHERE id=%s", (protocolo_id,))
        if not p:
            abort(404)
        notas = q("""SELECT * FROM ri_notas_devolutivas WHERE protocolo_id=%s
                     ORDER BY numero DESC, id DESC""", (protocolo_id,))

        if request.method == "GET":
            with db.connect() as _c:
                documentos = RDOC.documentos_de(_c, RDOC.ENTIDADE_RI, protocolo_id)
            return render_template("ri_nota.html", p=p, notas=notas,
                                   hoje=date.today().isoformat(),
                                   anexos_da_nota=lambda numero: RND.anexos_da_nota(
                                       documentos, numero),
                                   exigencias_da=RND.exigencias_da,
                                   por_que_nao_emite=RND.por_que_nao_emite(p))

        # O ARQUIVO DA NOTA PODE VIR JUNTO (25/10/2026): a nota desta casa é redigida
        # em Word e assinada; com o arquivo, as exigências digitadas ficam opcionais.
        arquivos = [f for f in request.files.getlist("arquivo_nota") if f and f.filename]
        return _emitir_nota_devolutiva(p, arquivos=arquivos)

    def _emitir_nota_devolutiva(p, *, arquivos, descricao=None):
        """A nota devolutiva, pela tela da nota ou pelo anexo do protocolo — uma porta só.

        A recusa vem antes de guardar o arquivo: arquivo guardado como «nota» de um
        protocolo que não pode recebê-la seria um papel sem lugar.
        """
        exigencias = [e.strip() for e in
                      (request.form.get("exigencias") or "").splitlines() if e.strip()]
        voltar = redirect(url_for("ri_nota_devolutiva", protocolo_id=p["id"]))
        motivo = RND.por_que_nao_emite(p)
        if motivo:
            flash(motivo, "danger")
            return voltar
        if not exigencias and not arquivos:
            flash("Informe ao menos uma exigência (uma por linha) ou anexe o arquivo da nota "
                  "devolutiva.", "danger")
            return voltar
        anexos = _anexar_ao_protocolo(p, arquivos, descricao)[0] if arquivos else []
        try:
            with db.transaction() as con:
                feito = RND.emitir(
                    con, p, exigencias=exigencias,
                    fundamentacao=request.form.get("fundamentacao"),
                    data_nota=(request.form.get("data_nota") or "").strip() or db.now()[:10],
                    quem=(app.extensions["usuario_nome"]() or "").strip() or None,
                    usuario_id=app.extensions["usuario_id"](), agora=db.now(),
                    anexos=anexos)
                # «Nota de exigência» no Acompanhamento do ONR, com o texto da nota
                # (o manual manda a nota de devolução nesse campo) — na transação dela.
                ACOMP.anotar_nota_de_exigencia(con, feito["nota_id"], agora=db.now())
                # A NOTA QUE NASCEU DA QUALIFICAÇÃO ASSISTIDA (26/10/2026): o
                # rascunho da IA guarda qual nota a rota de sempre emitiu com as
                # exigências dele — na mesma transação, para a ligação não ficar
                # pela metade. Sem o campo (a nota escrita à mão), não faz nada.
                import ri_qualificacao_ia as QIA
                ligada_a_ia = QIA.ligar_a_nota(con, request.form.get("qualificacao_ia_id"),
                                               p["id"], feito["nota_id"])
        except RND.NotaError as erro:
            flash(str(erro), "danger")
            return voltar
        audit("RI_NOTA_DEVOLUTIVA", "RI_NOTA", feito["nota_id"],
              {"protocolo": p["numero"], "numero": feito["numero"],
               "exigencias": feito["exigencias"], "anexos": feito["anexos"],
               "qualificacao_ia": (int(request.form["qualificacao_ia_id"])
                                   if ligada_a_ia else None)})
        if feito["anexos"]:
            flash(f"Nota devolutiva nº {feito['numero']} cadastrada com o arquivo anexado. "
                  f"O protocolo passou a devolvido; a prenotação continua correndo.", "success")
            return redirect(url_for("ri_nota_devolutiva", protocolo_id=p["id"]))
        flash(f"Nota devolutiva nº {feito['numero']} emitida com {feito['exigencias']} "
              f"exigência(s). O protocolo passou a devolvido; a prenotação continua "
              f"correndo.", "success")
        return redirect(url_for("ri_nota_odt", nota_id=feito["nota_id"]))

    @app.route("/registro-imoveis/notas/<int:nota_id>.odt")
    @login_required
    def ri_nota_odt(nota_id):
        n = q1("SELECT * FROM ri_notas_devolutivas WHERE id=%s", (nota_id,))
        if not n:
            abort(404)
        p = q1("SELECT * FROM ri_protocolos WHERE id=%s", (n["protocolo_id"],))
        s = db.get_settings()
        try:
            lista = json.loads(n["exigencias"])
        except (TypeError, ValueError):
            lista = [n["exigencias"]]

        exig_html = "".join(
            f"<p><b>{i}.</b> {e}</p>" for i, e in enumerate(lista, 1)) or (
            # Nota cadastrada pelo ARQUIVO (25/10/2026): as exigências estão no papel
            # assinado, anexado ao protocolo — dizer isso, e não imprimir lista vazia.
            "<p>As exigências constam da nota devolutiva assinada, anexada ao "
            "protocolo.</p>")
        contexto = {
            "nota": dict(n) | {"prazo_ate": fmt_date(n["prazo_ate"])},
            "protocolo": dict(p) | {"data_prenotacao": fmt_date(p["data_prenotacao"])},
            "exigencias_odf": html_para_odf(exig_html),
            "serventia": dados_serventia(db.get_settings) | {
                "nome": s.get("unit_name") or dados_serventia(db.get_settings)["unit_name"],
                "cns": s.get("ri_cns", ""),
                "cidade": s.get("ri_cidade", ""),
                "uf": s.get("ri_uf", "MA"),
                "registrador": s.get("ri_registrador", ""),
                "substituta": s.get("ri_substituta", ""),
            },
            "hoje_extenso": data_por_extenso(date.today()),
        }
        with db.connect() as _c:
            _corpo = MODELOS.corpo_de(_c, "RI_NOTA")
        try:
            html = render_modelo(_corpo, contexto)
        except Exception as erro:
            flash(f"O modelo da nota tem um erro: {SEGWEB.erro_do_modelo(erro, 'ri_nota')}",
                  "danger")
            return redirect(url_for("ri_protocolo"))

        arquivo = gerar_odt(html_para_odf(html))
        audit("RI_NOTA_IMPRESSA", "RI_NOTA", nota_id, {"protocolo": p["numero"]})
        return IMPW.resposta_do_papel(
            arquivo, nome=f'nota-devolutiva-{p["numero"]}-{n["numero"]}',
            get_setting=db.get_setting,
            # A TELA DA NOTA E A DO PROTOCOLO — `ri_nota` nao existe como
            # rota, e este `url_for` so seria chamado no caminho de falha:
            # o erro apareceria meses depois, e justamente quando o balcao ja
            # estivesse com um problema. Apanhado conferindo o `url_map`.
            voltar_para=url_for("ri_nota_devolutiva",
                                protocolo_id=n["protocolo_id"]))

    @app.route("/registro-imoveis/notas/<int:nota_id>/reingresso", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_reingresso(nota_id):
        """Registra o reingresso do titulo com as exigencias cumpridas.

        Dentro da vigencia da prenotacao, o titulo volta ao MESMO protocolo -
        nao se abre outro. Fora do prazo, e preciso protocolo novo.
        """
        n = q1("SELECT * FROM ri_notas_devolutivas WHERE id=%s", (nota_id,))
        if not n:
            abort(404)
        p = q1("SELECT * FROM ri_protocolos WHERE id=%s", (n["protocolo_id"],))
        arquivos = [f for f in request.files.getlist("documento") if f and f.filename]
        return _registrar_reingresso(n, p, arquivos=arquivos)

    def _registrar_reingresso(n, p, *, arquivos, descricao=None):
        """O reingresso, pela tela da nota ou pelo anexo «cumprimento de exigência»."""
        hoje = db.now()[:10]
        quando = (request.form.get("data_reingresso") or "").strip() or hoje
        observacao = request.form.get("observacao")
        papel = app.extensions["usuario_papel"]()
        if n["situacao"] != "ABERTA":
            flash(f"A nota nº {n['numero']} não está aguardando cumprimento.", "danger")
            return redirect(url_for("ri_nota_devolutiva", protocolo_id=p["id"]))
        # A DATA SE CONFERE ANTES DE GUARDAR O ARQUIVO (revisão de segurança de
        # 26/10/2026): ela decide a prioridade, e a recusa não pode deixar o
        # documento do interessado gravado sem reingresso. A regra mora em
        # `RND.conferir_data_do_reingresso`, e `RND.reingresso` a repete.
        try:
            quando = RND.conferir_data_do_reingresso(n, p, quando=quando, hoje=hoje,
                                                     papel=papel, observacao=observacao)
        except RND.NotaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_nota_devolutiva", protocolo_id=p["id"]))
        anexos = _anexar_ao_protocolo(p, arquivos, descricao)[0] if arquivos else []
        try:
            with db.transaction() as con:
                dentro_do_prazo = RND.reingresso(
                    con, n, p, quando=quando, observacao=observacao, hoje=hoje,
                    papel=papel, anexos=anexos)
                if dentro_do_prazo:
                    # «Título com reingresso» no ONR — só o reingresso no prazo, que
                    # é o único que volta à mesma prenotação.
                    ACOMP.anotar_reingresso(con, n["id"], agora=db.now())
        except RND.NotaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_nota_devolutiva", protocolo_id=p["id"]))
        nota_id = n["id"]

        audit("RI_REINGRESSO", "RI_NOTA", nota_id,
              {"protocolo": p["numero"], "data": quando, "no_prazo": dentro_do_prazo,
               "registrado_em": hoje, "retroativo": quando < hoje, "papel": papel,
               "anexos": anexos})
        if dentro_do_prazo:
            flash(f"Reingresso registrado no protocolo {p['numero']}, dentro da vigência "
                  f"da prenotação. O título aproveita o mesmo número de ordem.", "success")
        else:
            flash(f"Reingresso em {quando}, mas a prenotação venceu em "
                  f"{fmt_date(p['data_limite'])}. Será preciso abrir novo protocolo, "
                  f"com os emolumentos correspondentes.", "danger")
        return redirect(url_for("ri_nota_devolutiva", protocolo_id=p["id"]))

    # ------------------------------------------------- exportação ao ONR

    @app.route("/registro-imoveis/onr", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER")
    def ri_onr():
        """Gera os arquivos do ONR no formato levantado dos envios anteriores.

        Gera para conferência e envio manual. O sistema não transmite nada:
        transmissão automática exigiria credencial da serventia junto ao ONR.
        """
        hoje = date.today()
        inicio = (request.values.get("inicio") or "").strip() or hoje.replace(day=1).isoformat()
        fim = (request.values.get("fim") or "").strip() or hoje.isoformat()
        cns = db.get_setting("ri_cns", "")

        # Indicador Pessoal: um vínculo por pessoa/matrícula/ato no período.
        #
        # **`DTVENDA` LEVA A MESMA DATA — conserto de 04/09/2026.** Esta tela
        # mandava o campo VAZIO desde que nasceu, e o ensaio contra a produção
        # achou ao construir a carga do Next Cloud SAS: nos 19 arquivos que
        # esta casa mandou ao ONR, `DTVENDA` é igual a `DTREGAVERB` em
        # **10.781 de 10.781** — sem uma exceção.
        #
        # `ri_onr.gerar_indicador_pessoal` sempre aceitou `data_venda`; era
        # quem a chama que não a passava. **A peça estava pronta e ninguém a
        # usava**, pela enésima vez neste projeto — e aqui de um jeito novo:
        # não faltava o chamador, faltava um argumento dele.
        vinculos = q("""SELECT p.nome, p.documento_numero documento, m.numero matricula,
                               COALESCE(a.natureza_titulo,
                                        CASE WHEN a.tipo='R' THEN 'MATRICULA' ELSE 'OUTRO' END,
                                        'MATRICULA') tipo_ato,
                               COALESCE(a.data_ato, m.data_abertura) data_ato,
                               COALESCE(a.data_ato, m.data_abertura) data_venda
                        FROM ri_partes p
                        JOIN ri_matriculas m ON m.id = p.matricula_id
                        LEFT JOIN ri_atos a ON a.id = p.ato_id
                        WHERE COALESCE(a.data_ato, m.data_abertura) BETWEEN %s AND %s
                        ORDER BY COALESCE(a.data_ato, m.data_abertura), m.numero, p.nome""",
                     (inicio, fim))

        # Indicador Real: matrículas abertas no período.
        matriculas = q("""SELECT * FROM ri_matriculas
                          WHERE data_abertura BETWEEN %s AND %s
                          ORDER BY coalesce(substring(numero FROM '^[0-9]+')::bigint, 0), id""",
                       (inicio, fim))

        if request.method == "POST":
            tipo = (request.form.get("tipo") or "PESSOAL").upper()
            try:
                d1 = date.fromisoformat(inicio)
                d2 = date.fromisoformat(fim)
            except ValueError:
                flash("Período inválido.", "danger")
                return redirect(url_for("ri_onr"))

            if tipo == "PESSOAL":
                conteudo = gerar_indicador_pessoal([dict(v) for v in vinculos], cns)
                mime = "application/xml"
            else:
                conteudo = gerar_indicador_real([dict(m) for m in matriculas], cns)
                mime = "application/json"

            arquivo = nome_arquivo(tipo, d1, d2)
            audit("RI_ONR_EXPORTADO", "RI_ONR", None,
                  {"tipo": tipo, "inicio": inicio, "fim": fim,
                   "registros": len(vinculos) if tipo == "PESSOAL" else len(matriculas),
                   "arquivo": arquivo})
            return Response(conteudo.encode("utf-8"), mimetype=mime,
                            headers={"Content-Disposition":
                                     f'attachment; filename="{arquivo}"'})

        # Conferência antes de gerar: o que sairia com documento desconhecido.
        sem_doc = sum(1 for v in vinculos
                      if len(so_digitos(v["documento"])) not in (11, 14))
        return render_template("ri_onr.html", inicio=inicio, fim=fim, cns=cns,
                               vinculos=vinculos, matriculas=matriculas,
                               sem_doc=sem_doc, TIPOS=TIPO_IMOVEL_ONR)

    # ------------------------------- a carga do Next Cloud SAS (modalidade b)
    #
    # **O OFICIAL ESCOLHEU A MODALIDADE (b) em 04/09/2026.** A (a) — web
    # service proprio — exige servidor em data center no territorio nacional,
    # link dedicado, VPN e 24x7x365; o servidor desta casa e a maquina do
    # balcao.
    #
    # **E O INDICADOR REAL NAO PASSA POR AQUI.** Medido nos seis documentos do
    # ONR: «indicador real» aparece zero vezes em todos. Ele continua indo pela
    # API, que e outra tela — e a tela diz isso, porque quem lesse «Next Cloud
    # SAS ligado» concluiria que o RI inteiro esta integrado.

    @app.route("/registro-imoveis/onr/next-cloud-sas")
    @roles_required("ADMIN", "MANAGER")
    def ri_onr_next_cloud():
        """A conferencia da carga completa. SO LE."""
        raiz = raiz_imagens()
        with db.connect() as con:
            quadro = OCG.prontidao(con, raiz)
            faltando = OCG.matriculas_sem_imagem(con, raiz, limite=50)                 if quadro["erro_do_disco"] is None else []
            # O QUADRO QUE SE COPIA NO FORMULARIO DE ADESAO. Ele pede numeros
            # que o sistema sabe e o oficial teria de contar a mao.
            formulario = OCG.para_o_formulario(
                con, raiz,
                conta_google=db.get_setting("onr_conta_google", ""),
                cns=db.get_setting("ri_cns", ""))
        return render_template("ri_onr_next_cloud.html", q=quadro,
                               faltando=faltando, raiz=str(raiz),
                               formulario=formulario,
                               cns=db.get_setting("ri_cns", ""))

    @app.route("/registro-imoveis/onr/next-cloud-sas/indicador-pessoal",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def ri_onr_next_cloud_ips():
        """Gera o XML da CARGA COMPLETA do Indicador Pessoal.

        **Nao transmite.** Quem sobe e o programa IPS que o ONR instala aqui;
        um segundo caminho gravando o mesmo fato divergiria do primeiro.
        """
        cns = db.get_setting("ri_cns", "")
        with db.connect() as con:
            conferencia = OCG.conferir_indicador_pessoal(con)
            conteudo = OCG.gerar_indicador_pessoal(con, cns)
        arquivo = f"IndicadorPessoal_CARGA_COMPLETA_{db.now()[:10]}.XML"
        audit("RI_ONR_CARGA_IPS", "RI_ONR", None,
              {"vinculos": conferencia["vinculos"],
               "sem_documento": conferencia["sem_documento"],
               "arquivo": arquivo})
        return Response(conteudo.encode("utf-8"), mimetype="application/xml",
                        headers={"Content-Disposition":
                                 f'attachment; filename="{arquivo}"'})

    # --------------------------------- indicador real e pessoal (Livros 4 e 5)

    @app.route("/registro-imoveis/indicador-real")
    @login_required
    def ri_indicador_real():
        """Livro 4 - Indicador Real (Lei 6.015/73, art. 173, IV).

        Localiza o imovel a partir da descricao: denominacao, endereco, bairro
        ou trecho do memorial. E o caminho de quem chega com o imovel, nao com
        o numero da matricula.
        """
        busca = (request.args.get("busca") or "").strip()
        bairro = (request.args.get("bairro") or "").strip()
        tipo = (request.args.get("tipo") or "").strip()
        # LD13: «abc» no endereço era 500, e a página de 18 dígitos estoura o OFFSET.
        pagina = max(1, numero_digitado(request.args.get("pagina"),
                                        maximo=PAGINA_MAIS_ALTA) or 1)

        onde, params = ["1=1"], []
        if busca:
            # A REGUA DO NUMERO E A MESMA DA LISTA, e nao uma parecida: quem
            # procura o imovel pela descricao pode digitar o numero da ficha, e
            # «contem» ali traria as mesmas 782 fichas do «1». A descricao (o
            # `imovel_norm`) continua por trecho, que e o proposito da tela.
            digitos = _numero_digitado(busca)
            condicoes = ["m.imovel_norm ILIKE %s"]
            params.append(f"%{normalizar_busca(busca)}%")
            if digitos:
                condicoes += ["m.numero = %s", "m.cnm = %s"]
                params += [digitos, _cnm_da_casa(digitos)]
            onde.append("(" + " OR ".join(condicoes) + ")")
        if bairro:
            onde.append("m.bairro = %s")
            params.append(bairro)
        if tipo in ("R", "U"):
            onde.append("m.rural_urbano = %s")
            params.append(tipo)
        filtro = " AND ".join(onde)

        total = q1(f"SELECT COUNT(*) c FROM ri_matriculas m WHERE {filtro}", params)["c"]
        # MESMO CONSERTO DA LISTA DE MATRICULAS, e pelo mesmo motivo: ordenar
        # por `CAST(m.numero AS INTEGER)` obriga a carregar as 1.982 fichas
        # inteiras — com os 31,8 MB de teor — para escolher cinquenta. Aqui a
        # subconsulta ordena e pagina sobre colunas curtas, e so entao as 50
        # linhas cheias sao buscadas.
        #   `NULLS FIRST`: o SQLite punha a ficha sem bairro ou sem logradouro
        #   no comeco; o PostgreSQL, sem dizer, a mandaria para o fim.
        rows = q(f"""SELECT m.*,
                       (SELECT COUNT(*) FROM ri_partes p
                        WHERE p.matricula_id=m.id AND p.proprietario_ativo=1) n_prop
                     FROM ri_matriculas m
                     WHERE m.id IN (
                         SELECT id FROM ri_matriculas m WHERE {filtro}
                          ORDER BY m.bairro NULLS FIRST, m.logradouro NULLS FIRST,
                                   coalesce(substring(m.numero FROM '^[0-9]+')::bigint, 0), m.id
                          LIMIT %s OFFSET %s)
                     ORDER BY m.bairro NULLS FIRST, m.logradouro NULLS FIRST,
                              coalesce(substring(m.numero FROM '^[0-9]+')::bigint, 0), m.id""",
                 params + [POR_PAGINA, (pagina - 1) * POR_PAGINA])
        bairros = q("""SELECT bairro, COUNT(*) c FROM ri_matriculas
                       WHERE bairro IS NOT NULL AND TRIM(bairro)<>''
                       GROUP BY bairro ORDER BY bairro""")
        with db.connect() as con_l:
            lancamentos = RILANC.listar(con_l, 4, busca=busca, limite=40)
        return render_template("ri_indicador_real.html", rows=rows, total=total,
                               busca=busca, bairro=bairro, tipo=tipo, bairros=bairros,
                               pagina=pagina, paginas=max(1, math.ceil(total / POR_PAGINA)),
                               lancamentos=lancamentos)

    @app.route("/registro-imoveis/indicador-pessoal")
    @login_required
    def ri_indicador_pessoal():
        """Livro 5 - Indicador Pessoal (Lei 6.015/73, art. 173, V).

        Agrupa por pessoa e lista todas as matriculas em que ela aparece, com o
        papel em cada uma. E o caminho inverso do indicador real.
        """
        busca = (request.args.get("busca") or "").strip()
        so_proprietarios = request.args.get("proprietarios") == "1"
        pessoas: list[dict] = []
        total = 0

        if busca:
            # O NOME POR TRECHO E PELO NORMALIZADO; O DOCUMENTO EXATO — a mesma
            # regua das outras duas telas de busca do RI (ver `_numero_digitado`).
            # Quem digita o CPF inteiro, com ou sem pontuacao, acha; quem digita
            # quatro digitos soltos deixa de achar o homonimo de outro CPF.
            onde = ["(p.nome_norm ILIKE %s OR p.documento_numero = %s)"]
            params = [f"%{normalizar_busca(busca)}%", so_digitos(busca) or busca]
            if so_proprietarios:
                onde.append("p.proprietario_ativo = 1")
            filtro = " AND ".join(onde)

            # Agrupa por documento quando existe; por nome normalizado quando nao.
            # O acervo tem 71% de partes sem documento, entao agrupar so por
            # documento perderia a maioria.
            grupos = q(f"""SELECT COALESCE(NULLIF(p.documento_numero,''), p.nome_norm) chave,
                                  MAX(p.nome) nome, MAX(p.documento_tipo) doc_tipo,
                                  MAX(p.documento_numero) doc, MAX(p.documento_valido) valido,
                                  MAX(p.qualificacao) qualificacao,
                                  COUNT(DISTINCT p.matricula_id) n_matriculas
                           FROM ri_partes p WHERE {filtro}
                           GROUP BY chave ORDER BY n_matriculas DESC, nome, chave LIMIT 60""",
                       params)
            total = len(grupos)
            for g in grupos:
                # As candidatas da positiva (25/10/2026): só para quem é
                # proprietário atual; o escrevente marca uma a uma.
                g["candidatas"] = []
                vinculos = q("""SELECT m.id, m.numero, m.livro_norm, m.logradouro,
                                       m.bairro, m.encerrada,
                                       MAX(p.proprietario_ativo) ativo, MAX(p.papel) papel
                                FROM ri_partes p JOIN ri_matriculas m ON m.id=p.matricula_id
                                WHERE COALESCE(NULLIF(p.documento_numero,''), p.nome_norm)=%s
                                GROUP BY m.id
                                ORDER BY coalesce(substring(m.numero FROM '^[0-9]+')::bigint, 0), m.id""",
                             (g["chave"],))
                if any(v["ativo"] and not v["encerrada"] for v in vinculos):
                    with db.connect() as _c_pos:
                        g["candidatas"] = RINEG.candidatas_da_positiva(_c_pos, g["chave"])
                pessoas.append({"pessoa": g, "matriculas": vinculos})

        with db.connect() as con_l:
            lancamentos = RILANC.listar(con_l, 5, busca=busca, limite=40)
        return render_template("ri_indicador_pessoal.html", pessoas=pessoas,
                               busca=busca, total=total, so_proprietarios=so_proprietarios,
                               lancamentos=lancamentos)

    # ------------------------------------------- busca em texto livre no acervo
    #
    # Pedido do oficial, 26/10/2026: procurar no TEOR de todas as fichas — e
    # nao so no numero, no endereco e nas partes cadastradas, que e o que a
    # lista e os dois indicadores olham. O desenho, a escolha do indice e o que
    # se mediu estao em `ri_busca_acervo`.
    #
    # QUEM USA: TODO USUARIO HUMANO LOGADO — decisao do oficial em 26/10/2026,
    # «todos podem usar». ADMIN, MANAGER, USER e tambem o AUDITOR: ler o
    # acervo e o papel dele, e a busca so le (a primeira versao deste PR a
    # restringia a quem pratica ato). O ROBO CONTINUA VEDADO, pela lista de
    # `selo_robo.ROTAS_VEDADAS_AO_ROBO` (revisao de seguranca de 26/10), que
    # nao mudou. As outras duas guardas, na forma da busca do devedor do
    # Protesto (`protesto_devedores_buscar`), ficam:
    #   · O TERMO NAO VAI NO ENDERECO: a busca e POST, como a do devedor — CPF
    #     em `?busca=` fica no historico do navegador e no log de quem estiver
    #     no meio;
    #   · TODA BUSCA VAI A AUDITORIA, com quem, quando, o tipo do termo, quantas
    #     fichas e quais (as cinquenta primeiras) — e, NO LUGAR DO TERMO, a
    #     impressao dele (`BUSCA.impressao_da_busca`), agora COM A CHAVE do
    #     servidor: o sha256 puro de um CPF se desfaz percorrendo os CPFs
    #     possiveis, e entao o CPF estaria no rastro. O CPF/CNPJ procurado vai
    #     MASCARADO (so os dois ultimos digitos, a regua da auditoria da casa),
    #     para quem audita ver que se procurou um documento sem ver qual.
    #     Gravar o termo em claro e decisao do oficial.
    QUEM_LE_O_ACERVO = ("ADMIN", "MANAGER", "USER", "AUDITOR")

    @app.route("/registro-imoveis/busca-no-acervo", methods=["GET", "POST"])
    @roles_required(*QUEM_LE_O_ACERVO)
    def ri_busca_no_acervo():
        """Procura no teor das fichas e dos atos. SO LE (grava so a auditoria)."""
        termo = (request.form.get("termo") or "").strip() if request.method == "POST" else ""
        modo = (request.form.get("modo") or "FRASE").strip().upper()
        resultado, erro = None, None
        if request.method == "POST":
            try:
                with db.connect() as con:
                    resultado = BUSCA.buscar(con, termo, modo=modo)
            except BUSCA.BuscaError as e:
                erro = str(e)
            if resultado is not None:
                audit("RI_BUSCA_NO_ACERVO", "RI_MATRICULA", None, {
                    "tipos": [p.tipo for p in resultado.termos],
                    "modo": resultado.modo,
                    "impressao": BUSCA.impressao_da_busca(termo, chave=app.secret_key),
                    "documentos_mascarados": [
                        BUSCA.documento_mascarado(p.termo)
                        for p in resultado.termos if p.tipo == "DOCUMENTO"],
                    "fichas": resultado.total,
                    "ids": [f["id"] for f in resultado.fichas][:50],
                    "agente": "pessoa — tela de busca no acervo do RI",
                    "a_mando_de": app.extensions["usuario_nome"](),
                })
        return render_template("ri_busca_acervo.html", termo=termo, modo=modo,
                               resultado=resultado, erro=erro,
                               limite=BUSCA.LIMITE_DE_FICHAS)

    # ------------------------------------- a situacao juridica, num clique
    #
    # Pedido do oficial, 26/10/2026. O que se junta e de onde vem esta em
    # `ri_situacao_juridica`. QUEM USA: todo usuario humano logado («todos
    # podem usar», 26/10) — os mesmos quatro papeis da busca, declarados na
    # rota; e o resumo nao mostra nada que a ficha nao mostre, so junta. A
    # consulta fica no rastro, como a da ficha (`RI_FICHA_CONSULTADA`). A
    # lista do robo (`selo_robo`) nao foi tocada: hoje ela veda a busca e nao
    # o resumo, como nao veda a ficha.
    #   NAO E CERTIDAO, e a tela diz isso no alto; e NAO GRAVA nada alem da
    #   linha de auditoria.

    @app.route("/registro-imoveis/<int:matricula_id>/situacao-juridica")
    @login_required
    @roles_required(*QUEM_LE_O_ACERVO)
    def ri_situacao_juridica(matricula_id):
        base_data, base_n = cnib_referencia()
        with db.connect() as con:
            s = SITJ.montar(con, matricula_id, hoje=date.today(),
                            cnib_base=base_data, cnib_ordens=base_n)
        if s is None:
            abort(404)
        audit("RI_SITUACAO_JURIDICA_CONSULTADA", "RI_MATRICULA", matricula_id,
              {"numero": s["m"]["numero"], "onus": len(s["onus"]),
               "onus_no_teor": len(s["teor"]["onus"]),
               "cnib": len(s["cnib"]["ordens"]),
               "agente": "pessoa — tela do resumo da situação jurídica do RI",
               "a_mando_de": app.extensions["usuario_nome"]()})
        return render_template("ri_situacao_juridica.html", s=s,
                               agora=db.now(), quem=app.extensions["usuario_nome"]())


    # ------------------------------------------- certidao negativa de imovel
    #
    # Pedido Beatriz 25/09/2026. NAO mora na ficha da matricula (#75): a
    # pergunta e «consta algo em nome desta pessoa / sobre este imovel?», e
    # a resposta negativa so vale quando a busca dos indicadores devolve
    # zero. O POST refaz a busca — nao confia no GET (mesmo desenho da
    # negativa de Protesto).

    def _voltar_negativa(modo, busca, bairro="", tipo_ru="", so_prop=False):
        if modo == "IMOVEL":
            return redirect(url_for(
                "ri_indicador_real", busca=busca or None,
                bairro=bairro or None, tipo=tipo_ru or None))
        kw = {"busca": busca or None}
        if so_prop:
            kw["proprietarios"] = "1"
        return redirect(url_for("ri_indicador_pessoal", **kw))

    @app.route("/registro-imoveis/certidao-negativa", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_emitir_certidao_negativa():
        """Emite a certidao negativa (busca sem achado) — ou, por pessoa, a
        POSITIVA com a relacao dos imoveis atuais (25/10/2026). ESCREVE."""
        modo = (request.form.get("modo") or "PESSOA").strip().upper()
        if modo not in ("PESSOA", "IMOVEL"):
            flash("Modo de busca invalido.", "danger")
            return redirect(url_for("ri_indicador_pessoal"))
        # A POSITIVA POR PESSOA — 25/10/2026, o oficial: «relação dos imóveis
        # atuais». É a mesma rota de propósito: o número, o hash e o selo
        # (16.24.1) são os da negativa, e duas rotas dariam duas réguas.
        positiva = (request.form.get("resultado") or "").strip().upper() == "POSITIVA"
        if positiva and modo != "PESSOA":
            flash("A certidão positiva é só da busca por pessoa.", "danger")
            return redirect(url_for("ri_indicador_real"))
        pessoa_chave = (request.form.get("pessoa_chave") or "").strip()
        tipo_cert = RINEG.TIPO_POSITIVA if positiva else RINEG.TIPO
        nome_cert = RINEG.NOME_DO_TIPO_POSITIVA if positiva else RINEG.NOME_DO_TIPO
        busca = (request.form.get("busca") or "").strip()
        bairro = (request.form.get("bairro") or "").strip()
        tipo_ru = (request.form.get("tipo_ru") or "").strip().upper()
        so_prop = request.form.get("proprietarios") == "1"
        requerente = (request.form.get("requerente") or "").strip()
        requerente_documento = so_digitos(
            request.form.get("requerente_documento")) or None
        finalidade = (request.form.get("finalidade") or "").strip() or None
        protocolo = (request.form.get("protocolo") or "").strip() or None
        isento, motivo_isencao = ler_isencao_do_form(request.form)
        motivo_isencao = motivo_isencao or ""
        if isento and not motivo_isencao:
            flash(
                "Certidao gratuita precisa do motivo escrito — e ele que a "
                "conferencia le no selo. Escreva o motivo ou desmarque "
                "Selo gratuito / isento.",
                "danger")
            return _voltar_negativa(modo, busca, bairro, tipo_ru, so_prop)
        if not isento:
            motivo_isencao = None

        # O ITEM DA BUSCA (15/10/2026) — aqui `busca` é o TERMO pesquisado,
        # e por isso o item tem outro nome. A negativa não tem ato de onde
        # contar o tempo: a tela abre em «escolha», e vazio se recusa.
        try:
            item_busca = _busca_da_certidao_do_ri(request.form)
        except BU.BuscaError as erro:
            flash(str(erro), "danger")
            return _voltar_negativa(modo, busca, bairro, tipo_ru, so_prop)
        # O PROTOCOLO QUE PAGA O SELO (22/10/2026), antes de numerar.
        recusa = _atender_o_protocolo_escolhido(request.form)
        if recusa:
            flash(recusa, "danger")
            return _voltar_negativa(modo, busca, bairro, tipo_ru, so_prop)

        hoje = date.today()
        agora = datetime.now()
        grupo = None
        imoveis: list[dict] = []
        try:
            with db.connect() as con:
                if positiva:
                    # A busca da positiva é a do Indicador Pessoal inteira (não
                    # só proprietários): a pessoa escolhida tem de estar nela.
                    grupo = RINEG.conferir_positiva(
                        RINEG.buscar_por_pessoa(con, busca), pessoa_chave)
                    candidatas = RINEG.candidatas_da_positiva(con, grupo["chave"])
                    if not candidatas:
                        raise RINEG.CertidaoNegativaError(
                            "A pessoa escolhida não é proprietária atual de nenhuma "
                            "matrícula aberta. Não há o que certificar como positiva.")
                    # SÓ AS MARCADAS (o oficial, 25/10/2026): o escrevente
                    # confere cada matrícula — homônimo e pessoa partida.
                    imoveis = RINEG.conferir_marcadas(
                        candidatas, request.form.getlist("matricula_marcada"))
                else:
                    if modo == "PESSOA":
                        achados = RINEG.buscar_por_pessoa(
                            con, busca, so_proprietarios=so_prop)
                    else:
                        achados = RINEG.buscar_por_imovel(
                            con, busca, bairro=bairro, tipo=tipo_ru)
                    RINEG.conferir_negativa(achados)
        except RINEG.CertidaoNegativaError as erro:
            flash(str(erro), "danger")
            return _voltar_negativa(modo, busca, bairro, tipo_ru, so_prop)

        # O TEXTO DO CRITERIO MORA NA BASE (LF06B): com `con`, o ajuste da casa.
        import ri_frases
        with db.connect() as _c_frases:
            ids = RINEG.montar_identificacao(busca, modo=modo, con=_c_frases)
            if modo == "IMOVEL" and bairro and not ids.get("imovel_busca"):
                ids["imovel_busca"] = bairro
                ids["criterio_rotulo"] = ri_frases.frase(
                    "RI_NEGATIVA_CRITERIO_BAIRRO", _c_frases, bairro=bairro)
        if positiva:
            # Quem a certidão nomeia é a pessoa ESCOLHIDA, e não o que se digitou.
            ids["pesquisado"] = grupo.get("nome") or ids.get("pesquisado") or busca
            ids["pesquisado_documento"] = grupo.get("doc") or ""

        _sv0 = dados_serventia(db.get_settings)
        sv = _sv0 | {
            "nome": _sv0.get("unit_name") or "",
            "cns": _sv0.get("ri_cns") or "",
            "cidade": _sv0.get("ri_cidade") or "",
            "uf": _sv0.get("ri_uf") or "MA",
            "registrador": _sv0.get("serventia_titular") or "",
            "substituta": _sv0.get("ri_substituta") or "",
            "titulo_registrador": "Tabelião Registrador",
            "titulo_substituta": "Tabeliã Registradora Substituta",
        }
        lavrou_nome = (
            (app.extensions["usuario_nome"]() or "").strip()
            or (sv.get("substituta") or sv.get("ri_substituta")
                or sv.get("registrador") or "")
        )
        lavrou_funcao = (
            (app.extensions["usuario_funcao"]() or "").strip()
            or ("Tabeliã Registradora Substituta"
                if (sv.get("substituta") or sv.get("ri_substituta"))
                else "Tabelião Registrador")
        )
        hoje_ext = data_por_extenso(hoje)

        contexto = {
            "serventia": sv,
            "requerente": requerente or None,
            "requerente_documento": requerente_documento,
            "finalidade": finalidade,
            "protocolo": protocolo,
            "hoje_extenso": hoje_ext,
            "hora_emissao": agora.strftime("%H:%M"),
            "lavrou_nome": lavrou_nome,
            "lavrou_funcao": lavrou_funcao,
            **ids,
            "imoveis": [{"numero": i["numero"], "livro": i.get("livro_norm") or "",
                         "descricao": RINEG.descricao_curta(i)} for i in imoveis],
        }
        chave_modelo = RINEG.CHAVE_MODELO_POSITIVA if positiva else RINEG.CHAVE_MODELO
        try:
            with db.connect() as _c:
                texto_modelo = MODELOS.corpo_de(_c, chave_modelo)
            corpo = render_modelo(
                texto_modelo or MODELOS.padrao_de(chave_modelo), contexto)
        except Exception as erro:
            flash("O modelo da certidao negativa tem um erro: "
                  f"{SEGWEB.erro_do_modelo(erro, 'ri_certidao_negativa')}",
                  "danger")
            return _voltar_negativa(modo, busca, bairro, tipo_ru, so_prop)
        corpo = RINEG.limpar_corpo(corpo)

        validade = RINEG.validade_ate(hoje)
        with db.transaction() as con:
            bd = banco(con)
            bd.travar("ri_certidoes.numero")
            ultimo = bd.valor(
                "SELECT MAX(numero) AS n FROM ri_certidoes WHERE ano=%s",
                (hoje.year,))
            numero = int((ultimo or 0)) + 1
            criterio = ids.get("criterio_rotulo") or busca
            h = RINEG.hash_do_corpo(
                numero, hoje.year, corpo, hoje.isoformat(), criterio, tipo_cert)
            certidao_id = bd.escrever(
                """INSERT INTO ri_certidoes
                   (numero, ano, tipo, matricula_id, matricula_numero,
                    requerente, requerente_documento, finalidade,
                    data_emissao, validade_ate, corpo, corpo_formato,
                    protocolo, selo_texto, emolumentos, hash_certidao,
                    origem, emitida_em, emitida_por, emitida_por_nome,
                    emitida_por_funcao, isento, motivo_isencao, fonte_corpo)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, 'html', %s,%s,%s,%s,
                           'MANUAL', %s, %s, %s, %s, %s, %s, 'TEXTO')
                   RETURNING id""",
                (numero, hoje.year, tipo_cert, None, None,
                 requerente or None, requerente_documento, finalidade,
                 hoje.isoformat(), validade, corpo, protocolo, None, None,
                 h, db.now(), app.extensions["usuario_id"](),
                 (app.extensions["usuario_nome"]() or "").strip() or None,
                 (app.extensions["usuario_funcao"]() or "").strip() or None,
                 1 if isento else 0, motivo_isencao),
            )[0]["id"]
            certidao_id = int(certidao_id)

        audit("RI_CERTIDAO_POSITIVA_EMITIDA" if positiva else "RI_CERTIDAO_NEGATIVA_EMITIDA",
              "RI_CERTIDAO", certidao_id,
              {"numero": numero, "ano": hoje.year, "tipo": tipo_cert,
               "modo": modo, "busca": busca, "hash": h,
               **({"pessoa_chave": grupo["chave"],
                   "matriculas": [i["numero"] for i in imoveis],
                   "conferidas_por": (app.extensions["usuario_nome"]() or "").strip()}
                  if positiva else {"achados": 0}),
               **({"item_busca": item_busca} if item_busca else {})})

        # Selo automatico — sem bypass «mesmo se o selo falhar».
        recado_do_selo = ""
        folhas_contadas_msg = ""
        aguardando = False
        try:
            folhas = CFOLHAS.decidir_folhas_antes_de_emitir(
                fonte="TEXTO", caminho_digi=None, paginas_digi=None,
                corpo_html=corpo, folhas_informadas=None,
                get_setting=db.get_setting)
            folhas_contadas_msg = (
                f" {folhas} folha(s) contabilizada(s) pelo sistema."
                if folhas else "")
            pedido = _pedir_os_selos_da_certidao_do_ri(
                certidao_id=certidao_id, tipo=tipo_cert, folhas=folhas,
                requerente=requerente,
                requerente_documento=requerente_documento, matricula="",
                isento=isento, motivo_isencao=motivo_isencao)
            recado_do_selo = _recado_dos_selos_da_certidao(pedido)
            aguardando = pedido["aguardando"]
        except (AS.AtoError, ValueError) as erro:
            recado_do_selo = f" SEM SELO: {erro}"

        motivo_selo = _motivo_da_falha_do_selo(recado_do_selo)
        if motivo_selo and aguardando:
            # AGUARDANDO COBERTURA NÃO É SELO RECUSADO (22/10/2026). O selo
            # nem foi pedido: falta ligar o protocolo e o pagamento. Cancelar
            # aqui queimava um número por tentativa (83 e 84/2026 na produção);
            # a certidão fica de pé, sem poder ser impressa, até o selo sair.
            audit("RI_CERTIDAO_AGUARDANDO_COBERTURA", "RI_CERTIDAO",
                  certidao_id, {"numero": numero, "ano": hoje.year,
                                "tipo": tipo_cert, "motivo": motivo_selo})
            flash(f"{nome_cert} n. {numero}/{hoje.year} gravada, "
                  f"mas SEM SELO: {motivo_selo} Ela não pode ser impressa "
                  "até o selo sair. Ligue o protocolo pago e clique em "
                  "«Selar» na lista de certidões.", "warning")
            return redirect(url_for("ri_certidoes", busca=str(numero)))
        if motivo_selo:
            quando = db.now()
            quem = app.extensions["usuario_nome"]()
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE ri_certidoes
                          SET cancelada=1, motivo_cancelamento=%s,
                              cancelada_em=%s, cancelada_por=%s
                        WHERE id=%s""",
                    (f"Selo nao emitido: {motivo_selo}", quando, quem,
                     certidao_id))
            audit("RI_CERTIDAO_NAO_EMITIDA_SELO_FALHOU", "RI_CERTIDAO",
                  certidao_id, {"numero": numero, "ano": hoje.year,
                                "tipo": tipo_cert, "hash": h,
                                "motivo": motivo_selo})
            flash(
                "Certidao NAO emitida: o selo nao saiu. "
                f"Motivo: {motivo_selo}. Corrija o problema do "
                "selo e tente de novo.",
                "danger")
            return _voltar_negativa(modo, busca, bairro, tipo_ru, so_prop)

        # A BUSCA SAI DEPOIS DA CERTIDÃO JÁ SELADA (15/10/2026); a pessoa
        # pesquisada é quem vai nas partes, como na certidão.
        recado_do_selo += _selar_a_busca_da_certidao_do_ri(
            certidao_id=certidao_id, busca=item_busca, nome=requerente,
            documento=requerente_documento, matricula="",
            isento=isento, motivo_isencao=motivo_isencao)

        flash(
            f"{nome_cert} n. {numero}/{hoje.year} emitida. "
            f"Valida ate {validade}. O teor foi congelado nesta data."
            f"{folhas_contadas_msg}{recado_do_selo}",
            "success")
        return redirect(url_for("ri_certidao_odt", certidao_id=certidao_id))

    # ------------------------------------------- digitalizacao oficial

    def _tem_digitalizacao(matricula_id: int) -> bool:
        """Há arquivo oficial NO DISCO para esta matrícula? Só LÊ.

        Pergunta pelo arquivo, e não só pela coluna: caminho gravado apontando
        para arquivo que sumiu faria a certidão prometer uma reprodução que
        ninguém consegue montar.
        """
        with db.connect() as con:
            digi = RDIGI.atual_da_matricula(con, matricula_id)
        return bool(digi and digi.get("digi_path")
                    and Path(digi["digi_path"]).is_file())

    @app.route("/registro-imoveis/<int:matricula_id>/digitalizacao",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_upload_digitalizacao(matricula_id):
        """Atualiza o arquivo oficial de digitalizacao da matricula.

        Pedido de 16/09/2026: o balcao envia a varredura atualizada; o
        arquivo fica pronto para a certidao de inteiro teor por reproducao
        e marcado como pendente de envio ao ONR (sem transmitir ainda).
        """
        m = q1("SELECT id, numero FROM ri_matriculas WHERE id=%s", (matricula_id,))
        if not m:
            abort(404)
        arquivo = request.files.get("arquivo")
        try:
            info = RDIGI.gravar_upload(
                db, matricula_id=matricula_id, arquivo=arquivo,
                usuario=app.extensions["usuario_nome"]())
        except ValueError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))
        audit("RI_DIGITALIZACAO_ATUALIZADA", "RI_MATRICULA", matricula_id,
              {"numero": m["numero"], "nome": info["nome"],
               "sha256": info["sha256"], "onr_pendente": True})
        # A COPIA EM TIFF PARA O ONR NASCE AGORA, numa linha a parte — 10/10/2026
        # (gestor_cargas_ri, «NA HORA DO ENVIO»). Nao espera e nao estoura: o
        # que falhar fica na ficha, e a rodada das 07:30 refaz.
        import gestor_cargas_ri
        gestor_cargas_ri.converter_em_segundo_plano(db, matricula_id)
        flash(
            f"Digitalizacao oficial atualizada ({info['nome']}). "
            "A copia para o ONR esta sendo preparada — a ficha mostra quando ficar pronta.",
            "success")
        return redirect(url_for("ri_ficha", matricula_id=matricula_id))

    @app.route("/registro-imoveis/<int:matricula_id>/digitalizacao/arquivo")
    @login_required
    def ri_baixar_digitalizacao(matricula_id):
        with db.connect() as con:
            digi = RDIGI.atual_da_matricula(con, matricula_id)
        if not digi or not digi.get("digi_path"):
            abort(404)
        caminho = Path(digi["digi_path"])
        if not caminho.is_file():
            abort(404)
        # A mesma rota serve ao botao de baixar e a tela de conferencia. Antes
        # ela respondia sempre como anexo generico; por isso um PDF oficial
        # existente nunca podia ser mostrado dentro de «Conferir com a
        # digitalizacao». O parametro so muda a apresentacao HTTP — nao altera
        # nem copia o arquivo.
        visualizar = request.args.get("visualizar") == "1"
        nome = (digi.get("digi_nome") or caminho.name)
        nome = str(nome).replace('"', "").replace("\r", "").replace("\n", "")
        tipo = mimetypes.guess_type(nome)[0] or "application/octet-stream"
        return Response(
            caminho.read_bytes(),
            mimetype=tipo,
            headers={
                "Content-Disposition":
                f'{"inline" if visualizar else "attachment"}; filename="{nome}"',
                "X-Content-Type-Options": "nosniff",
            })

    @app.route("/registro-imoveis/<int:matricula_id>/digitalizacao/miniatura")
    @login_required
    def ri_miniatura_digitalizacao(matricula_id):
        """Primeira pagina do arquivo oficial para a ficha inicial. So le."""
        with db.connect() as con:
            digi = RDIGI.atual_da_matricula(con, matricula_id)
        if not digi or not digi.get("digi_path"):
            abort(404)
        caminho = Path(digi["digi_path"])
        if not caminho.is_file():
            abort(404)
        try:
            largura = int(request.args.get("w") or 420)
        except ValueError:
            largura = 420
        try:
            png = RDIGI.miniatura_png(caminho, largura=largura)
        except ValueError as erro:
            app.logger.warning(
                "Nao consegui montar miniatura da digitalizacao da matricula %s: %s",
                matricula_id, erro)
            abort(404)
        return Response(
            png, mimetype="image/png",
            headers={"Cache-Control": "private, max-age=3600",
                     "X-Content-Type-Options": "nosniff"})

    # ------------------------------------------- fichas digitalizadas

    def raiz_imagens() -> Path:
        configurada = (db.get_setting("ri_imagens_raiz", "") or "").strip()
        if configurada:
            return Path(configurada)
        return PDC.do_eoficio("ONR_IMAGENS", banco=db.db_path,
                              archive_root=db.get_setting("archive_root", ""))

    @app.route("/registro-imoveis/imagens/resolver", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER")
    def ri_resolver_imagens():
        """Liga cada registro de imagem ao arquivo no disco.

        O E-Oficio guarda o id_path, mas ele nao corresponde ao nome da pasta
        (1 aponta para 00000000, 2 para 00000003 ...). Como os nomes de arquivo
        sao unicos entre as pastas, indexamos por nome, que e estavel.
        """
        raiz = raiz_imagens()
        if request.method == "GET":
            n = q1("""SELECT COUNT(*) total,
                   COALESCE(SUM(CASE WHEN caminho IS NOT NULL THEN 1 ELSE 0 END),0)::bigint resolvidas,
                   COALESCE(SUM(CASE WHEN caminho_interno IS NOT NULL THEN 1 ELSE 0 END),0)::bigint copiadas,
                   COALESCE(SUM(bytes),0)::bigint bytes FROM ri_imagens""")
            # O diagnóstico só roda quando ainda há ficha por resolver: varrer
            # a pasta inteira à toa deixaria a tela lenta depois de pronta.
            diag = None
            if n["total"] and n["resolvidas"] < n["total"]:
                nomes = [r["nome_arquivo"] for r in
                         q("""SELECT nome_arquivo FROM ri_imagens
                              WHERE nome_arquivo IS NOT NULL AND caminho IS NULL
                              ORDER BY id LIMIT 500""")]
                diag = RIMG.diagnostico(nomes, raiz)
            return render_template("ri_imagens.html", raiz=str(raiz),
                                   existe=RIMG.e_pasta(raiz),
                                   total=n["total"], resolvidas=n["resolvidas"],
                                   copiadas=n["copiadas"], diag=diag,
                                   pillow=RIMG.pillow_disponivel(),
                                   megabytes=round((n["bytes"] or 0) / 1048576, 1))

        nova = (request.form.get("raiz") or "").strip()
        if nova:
            db.set_settings({"ri_imagens_raiz": nova})
            raiz = Path(nova)
        if not RIMG.e_pasta(raiz):
            flash(f"A pasta {raiz} não existe ou o servidor não consegue abri-la. "
                  f"Lembre que ele roda como SYSTEM: caminho local funciona, "
                  f"unidade mapeada não.", "danger")
            return redirect(url_for("ri_resolver_imagens"))

        # O casamento mora em `ri_imagens`, com teste. O E-Ofício grava o nome
        # como `00003967.0001`, onde o `.0001` é o NÚMERO DA PÁGINA e não
        # extensão; no disco o arquivo é `00003967.0001.TIF`. Casar por
        # igualdade exata derrubava as 3.689 de uma vez, em silêncio.
        try:
            indice, arquivos, exemplos_disco = RIMG.indexar(raiz)
        except OSError as erro:
            flash(f"Não consegui ler {raiz}: {erro}", "danger")
            return redirect(url_for("ri_resolver_imagens"))

        achadas = perdidas = 0
        exemplos_perdidos: list[str] = []
        with db.transaction() as con:
            bd = banco(con)
            for linha in bd.ler(
                    "SELECT id, nome_arquivo FROM ri_imagens WHERE nome_arquivo IS NOT NULL "
                    "ORDER BY id"):
                caminho = RIMG.achar(linha["nome_arquivo"], indice)
                if caminho:
                    bd.escrever("UPDATE ri_imagens SET caminho=%s WHERE id=%s",
                                (caminho, linha["id"]))
                    achadas += 1
                else:
                    perdidas += 1
                    if len(exemplos_perdidos) < 5:
                        exemplos_perdidos.append(linha["nome_arquivo"])
        audit("RI_IMAGENS_RESOLVIDAS", "RI_IMAGEM", None,
              {"raiz": str(raiz), "achadas": achadas, "perdidas": perdidas,
               "arquivos_no_disco": arquivos})
        if perdidas and not achadas:
            # Nenhuma casou: quase sempre é pasta errada. Mostrar os dois lados
            # resolve em cinco segundos o que a mensagem antiga não explicava.
            flash(f"Nenhuma das {perdidas} imagens foi localizada em {raiz}, "
                  f"onde varri {arquivos} arquivo(s). "
                  f"No banco os nomes são como: {', '.join(exemplos_perdidos)}. "
                  + (f"No disco são como: {', '.join(exemplos_disco)}. "
                     "Se não se parecem, a pasta é outra."
                     if exemplos_disco else "A pasta está vazia."), "danger")
        else:
            flash(f"{achadas} imagens localizadas de {achadas + perdidas}. "
                  f"{arquivos} arquivos varridos em {raiz}."
                  + (f" Não achei, por exemplo: {', '.join(exemplos_perdidos)}."
                     if perdidas else ""),
                  "success" if not perdidas else "warning")
        return redirect(url_for("ri_resolver_imagens"))

    # ------------------- as paginas que o banco NAO conhece
    #
    # **A TELA DE CIMA SO OLHA O QUE JA ESTA EM `ri_imagens`**, e por isso
    # pagina que a exportacao do E-Oficio nao listou nunca aparecia em tela
    # nenhuma. Medido em 04/09/2026: **6.508 paginas no disco fora do banco**,
    # e **1.203 matriculas com a ficha incompleta** — a de numero 5 tem 60
    # paginas no disco e 6 no sistema.
    #
    #   Quem abre aquela ficha no balcao le um decimo dela, e nada avisa.

    @app.route("/registro-imoveis/imagens/do-disco")
    @roles_required("ADMIN", "MANAGER")
    def ri_fichas_do_disco():
        """O que ha no disco e o banco nao conhece. SO LE."""
        raiz = raiz_imagens()
        try:
            with db.connect() as con:
                achado = RFD.conferir(con, raiz)
                painel = RFD.quadro(con)
                faltando = RFD.incompletas(con, raiz)
                escolher = RFD.candidatas(con, raiz)
                # A FICHA NOVA QUE NINGUEM DIGITALIZOU — para o numero parar
                # de crescer enquanto o mutirao do acervo espera decisao.
                atrasadas = OCG.sem_digitalizacao(
                    con, raiz, hoje=db.now()[:10],
                    dias=int(db.get_setting("ri_dias_para_digitalizar",
                                            OCG.DIAS_PARA_DIGITALIZAR_PADRAO)))
        except RFD.FichaDoDiscoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_resolver_imagens"))
        return render_template("ri_fichas_do_disco.html", a=achado,
                               quadro=painel, faltando=faltando,
                               escolher=escolher, atrasadas=atrasadas,
                               dias_para_digitalizar=int(db.get_setting(
                                   "ri_dias_para_digitalizar",
                                   OCG.DIAS_PARA_DIGITALIZAR_PADRAO)),
                               raiz=str(raiz))

    @app.route("/registro-imoveis/imagens/do-disco/trazer", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def ri_fichas_do_disco_trazer():
        """Traz as paginas que faltam. **GRAVA e copia para dentro.**"""
        raiz = raiz_imagens()
        try:
            limite = int(request.form.get("limite") or 0)
        except ValueError:
            limite = 0
        try:
            r = RFD.trazer(db, raiz,
                           quem=app.extensions["usuario_nome"](),
                           limite=limite)
        except RFD.FichaDoDiscoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_fichas_do_disco"))
        audit("RI_FICHAS_DO_DISCO", "RI_IMAGEM", None,
              {"trazidas": r["trazidas"], "falhas": len(r["falhas"]),
               "raiz": str(raiz)})
        recado = (f"{r['trazidas']} página(s) trazida(s) do disco e copiada(s) "
                  f"para dentro do sistema.")
        if r["falhas"]:
            # **A FALHA APARECE, e nao vira zero.** Arquivo que nao copiou e
            # ficha que continua incompleta, e o balcao precisa saber qual.
            recado += (f" {len(r['falhas'])} não deu para copiar: "
                       + ", ".join(x["nome"] for x in r["falhas"][:3]) + ".")
        flash(recado, "success" if not r["falhas"] else "warning")
        return redirect(url_for("ri_fichas_do_disco"))

    @app.route("/registro-imoveis/imagens/do-disco/escolher",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def ri_fichas_do_disco_escolher():
        """Liga uma pagina ambigua a matricula que o oficial escolheu."""
        raiz = raiz_imagens()
        try:
            r = RFD.resolver(db, request.form.get("nome") or "",
                             int(request.form.get("matricula_id") or 0),
                             raiz=raiz,
                             quem=app.extensions["usuario_nome"]())
        except (RFD.FichaDoDiscoError, ValueError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_fichas_do_disco"))
        audit("RI_FICHA_AMBIGUA_RESOLVIDA", "RI_IMAGEM", r["matricula_id"],
              {"nome": r["nome"], "pagina": r["pagina"]})
        flash(f"A página {r['nome']} foi ligada à matrícula escolhida.",
              "success")
        return redirect(url_for("ri_fichas_do_disco"))

    def pasta_imagens_internas() -> Path:
        """Onde o sistema guarda a sua propria copia.

        Fica dentro da pasta de arquivos que o backup ja varre, entao a copia
        entra no backup sem mexer na rotina existente.
        """
        raiz = Path(db.get_setting("archive_root", "").strip()
                    or (Path(db.db_path).parent / "arquivos"))
        destino = raiz / "ri" / "fichas"
        destino.mkdir(parents=True, exist_ok=True)
        return destino

    @app.route("/registro-imoveis/imagens/copiar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def ri_copiar_imagens():
        """Traz as digitalizacoes para dentro do acervo do sistema.

        Enquanto os arquivos moram na pasta do E-Oficio, desligar aquele
        sistema levaria as fichas junto - e o backup daqui nao as alcanca.
        """
        import hashlib
        import shutil

        destino = pasta_imagens_internas()
        copiadas = ja_tinha = faltando = 0
        erros: list[str] = []
        total_bytes = 0

        linhas = q("""SELECT id, matricula_id, nome_arquivo, caminho, caminho_interno
                      FROM ri_imagens WHERE nome_arquivo IS NOT NULL ORDER BY id""")
        with db.transaction() as con:
            bd = banco(con)
            for linha in linhas:
                relativo = linha["caminho_interno"]
                if relativo and (destino.parent.parent / relativo).is_file():
                    ja_tinha += 1
                    continue
                origem = Path(linha["caminho"]) if linha["caminho"] else None
                if not origem or not origem.is_file():
                    faltando += 1
                    continue
                # O NOME QUE JÁ ESTAVA GRAVADO também se confere: a recusa no
                # renomear vale do conserto em diante (LS02), e um nome com
                # pasta dentro levaria a cópia para fora do acervo.
                if not nome_simples(linha["nome_arquivo"]):
                    erros.append(f"{linha['nome_arquivo']}: o nome tem pasta "
                                 "dentro, e a cópia sairia do acervo")
                    continue
                sub = destino / str(linha["matricula_id"] or "sem_matricula")
                sub.mkdir(parents=True, exist_ok=True)
                alvo = sub / linha["nome_arquivo"]
                try:
                    shutil.copy2(origem, alvo)
                    dados = alvo.read_bytes()
                    bd.escrever(
                        """UPDATE ri_imagens SET caminho_interno=%s, sha256=%s, bytes=%s,
                           copiado_em=%s WHERE id=%s""",
                        (str(alvo.relative_to(destino.parent.parent)),
                         hashlib.sha256(dados).hexdigest(), len(dados),
                         db.now(), linha["id"]),
                    )
                    copiadas += 1
                    total_bytes += len(dados)
                except OSError as erro:
                    erros.append(f"{linha['nome_arquivo']}: {erro}")

        audit("RI_IMAGENS_INTERNALIZADAS", "RI_IMAGEM", None,
              {"copiadas": copiadas, "ja_existiam": ja_tinha, "sem_origem": faltando,
               "megabytes": round(total_bytes / 1048576, 1), "destino": str(destino)})
        recado = (f"{copiadas} imagens copiadas para o acervo do sistema "
                  f"({total_bytes / 1048576:.1f} MB). {ja_tinha} já estavam. ")
        if faltando:
            recado += f"{faltando} sem arquivo de origem. "
        if erros:
            recado += f"{len(erros)} falharam: {erros[0]}"
        flash(recado, "warning" if (faltando or erros) else "success")
        return redirect(url_for("ri_resolver_imagens"))

    def _normalizar_a_ordem(con, matricula_id: int) -> None:
        """Deixa as paginas em 1..N, sem buracos. ESCREVE, dentro da transacao.

        Sem isto a ordem vira 1, 2, 5, 9 depois de duas exclusoes, e a
        «pagina 7» da tela deixa de ser a setima folha do livro de papel — que
        e a unica coisa que esse numero quer dizer.
        """
        bd = banco(con)
        linhas = bd.ler(
            """SELECT id FROM ri_imagens WHERE matricula_id=%s
                ORDER BY COALESCE(ordem, 999999), id""", (matricula_id,))
        for posicao, linha in enumerate(linhas, start=1):
            bd.escrever("UPDATE ri_imagens SET ordem=%s WHERE id=%s",
                        (posicao, linha["id"]))

    @app.route("/registro-imoveis/<int:matricula_id>/imagens", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def ri_organizar_imagens(matricula_id):
        """Edita, exclui e reordena as digitalizacoes desta matricula.

            «preciso de poderes para, caso necessario, editar e excluir e
             alterar ordem das digitalizacoes nas matriculas»
              — o oficial, 17/09/2026

        **E DO OFICIAL E DO GERENTE**: lavrar ato e do balcao; mexer na ordem
        do que foi digitalizado do livro e de quem responde pela guarda do
        acervo. Mesma regua do encerramento da matricula.

        **EXCLUIR TIRA DA FICHA E NAO APAGA O ARQUIVO** — ver o cabecalho de
        `scratchpad/organizar_as_digitalizacoes.py` e o aviso na tela.
        """
        m = q1("SELECT id, numero FROM ri_matriculas WHERE id=%s", (matricula_id,))
        if not m:
            abort(404)
        acao = (request.form.get("acao") or "").strip().lower()
        # LD13: «abc» era 500; o que não é número não acha imagem nenhuma.
        img_id = numero_digitado(request.form.get("imagem_id") or 0)
        img = q1("SELECT * FROM ri_imagens WHERE id=%s AND matricula_id=%s",
                 (img_id, matricula_id))
        if not img:
            # NAO SE MEXE NA IMAGEM DE OUTRA FICHA, e a conferencia e aqui: o
            # numero vem do formulario, e um numero trocado na barra de
            # enderecos tiraria a pagina de outra matricula — e ninguem
            # desconfia de uma pagina que some de uma ficha que ele nao abriu.
            flash("Esta digitalização não é desta matrícula.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        nome = img["nome_arquivo"] or "(sem nome)"
        if acao == "excluir":
            with db.transaction() as con:
                bd = banco(con)
                bd.travar("ri_imagens.ordem")
                bd.escrever("DELETE FROM ri_imagens WHERE id=%s", (img_id,))
                _normalizar_a_ordem(bd, matricula_id)
            audit("RI_IMAGEM_TIRADA_DA_FICHA", "RI_MATRICULA", matricula_id,
                  {"numero": m["numero"], "imagem_id": img_id,
                   "nome_arquivo": nome, "ordem_que_tinha": img["ordem"],
                   "arquivo_apagado": False})
            flash(f"A página {img['ordem']} ({nome}) saiu desta ficha. "
                  "O arquivo continua no disco — para trazê-la de volta, use "
                  "«Fichas digitalizadas».", "success")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        if acao == "renomear":
            novo = (request.form.get("nome_arquivo") or "").strip()
            if not novo:
                flash("O nome não pode ficar vazio.", "danger")
                return redirect(url_for("ri_ficha", matricula_id=matricula_id))
            # O NOME É SÓ DE ARQUIVO (LS02, 19/10/2026). Ele vai depois para
            # `ri_copiar_imagens`, que copia para `pasta / nome` como SYSTEM:
            # com `..\` ou `C:\` no nome, a cópia saía do acervo e podia
            # sobrescrever o próprio sistema.
            if not nome_simples(novo):
                flash("O nome é só o do arquivo, sem pasta: tire as barras, "
                      "os dois-pontos e o «..».", "danger")
                return redirect(url_for("ri_ficha", matricula_id=matricula_id))
            with db.transaction() as con:
                banco(con).escrever("UPDATE ri_imagens SET nome_arquivo=%s WHERE id=%s",
                                    (novo, img_id))
            audit("RI_IMAGEM_RENOMEADA", "RI_MATRICULA", matricula_id,
                  {"numero": m["numero"], "imagem_id": img_id,
                   "antes": nome, "depois": novo})
            flash(f"A página {img['ordem']} passou a chamar-se «{novo}».",
                  "success")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        if acao in ("subir", "descer", "ordem"):
            if acao == "ordem":
                # LD13: o «²» e os 5.000 dígitos passavam pelo `isdigit()` e
                # caíam no `int()`.
                destino = numero_digitado(request.form.get("ordem"))
                if destino is None or destino < 1:
                    flash("A página tem de ser um número a partir de 1.",
                          "danger")
                    return redirect(url_for("ri_ficha",
                                            matricula_id=matricula_id))
            else:
                destino = int(img["ordem"] or 1) + (-1 if acao == "subir" else 1)
            quantas = q1("SELECT COUNT(*) n FROM ri_imagens WHERE matricula_id=%s",
                         (matricula_id,))["n"]
            destino = max(1, min(destino, quantas))
            if destino == int(img["ordem"] or 0):
                return redirect(url_for("ri_ficha", matricula_id=matricula_id))
            with db.transaction() as con:
                # A MEIA CASA E O TRUQUE: pondo a pagina em «destino - 0,5» ela
                # cai imediatamente antes de quem ocupa o lugar, e a
                # normalizacao seguinte resolve o resto. Trocar duas a duas
                # exigiria um caso para cada sentido, e e onde se erra.
                #   No PostgreSQL `ordem` e inteiro de verdade e o 0,5 se
                #   arredondaria: a meia casa se faz dobrando as ordens da
                #   ficha, e a pagina vai para 2*destino -1 ou +1.
                #   A trava faz o que o BEGIN IMMEDIATE fazia: duas reordenacoes
                #   da mesma ficha nao se misturam na renumeracao.
                bd = banco(con)
                bd.travar("ri_imagens.ordem")
                bd.escrever("UPDATE ri_imagens SET ordem=ordem*2 WHERE matricula_id=%s",
                            (matricula_id,))
                bd.escrever("UPDATE ri_imagens SET ordem=%s WHERE id=%s",
                            (2 * destino - 1 if destino < int(img["ordem"] or 0)
                             else 2 * destino + 1, img_id))
                _normalizar_a_ordem(bd, matricula_id)
            audit("RI_IMAGEM_REORDENADA", "RI_MATRICULA", matricula_id,
                  {"numero": m["numero"], "imagem_id": img_id,
                   "nome_arquivo": nome, "de": img["ordem"], "para": destino})
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        flash("Não entendi o que fazer com a digitalização.", "danger")
        return redirect(url_for("ri_ficha", matricula_id=matricula_id))

    @app.route("/registro-imoveis/imagem/<int:imagem_id>")
    @login_required
    def ri_imagem(imagem_id):
        """Serve a ficha digitalizada.

        Os arquivos sao TIFF Grupo 4, que navegador nenhum exibe. Convertemos
        para PNG na hora. Sem Pillow instalado, entregamos o TIFF original para
        download - melhor baixar do que nao ver.
        """
        img = q1("SELECT * FROM ri_imagens WHERE id=%s", (imagem_id,))
        if not img:
            abort(404)
        # A copia do proprio sistema tem precedencia: a origem pertence ao
        # E-Oficio e pode desaparecer quando ele for desligado.
        caminho = None
        if img["caminho_interno"]:
            interno = pasta_imagens_internas().parent.parent / img["caminho_interno"]
            if interno.is_file():
                caminho = interno
        if caminho is None and img["caminho"] and Path(img["caminho"]).is_file():
            caminho = Path(img["caminho"])
        if caminho is None:
            abort(404)

        # LD13: «abc», «²» e 5.000 dígitos no endereço eram 500.
        pagina = numero_digitado(request.args.get("p"), maximo=PAGINA_MAIS_ALTA) or 0

        def entregar_original(motivo: str):
            """O TIFF cru, quando nao da para converter.

            COM EXTENSAO, E POR EXPERIENCIA.
                As fichas do E-Oficio nao tem extensao no disco: chamam-se
                `00002576.0001`. Entregando com esse nome, o Windows nao
                associa a visualizador nenhum e o operador ve "baixou um
                arquivo que nao abre" — que foi exatamente o que aconteceu.
                Acrescentar `.tif` custa nada e faz o arquivo virar imagem
                para quem recebe.

            SÓ O QUE COMEÇA COMO IMAGEM OU PDF (LS02, 19/10/2026): o caminho
            vem da pasta e do nome que a tela de imagens deixa digitar, e
            entregava cru qualquer arquivo do servidor — o `secret.key`
            inclusive. Ver `ri_imagens.parece_ficha`.
            """
            if not RIMG.parece_ficha(caminho):
                app.logger.warning(
                    "A ficha %s aponta para %s, que não é imagem nem PDF: "
                    "não foi entregue.", imagem_id, caminho)
                abort(404)
            nome = caminho.name
            if "." not in nome or nome.rsplit(".", 1)[1].isdigit():
                nome += ".tif"
            return Response(
                caminho.read_bytes(), mimetype="image/tiff",
                headers={"Content-Disposition": f'attachment; filename="{nome}"',
                         "X-Ficha-Motivo": motivo})

        try:
            from PIL import Image
        except ImportError:
            # Nao e defeito da ficha: e biblioteca faltando no servidor. Quem
            # ve isso precisa saber o que fazer, e nao receber um arquivo mudo.
            app.logger.warning(
                "Pillow ausente: a ficha %s foi entregue como TIFF para download. "
                "Instale com: <runtime>\\Scripts\\python.exe -m pip install Pillow",
                imagem_id)
            return entregar_original("pillow-ausente")

        import io as _io
        try:
            with Image.open(caminho) as im:
                try:
                    im.seek(pagina)
                except EOFError:
                    pass
                im = im.convert("L")
                largura = int(request.args.get("w") or 1100)
                if im.width > largura:
                    im = im.resize((largura, int(im.height * largura / im.width)))
                buf = _io.BytesIO()
                im.save(buf, format="PNG", optimize=True)
        except (OSError, ValueError) as erro:
            # Arquivo corrompido, formato que o Pillow nao reconhece, ou TIFF
            # sem a codificacao instalada. Antes isto virava erro 500 e a tela
            # inteira quebrava por causa de UMA ficha ruim.
            app.logger.warning("Não consegui converter a ficha %s (%s): %s",
                               imagem_id, caminho, erro)
            return entregar_original("conversao-falhou")
        return Response(buf.getvalue(), mimetype="image/png",
                        headers={"Cache-Control": "private, max-age=3600"})

    @app.route("/registro-imoveis/<int:matricula_id>/conferir-ficha")
    @login_required
    def ri_conferir_ficha(matricula_id):
        """Tela de conferencia: dado importado de um lado, digitalizacao do outro."""
        m = q1("SELECT * FROM ri_matriculas WHERE id=%s", (matricula_id,))
        if not m:
            abort(404)
        m = dict(m)
        imagens = q("""SELECT * FROM ri_imagens WHERE matricula_id=%s
                       ORDER BY ordem NULLS FIRST, nome_arquivo NULLS FIRST, id""",
                    (matricula_id,))
        # Ha duas fontes deliberadamente separadas: as paginas antigas do
        # E-Oficio (`ri_imagens`) e o arquivo oficial atual enviado pelo balcao
        # (`digi_*`). A conferencia so conhecia a primeira. Matriculas novas,
        # como a 4.016, portanto exibiam zero imagens embora o PDF estivesse
        # salvo e integro. Quando existe arquivo oficial, ele prevalece na
        # conferencia; as fontes nao sao somadas para evitar comparar ou
        # certificar uma mistura de versoes.
        digitalizacao = None
        if m.get("digi_path"):
            caminho_digi = Path(m["digi_path"])
            extensao = caminho_digi.suffix.lower()
            digitalizacao = {
                "nome": m.get("digi_nome") or caminho_digi.name,
                "extensao": extensao,
                "existe": caminho_digi.is_file(),
                "imagem_navegador": extensao in {".png", ".jpg", ".jpeg"},
                "pdf": extensao == ".pdf",
                "em": m.get("digi_em"),
                "por": m.get("digi_por"),
            }
        atos = q("""SELECT * FROM ri_atos WHERE matricula_id=%s
                    ORDER BY COALESCE(data_ato,'9999'), numero""", (matricula_id,))
        partes = q("SELECT * FROM ri_partes WHERE matricula_id=%s ORDER BY nome, id",
                   (matricula_id,))
        proximas = q("""SELECT id, numero, livro_norm FROM ri_matriculas
                        WHERE conferido=0 AND id<>%s ORDER BY livro_norm NULLS FIRST,
                        coalesce(substring(numero FROM '^[0-9]+')::bigint, 0), id
                        LIMIT 1""", (matricula_id,))
        return render_template("ri_conferir.html", m=m, imagens=imagens, atos=atos,
                               digitalizacao=digitalizacao,
                               partes=partes, teor_seguro=teor_seguro,
                               pillow=RIMG.pillow_disponivel(),
                               proxima=(proximas[0] if proximas else None))

    # ------------------------------------------------------- certidoes

    @app.route("/registro-imoveis/certidoes")
    @login_required
    def ri_certidoes():
        busca = (request.args.get("busca") or "").strip()
        onde, params = ["1=1"], []
        if busca:
            onde.append("(CAST(c.numero AS TEXT) ILIKE %s OR c.matricula_numero ILIKE %s "
                        "OR c.requerente ILIKE %s)")
            params += [f"%{busca}%"] * 3
        rows = q(f"""SELECT c.*, m.id mid FROM ri_certidoes c
                     LEFT JOIN ri_matriculas m ON m.id = c.matricula_id
                     WHERE {' AND '.join(onde)}
                     ORDER BY c.ano DESC, c.numero DESC LIMIT 300""", params)
        hoje = date.today().isoformat()
        resumo = q1("""SELECT COUNT(*) total,
            COALESCE(SUM(CASE WHEN origem='EOFICIO' THEN 1 ELSE 0 END),0)::bigint importadas,
            COALESCE(SUM(CASE WHEN origem='MANUAL' THEN 1 ELSE 0 END),0)::bigint emitidas,
            COALESCE(SUM(CASE WHEN cancelada=1 THEN 1 ELSE 0 END),0)::bigint canceladas
            FROM ri_certidoes""")
        return render_template("ri_certidoes.html", rows=rows, resumo=resumo,
                               busca=busca, hoje=hoje, TIPOS=ROTULOS_CERTIDAO_RI,
                               aguardando_selo=_certidoes_aguardando_selo(
                                   [r["id"] for r in rows]),
                               CODIGO_BASE_DA_CERTIDAO=_codigo_base_da_certidao())

    @app.route("/registro-imoveis/certidoes/<int:certidao_id>/selar",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_certidao_selar(certidao_id):
        """Pede de novo o selo da certidão que ficou aguardando cobertura.

        22/10/2026, dia da 3.7.0: a trava do selo pago deixa a certidão sem
        selo quando o protocolo pago não está ligado a ela, e a 3.7.0 não
        tinha como pedir o selo DEPOIS — só emitir, imprimir e cancelar. Quem
        resolveu o protocolo e o pagamento em «Selo e caixa» volta aqui.

        **AS MESMAS REFERÊNCIAS DA EMISSÃO** (`_pedir_os_selos_da_certidao_do_ri`):
        com elas o aparelho devolve o selo que já existir em vez de vender
        outro. As folhas se recontam do teor congelado, como na emissão.
        """
        c = q1("SELECT * FROM ri_certidoes WHERE id=%s", (certidao_id,))
        if not c:
            abort(404)
        voltar = (url_for("ri_ficha", matricula_id=c["matricula_id"])
                  + "#certidoes-da-ficha" if c["matricula_id"]
                  else url_for("ri_certidoes", busca=str(c["numero"])))
        if c["cancelada"]:
            flash("Esta certidão está cancelada: não se sela certidão "
                  "cancelada. Emita outra.", "danger")
            return redirect(voltar)
        if str(c["selo_texto"] or "").strip():
            flash("Esta certidão já tem selo. Para outra via, clique no número "
                  "dela: reimprimir não pede selo novo.", "success")
            return redirect(voltar)
        if int(certidao_id) not in _certidoes_aguardando_selo([certidao_id]):
            flash("Esta certidão não está esperando selo — ela não ficou "
                  "«aguardando cobertura». Selo de certidão antiga se digita "
                  "à mão.", "warning")
            return redirect(voltar)
        # O protocolo marcado no quadro («Atender este protocolo e selar de
        # novo», `_protocolo_do_selo.html`) chega como `protocolo_selo`.
        recusa = _atender_o_protocolo_escolhido(request.form)
        if recusa:
            flash(recusa, "danger")
            return redirect(voltar)
        fonte = str(c["fonte_corpo"] or "TEXTO").upper()
        caminho_digi = c["digi_path"] if fonte == "DIGITALIZACAO" else None
        paginas = None
        if caminho_digi and Path(caminho_digi).is_file():
            try:
                paginas = len(RDIGI.paginas_png(Path(caminho_digi)))
            except ValueError:
                paginas = None
        try:
            folhas = CFOLHAS.decidir_folhas_antes_de_emitir(
                fonte=fonte, caminho_digi=caminho_digi, paginas_digi=paginas,
                corpo_html=c["corpo"], folhas_informadas=None,
                get_setting=db.get_setting)
            pedido = _pedir_os_selos_da_certidao_do_ri(
                certidao_id=int(certidao_id), tipo=c["tipo"], folhas=folhas,
                requerente=c["requerente"],
                requerente_documento=c["requerente_documento"],
                matricula=c["matricula_numero"] or "",
                isento=bool(c["isento"]), motivo_isencao=c["motivo_isencao"])
        except (AS.AtoError, ValueError) as erro:
            flash(f"O selo não saiu: {erro}", "danger")
            return redirect(voltar)
        recado = _recado_dos_selos_da_certidao(pedido)
        if not pedido["saiu"]:
            audit("RI_CERTIDAO_SELO_PEDIDO_DE_NOVO", "RI_CERTIDAO", certidao_id,
                  {"numero": c["numero"], "ano": c["ano"], "selado": False,
                   "motivo": (pedido["faltou"] or [""])[0]})
            flash(f"A certidão nº {c['numero']}/{c['ano']} continua sem selo e "
                  f"não pode ser impressa.{recado}", "warning")
            return redirect(voltar)
        busca = _busca_pedida_na_emissao(int(certidao_id))
        if busca:
            recado += _selar_a_busca_da_certidao_do_ri(
                certidao_id=int(certidao_id), busca=busca,
                nome=c["requerente"], documento=c["requerente_documento"],
                matricula=c["matricula_numero"] or "",
                isento=bool(c["isento"]), motivo_isencao=c["motivo_isencao"])
        audit("RI_CERTIDAO_SELO_PEDIDO_DE_NOVO", "RI_CERTIDAO", certidao_id,
              {"numero": c["numero"], "ano": c["ano"], "selado": True,
               "selos": pedido["saiu"], **({"busca": busca} if busca else {})})
        flash(f"Certidão nº {c['numero']}/{c['ano']} selada.{recado} "
              "Já pode ser impressa.", "success")
        return redirect(url_for("ri_certidao_odt", certidao_id=certidao_id))

    # A CADEIA DOMINIAL E A VINTENÁRIA — 28/09/2026, reconstituídas em
    # 14/10/2026 (o código da 3.6.233/234 foi construído direto na produção e
    # se perdeu nos pacotes da 3.6.282 em diante; ver `ri_odt`, junto dos
    # miolos). O que o balcão escolhe na ficha entra aqui:
    #
    #   VINTENÁRIA — os ANOS (10, 15, 20 ou 30; padrão 20). Anos só valem
    #     para ela.
    #   DOMINIAL — as MATRÍCULAS DE ORIGEM. Digitadas, valem exatamente as
    #     digitadas (a 394/2026 saiu assim: 3472 → 2667 → 2548, e o «sob n°
    #     2.548» do registro anterior da 2667 não é citação que a régua
    #     reconheça). Em branco, o sistema segue o `registro_anterior` de
    #     matrícula em matrícula, até `MAX_PROFUNDIDADE_ORIGEM` degraus e
    #     `MAX_ORIGENS_POR_CERTIDAO` blocos.
    #
    # **SÓ ENTRA NO PAPEL A MATRÍCULA QUE EXISTE NO BANCO, E UMA SÓ.** Número
    # citado que não existe — ou que responde por mais de uma ficha — não vira
    # bloco: volta na lista `origens_nao_encontradas`, e a emissão avisa.
    # Nunca se inventa origem.
    TIPOS_DA_CADEIA = ("DOMINIAL", "VINTENARIA")

    def _contexto_da_cadeia(contexto: dict, tipo: str, *, anos=None,
                            origens_digitadas=None) -> dict:
        m = contexto["m"]
        if tipo == "VINTENARIA":
            return {**_janela_da_vintenaria(
                        contexto.get("atos") or [],
                        RIDOM.normalizar_anos(
                            str(anos or "").strip()
                            or RIDOM.ANOS_PADRAO_VINTENARIA)),
                    "_cadeia_montada": True}
        atual = {"numero": m["numero"], "papel": "atual",
                 "registro_anterior": (m.get("registro_anterior") or "").strip(),
                 "atos": RIDOM.cadeia_dominial(contexto.get("atos") or [])}
        blocos, nao_achadas = [atual], []
        digitadas = str(origens_digitadas or "").strip()
        if digitadas:
            fila = [(n, 1) for n in RIDOM.parsear_numeros_digitados(digitadas)]
            seguir = False
        else:
            fila = [(n, 1) for n in RIDOM.sugerir_numeros_origem(
                m.get("registro_anterior"), numero_atual=m["numero"])]
            seguir = True
        vistos = {RIDOM.normalizar_numero_matricula(m["numero"])}
        while fila and len(blocos) - 1 < RIDOM.MAX_ORIGENS_POR_CERTIDAO:
            numero, degrau = fila.pop(0)
            if numero in vistos:
                continue
            vistos.add(numero)
            achadas = q("SELECT id FROM ri_matriculas "
                        "WHERE CAST(numero AS TEXT)=%s", (numero,))
            if len(achadas) != 1:
                nao_achadas.append(
                    f"{numero} (" + ("não existe no banco" if not achadas
                                     else f"{len(achadas)} fichas com este número")
                    + ")")
                continue
            ctx_o = contexto_ficha(int(achadas[0]["id"]), para_odt=False)
            m_o = ctx_o["m"]
            blocos.append({
                "numero": m_o["numero"], "papel": "origem",
                "registro_anterior": (m_o.get("registro_anterior") or "").strip(),
                "atos": RIDOM.cadeia_dominial(ctx_o.get("atos") or [])})
            if seguir and degrau < RIDOM.MAX_PROFUNDIDADE_ORIGEM:
                fila.extend((n, degrau + 1) for n in RIDOM.sugerir_numeros_origem(
                    m_o.get("registro_anterior"), numero_atual=m_o["numero"]))
        return {"cadeia_dominial": atual["atos"], "cadeia_matriculas": blocos,
                "origens_nao_encontradas": nao_achadas,
                "_cadeia_montada": True}

    def corpo_certidao(tipo: str, contexto: dict) -> str:
        """Renderiza a certidao: O MOLDE do papel mais O MIOLO do tipo pedido.

        **SAO DOIS TEXTOS, E NAO UM** — problema #75, 18/09/2026. O molde
        (`RI_CERTIDAO`) traz o que toda certidao tem — a abertura, a finalidade,
        a validade do art. 553, quem assina — e carrega o marcador que diz ONDE
        o texto do tipo entra. Cada tipo tem o seu miolo no catalogo
        (`RI_CERTIDAO_INTEIRO_TEOR`, `RI_CERTIDAO_ONUS`,
        `RI_CERTIDAO_PROPRIEDADE`), e o oficial edita os quatro na mesma tela.

        **O MIOLO E RENDERIZADO PRIMEIRO, E ENTRA COMO TEXTO JA PRONTO.** Se
        ele fosse colado dentro do molde antes de renderizar, o `{{ }}` que o
        teor da ficha tiver — e o teor do acervo tem chave de tudo quanto e
        jeito — seria lido como marcador do Jinja, e o papel sairia com o texto
        do livro interpretado como modelo. Renderizado antes, o que entra no
        molde e papel, e nao modelo.
        """
        _chave_do_miolo = MIOLO_DA_CERTIDAO.get(tipo)
        if not _chave_do_miolo:
            raise ValueError(
                f"«{tipo}» não é um tipo de certidão desta casa. Os que "
                "existem: " + ", ".join(sorted(MIOLO_DA_CERTIDAO)) + ".")
        with db.connect() as _c:
            _corpo = MODELOS.corpo_de(_c, "RI_CERTIDAO")
            _miolo = MODELOS.corpo_de(_c, _chave_do_miolo)

        # O MOLDE TEM DE CARREGAR ONDE O MIOLO ENTRA. A guarda mora na mesma
        # funcao que a tela de editar usa, de modo que os dois lados conferem
        # com a MESMA regua: sem ela, o molde salvo sem o marcador sairia com a
        # abertura, a validade e a assinatura, e sem o teor — a certidao
        # afirmando «cujo inteiro teor segue:» e nao reproduzindo nada.
        #
        # `MoldeSemMarcador` (um `ModeloError`), e nao `ValueError` cru: a
        # frase e para quem edita o modelo, e a rota a mostra como mostra o
        # erro do Jinja (LX22B2) — so ela, e nao todo `ModeloError` (LX24).
        if (_erro := MODELOS.conferir_marcadores("RI_CERTIDAO", _corpo)):
            raise MoldeSemMarcador(_erro)

        # O TÍTULO DA CERTIDÃO DE ÔNUS DIZ SE ELA É POSITIVA OU NEGATIVA —
        # 13/10/2026. Antes saía «CERTIDÃO NEGATIVA DE ÔNUS REAIS» também sobre
        # imóvel hipotecado: o nome do tipo era o título do papel.
        # A frase do titulo mora na base (LF06B, `RI_ONUS_TITULO`): com `con`,
        # vale o ajuste da casa.
        with db.connect() as _c_frases:
            _nome = (RONIA.titulo(contexto.get("resultado_onus"),
                                  contexto.get("resultado_acoes"), con=_c_frases)
                     if tipo == "ONUS" else TIPOS_CERTIDAO.get(tipo, tipo))
        # A DOMINIAL E A VINTENÁRIA MONTAM A CADEIA SE NINGUÉM MONTOU — é o caso
        # de quem chama sem a tela (a remontagem, o ensaio): vale o padrão, 20
        # anos e a origem seguida pelo registro anterior. E a vintenária diz os
        # anos no título, como a 3.6.233 dizia.
        if tipo in TIPOS_DA_CADEIA and not contexto.get("_cadeia_montada"):
            contexto = contexto | _contexto_da_cadeia(contexto, tipo)
        if tipo == "VINTENARIA" and contexto.get("anos_periodo"):
            _nome = f"{_nome} ({contexto['anos_periodo']} anos)"
        return sem_linha_de_assinatura_a_mao(
            render_modelo(
            _corpo,
            contexto | {"tipo_certidao": tipo,
                        "tipo_certidao_nome": _nome,
                        # ja renderizado: e papel, e nao modelo
                        "miolo_do_tipo": render_modelo(_miolo, contexto)}))

    import ri_certidao_emissao as _RCE_REG
    _RCE_REG.registrar(contexto_ficha=contexto_ficha, corpo_certidao=corpo_certidao)

    @app.route("/registro-imoveis/<int:matricula_id>/certidao", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_emitir_certidao(matricula_id):
        tipo = (request.form.get("tipo") or "INTEIRO_TEOR").strip().upper()
        if tipo not in TIPOS_CERTIDAO:
            flash("Tipo de certidão inválido.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        # GRATUIDADE — 23/09/2026 (Beatriz, matricula 582). Espelho do
        # RCPN: recusa ANTES de criar a certidao. Motivo em branco com
        # isento marcado deixava certidao sem selo (licao do civil).
        isento, motivo_isencao = ler_isencao_do_form(request.form)
        motivo_isencao = motivo_isencao or ""
        if isento and not motivo_isencao:
            flash(
                "Certidao gratuita precisa do motivo escrito — e ele que a "
                "conferencia le no selo. Escreva o motivo ou desmarque "
                "Selo gratuito / isento.",
                "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))
        if isento and len(motivo_isencao) > 500:
            flash(
                "Motivo da gratuidade tem no maximo 500 caracteres "
                "(limite do TJ em motivoIsentoGratuito).",
                "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))
        if not isento:
            motivo_isencao = None

        # A BUSCA — pedido do oficial, 15/10/2026: selo próprio junto com a
        # certidão, a faixa sugerida pela abertura da matrícula. A escolha se
        # confere AQUI, antes de numerar, como a gratuidade logo acima.
        try:
            busca = _busca_da_certidao_do_ri(request.form)
        except BU.BuscaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        # O PROTOCOLO QUE PAGA O SELO, escolhido na tela (22/10/2026): vira o
        # «em atendimento» ANTES de numerar, para a recusa (protocolo
        # encerrado, inexistente) não deixar certidão gravada para trás.
        recusa = _atender_o_protocolo_escolhido(request.form)
        if recusa:
            flash(recusa, "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        contexto = contexto_ficha(matricula_id, para_odt=False)
        m = contexto["m"]

        # A CERTIDÃO DE ÔNUS: POSITIVA OU NEGATIVA, E O QUE SE TRANSCREVE —
        # 13/10/2026. A tela manda `onus_formulario=1` e obriga a escolher;
        # `ri_onus_ia.decidir` confere a escolha (trecho escrito na ficha,
        # negativa sobre ônus lavrado, negativa contra a IA sem justificativa) e
        # recusa ANTES de número e selo. Sem o campo — chamada antiga, sem a
        # tela —, vale o que o sistema sabe dos atos lavrados, como antes.
        if tipo == "ONUS" and request.form.get("onus_formulario") == "1":
            try:
                with db.connect() as _c_onus:
                    _escolha = RONIA.decidir(
                        texto_da_ficha_=RONIA.texto_da_ficha(_c_onus, matricula_id),
                        onus_vigentes=contexto.get("onus") or [],
                        sugestao=RONIA.ultima(_c_onus, matricula_id),
                        resultado_onus=request.form.get("resultado_onus"),
                        resultado_acoes=request.form.get("resultado_acoes"),
                        marcados=request.form.getlist("onus_item"),
                        manual_onus=request.form.get("onus_transcricao") or "",
                        manual_acao=request.form.get("acao_transcricao") or "",
                        justificativa=request.form.get("onus_justificativa") or "",
                        # O PROPRIETÁRIO QUE O PAPEL IMPRIME, conferido com o
                        # que a IA leu no teor — 15/10/2026 (certidão 64/2026).
                        proprietarios_cadastro=contexto.get("proprietarios") or [],
                        ia_ligada=RONIA.ligada(_c_onus, Path(app.config["DATA_DIR"])),
                        proprietario_conferido=(
                            request.form.get("proprietario_conferido") == "1"),
                        justificativa_proprietario=(
                            request.form.get("proprietario_justificativa") or ""))
            except RONIA.OnusError as erro:
                audit("RI_CERTIDAO_ONUS_RECUSADA", "RI_MATRICULA", int(matricula_id),
                      {"motivo": str(erro)[:400],
                       "resultado_onus": request.form.get("resultado_onus")})
                flash(str(erro), "danger")
                return redirect(url_for("ri_ficha", matricula_id=matricula_id)
                                + "#certidao-onus")
            contexto = contexto | _escolha

        # A DOMINIAL E A VINTENÁRIA LEVAM O QUE O BALCÃO ESCOLHEU — os anos da
        # vintenária e as matrículas de origem da cadeia (ver
        # `_contexto_da_cadeia`). Monta-se ANTES de número e selo: a cadeia é o
        # teor, e o teor congela junto com o número.
        if tipo in TIPOS_DA_CADEIA:
            contexto = contexto | _contexto_da_cadeia(
                contexto, tipo, anos=request.form.get("anos"),
                origens_digitadas=request.form.get("origens"))

        # A REVISÃO DA TRANSCRIÇÃO PELA IA — LH11, pedido do oficial em
        # 21/10/2026. Na certidão de inteiro teor (pelo texto ou pela
        # reprodução, quando a ficha tem texto transcrito) a divergência GRAVE
        # ainda não resolvida pede justificativa escrita, e a recusa vem ANTES
        # de número e selo, como a do ônus. A IA fora do ar NÃO trava: a
        # certidão sai, e a tela diz que saiu sem revisão. A régua mora em
        # `revisao_transcricao.conferir_para_emitir`; o que der errado nela
        # também não trava — o balcão parado é pior que a revisão atrasada.
        # Ela se repete com a linha da revisão presa dentro da transação que
        # numera (`reconferir_na_emissao`, LH12; depois da trava do número e
        # num SAVEPOINT próprio, LH15): esta aqui recusa cedo.
        transcricao = None

        def _recusa_da_transcricao(erro):
            audit("RI_CERTIDAO_TRANSCRICAO_RECUSADA", "RI_MATRICULA", int(matricula_id),
                  {"graves": erro.graves, "revisao_id": erro.revisao_id})
            flash(str(erro), "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id)
                            + "#certidao-transcricao")

        if tipo == "INTEIRO_TEOR":
            try:
                with db.connect() as _c_rt:
                    transcricao = RTRANS.conferir_para_emitir(
                        _c_rt, Path(app.config["DATA_DIR"]), RDIGI.raiz_arquivos(db),
                        matricula_id,
                        justificativa=request.form.get("transcricao_justificativa") or "")
            except RTRANS.TranscricaoPendente as erro:
                return _recusa_da_transcricao(erro)
            except Exception:                         # noqa: BLE001 — não trava a certidão
                app.logger.warning("A revisão da transcrição da matrícula %s não pôde ser "
                                   "conferida na emissão.", matricula_id, exc_info=True)
                transcricao = {"situacao": "ERRO", "revisao_id": None,
                               "recado": "a revisão não pôde ser conferida agora"}

        hoje = date.today()
        # 30 dias corridos, conforme o Codigo de Normas do TJMA.
        validade = (hoje + timedelta(days=VALIDADE_CERTIDAO_DIAS)).isoformat()

        # Fonte do corpo da certidao de inteiro teor (16/09/2026):
        # DIGITALIZACAO = reproducao do scan + selo ao final;
        # TEXTO = modelo RI_CERTIDAO (livros antigos / manuscritos).
        # Outros tipos de certidao continuam sempre em texto.
        fonte_pedida = (request.form.get("fonte_corpo") or "").strip().upper()
        if tipo == "INTEIRO_TEOR":
            if fonte_pedida not in ("DIGITALIZACAO", "TEXTO"):
                # O PADRÃO SEGUE A FICHA, E NÃO UMA CONSTANTE — corrigido em
                # 16/09/2026, depois de medir a produção: `digi_path` está
                # vazio em **1.982 matrículas de 1.982**, e esta casa já
                # emitiu **370** certidões de inteiro teor.
                #
                # Com `DIGITALIZACAO` fixo aqui, toda certidão de inteiro teor
                # da casa era recusada — a recusa mandando «envie o arquivo na
                # ficha», e a certidão que mais se emite parava. A escolha do
                # balcão continua mandando: quem pedir a reprodução numa ficha
                # sem arquivo continua levando a recusa, com o motivo.
                fonte_pedida = ("DIGITALIZACAO"
                                if _tem_digitalizacao(matricula_id) else "TEXTO")
        else:
            fonte_pedida = "TEXTO"

        digi_info = None
        proximo = q1("SELECT COALESCE(MAX(numero),0)+1 n FROM ri_certidoes WHERE ano=%s",
                     (hoje.year,))["n"]
        contexto["certidao_numero"] = proximo

        if fonte_pedida == "DIGITALIZACAO":
            with db.connect() as _c:
                digi_info = RDIGI.atual_da_matricula(_c, matricula_id)
            if (not digi_info or not digi_info.get("digi_path")
                    or not Path(digi_info["digi_path"]).is_file()):
                flash(
                    "Nao ha digitalizacao oficial nesta matricula. "
                    "Envie o arquivo na ficha ou escolha emitir pelo texto "
                    "extraido.",
                    "danger")
                return redirect(url_for("ri_ficha", matricula_id=matricula_id))
            try:
                n_paginas = len(RDIGI.paginas_png(Path(digi_info["digi_path"])))
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("ri_ficha", matricula_id=matricula_id))
            with db.connect() as _c_frases:       # o fecho mora na base (LF06B)
                corpo = RDIGI.corpo_resumo_digitalizacao(
                    matricula=m["numero"], paginas=n_paginas,
                    sha256=digi_info["digi_sha256"] or "", con=_c_frases)
            # Fecho igual à via por texto corrido: protocolo em aberto + validade.
            corpo = (corpo or "") + (contexto.get("clausula_prenotacoes_abertas") or "")
            _hoje_ext = (contexto.get("hoje_extenso") or "").strip()
            if _hoje_ext:
                # A FRASE MORA NA BASE — LF06B (`RI_REPROGRAFICA_VALIDADE`).
                import ri_frases
                with db.connect() as _c_frases:
                    corpo += ri_frases.frase("RI_REPROGRAFICA_VALIDADE", _c_frases,
                                             hoje_extenso=_hoje_ext)
        else:
            try:
                corpo = corpo_certidao(tipo, contexto)
            except MoldeSemMarcador as erro:
                # O MOLDE SEM A EMENDA TEM DE DIZER O QUE FALTA — LX22B2,
                # 20/10/2026. Desde o LX11 o `except Exception` abaixo manda
                # para o log tudo o que nao e erro do Jinja (B2: texto do banco
                # nao vai a tela), e a recusa do relato #75 — frase escrita
                # para o balcao, sem nada do servidor — virou «nao foi possivel
                # concluir»: o escrevente ficava sem saber que era so repor
                # `{{ miolo_do_tipo }}`.
                #
                # SO ESTA RECUSA (LX24, ressalva 1 do LX22B2). O `ModeloError`
                # de `corpo_de` diz o schema da base, o arquivo que falta e a
                # variavel de ambiente: esse cai no `except Exception` e vai
                # ao log.
                flash(f"O modelo de certidao tem um erro: {erro}", "danger")
                return redirect(url_for("ri_ficha", matricula_id=matricula_id))
            except Exception as erro:
                flash("O modelo de certidao tem um erro: "
                      f"{SEGWEB.erro_do_modelo(erro, 'ri_certidao')}", "danger")
                return redirect(url_for("ri_ficha", matricula_id=matricula_id))

        recusa_de_dentro = RTRANS.RecusaGuardada()
        with recusa_de_dentro, db.transaction() as con:
            bd = banco(con)
            # A TRAVA DO NÚMERO PRIMEIRO, E A LINHA DA REVISÃO DEPOIS (LH15) —
            # a ordem da casa: a trava de assunto antes do `FOR UPDATE`. A
            # segunda emissão espera na porta, pelo número, sem segurar linha
            # nenhuma; e ela fica fora do SAVEPOINT de baixo, que a soltaria.
            bd.travar("ri_certidoes.numero")
            # A REVISÃO DA TRANSCRIÇÃO OUTRA VEZ, COM A LINHA PRESA, ANTES DE
            # LER O NÚMERO (LH12). A conferência lá de cima leu sem prender
            # nada; é a decisão daqui que vai para `ri_transcricao_emissoes`. A
            # recusa volta atrás sem nada gravado e é dada depois do `with` (ver
            # `RecusaGuardada`); o erro inesperado não trava, como lá em cima.
            #
            # NUM SAVEPOINT PRÓPRIO (LH15, a ressalva da revisão do LH12). Sem
            # a ponte, o erro de SQL aqui — a linha da revisão presa além do
            # `lock_timeout`, o deadlock, o erro em `mostrar` — condenava a
            # transação, e o número logo abaixo virava 500. O SAVEPOINT desfaz
            # só a reconferência (que não grava nada), e a certidão sai «sem
            # revisão», a regra do LH11 para a revisão que não se pôde ver.
            try:
                with bd.ponto_de_retorno("rt_reconferencia"):
                    transcricao = RTRANS.reconferir_na_emissao(
                        bd, transcricao, matricula_id=matricula_id,
                        justificativa=request.form.get("transcricao_justificativa") or "")
            except RTRANS.TranscricaoPendente:
                raise
            except Exception:                         # noqa: BLE001 — não trava a certidão
                app.logger.warning("A revisão da transcrição da matrícula %s não pôde ser "
                                   "reconferida na emissão.", matricula_id, exc_info=True)
                transcricao = {"situacao": "ERRO", "revisao_id": None,
                               "recado": "a revisão não pôde ser conferida agora"}
            ultimo = bd.valor("SELECT MAX(numero) AS n FROM ri_certidoes WHERE ano=%s",
                              (hoje.year,))
            numero = int((ultimo or 0)) + 1
            if fonte_pedida == "TEXTO" and numero != proximo:
                corpo = corpo_certidao(tipo, contexto | {"certidao_numero": numero})
            h = hash_certidao(numero, hoje.year, tipo, m["numero"], corpo, hoje.isoformat())
            certidao_id = bd.escrever(
                """INSERT INTO ri_certidoes
                   (numero, ano, tipo, matricula_id, matricula_numero, requerente,
                    requerente_documento, finalidade, data_emissao, validade_ate,
                    corpo, corpo_formato, protocolo, selo_texto, emolumentos,
                    hash_certidao, origem, emitida_em, emitida_por,
                    emitida_por_nome, emitida_por_funcao, isento, motivo_isencao)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, 'html', %s,%s,%s,%s, 'MANUAL',
                           %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (numero, hoje.year, tipo, matricula_id, m["numero"],
                 (request.form.get("requerente") or "").strip() or None,
                 so_digitos(request.form.get("requerente_documento")) or None,
                 (request.form.get("finalidade") or "").strip() or None,
                 hoje.isoformat(), validade, corpo,
                 (request.form.get("protocolo") or "").strip() or None,
                 (request.form.get("selo_texto") or "").strip() or None,
                 (request.form.get("emolumentos") or "").strip() or None,
                 # QUEM ASSINA A CERTIDAO — 16/09/2026, pedido do oficial:
                 # «precisa constar o nome e funcao do usuario logado».
                 #
                 #   Ate aqui `emitida_por` recebia `None`. A coluna existia, o
                 #   `INSERT` a nomeava, e passava vazio: medido na producao,
                 #   NULL nas 372 certidoes. Nao faltava chamador — faltava um
                 #   argumento dele.
                 #
                 #   **ELA E UM ID, E NAO UM NOME** (`REFERENCES users(id)`), e
                 #   e por isso que o nome e a funcao tem colunas proprias. Ver
                 #   `ri_schema.MIGRACOES`: escrever o nome aqui estoura na
                 #   chave estrangeira.
                 #
                 #   **GRAVA-SE AGORA, E NAO SE CALCULA AO IMPRIMIR**: a
                 #   segunda via de seis meses depois, tirada por outra
                 #   pessoa, tem de sair com o nome de quem expediu.
                 h, db.now(), app.extensions["usuario_id"](),
                 (app.extensions["usuario_nome"]() or "").strip() or None,
                 (app.extensions["usuario_funcao"]() or "").strip() or None,
                 1 if isento else 0, motivo_isencao),
            )[0]["id"]
            certidao_id = int(certidao_id)

            if fonte_pedida == "DIGITALIZACAO" and digi_info:
                bd.escrever(
                    """UPDATE ri_certidoes
                          SET fonte_corpo=%s, digi_path=%s, digi_sha256=%s
                        WHERE id=%s""",
                    ("DIGITALIZACAO", digi_info["digi_path"],
                     digi_info["digi_sha256"], certidao_id))
            else:
                bd.escrever(
                    "UPDATE ri_certidoes SET fonte_corpo=%s WHERE id=%s",
                    ("TEXTO", certidao_id))

            # EM QUE PÉ ESTAVA A REVISÃO DA TRANSCRIÇÃO (LH11): a justificativa
            # de quem emitiu com divergência grave fica com a certidão.
            RTRANS.gravar_na_certidao(bd, transcricao, certidao_id=certidao_id,
                                      matricula_id=matricula_id,
                                      usuario=app.extensions["usuario_nome"]())

            # O QUE A CERTIDÃO DE ÔNUS AFIRMOU, e quem escolheu — gravado ao
            # lado do corpo, para a lista e a correição não terem de ler o papel.
            if tipo == "ONUS":
                bd.escrever(
                    """UPDATE ri_certidoes
                          SET resultado_onus=%s, resultado_acoes=%s, onus_sugestao_id=%s,
                              onus_justificativa=%s, onus_escolhido_por=%s,
                              onus_proprietario_conferencia=%s,
                              onus_proprietario_justificativa=%s
                        WHERE id=%s""",
                    (contexto.get("resultado_onus"), contexto.get("resultado_acoes"),
                     contexto.get("onus_sugestao_id"),
                     contexto.get("onus_justificativa") or None,
                     contexto.get("onus_escolhido_por"),
                     contexto.get("onus_proprietario_conferencia"),
                     contexto.get("onus_proprietario_justificativa") or None,
                     certidao_id))
        if recusa_de_dentro.erro is not None:
            return _recusa_da_transcricao(recusa_de_dentro.erro)

        audit("RI_CERTIDAO_EMITIDA", "RI_CERTIDAO", certidao_id,
              {"numero": numero, "ano": hoje.year, "tipo": tipo,
               "matricula": m["numero"], "hash": h,
               # a busca escolhida (15/10/2026), inclusive o «.9» sem selo
               **({"busca": busca} if busca else {}),
               # a revisão da transcrição (LH11): só a situação, o id e a conta
               **({"transcricao": transcricao["situacao"],
                   "transcricao_revisao_id": transcricao.get("revisao_id"),
                   "transcricao_graves": transcricao.get("graves_pendentes") or 0}
                  if transcricao and transcricao["situacao"] not in (
                      "DESLIGADA", "SEM_TEXTO") else {}),
               **({"resultado_onus": contexto.get("resultado_onus"),
                   "resultado_acoes": contexto.get("resultado_acoes"),
                   "onus_escolhido_por": contexto.get("onus_escolhido_por"),
                   "onus_sugestao_id": contexto.get("onus_sugestao_id"),
                   "onus_justificativa": contexto.get("onus_justificativa") or None,
                   "onus_proprietario_conferencia":
                       contexto.get("onus_proprietario_conferencia"),
                   "onus_proprietario_justificativa":
                       contexto.get("onus_proprietario_justificativa") or None}
                  if tipo == "ONUS" else {})})

        if fonte_pedida == "DIGITALIZACAO" and digi_info:
            try:
                snap = RDIGI.congelar_para_certidao(
                    db, certidao_id=certidao_id,
                    origem=Path(digi_info["digi_path"]))
                with db.transaction() as con:
                    banco(con).escrever(
                        """UPDATE ri_certidoes
                              SET digi_path=%s, digi_sha256=%s
                            WHERE id=%s""",
                        (snap["path"], snap["sha256"], certidao_id))
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("ri_ficha", matricula_id=matricula_id))


        # ---------------------------------------------- o selo, sozinho
        #
        # **RELATO #43 do oficial, 07/09/2026**: «certidão não está emitindo
        # selo automático — ainda aparece campo para inclusão manual do selo».
        # Ele estava certo: esta rota lia `selo_texto` do formulário e nunca
        # chamava o selador. **O caminho existe e a casa o usou 667 vezes**
        # (`/selo/imovel/certidao`), e o envelope está medido nesses 667.
        #
        # **SELAR NUNCA DERRUBA ATO QUE JÁ EXISTE**, e por isso a chamada vem
        # DEPOIS do `with` e não estoura: a certidão já está gravada, com
        # número e hash. Balcão parado é pior que selo atrasado, e certidão com
        # selo inventado é pior que os dois. O campo de digitar à mão fica,
        # porque o selador é máquina da rede local e cai.
        recado_do_selo = ""
        # NASCE AQUI, E NÃO SÓ NO RAMO DO SELO AUTOMÁTICO — 23/09/2026. Ela só
        # era criada dentro deste `if`, e a mensagem final a lê sempre: com o
        # selo DIGITADO À MÃO a tela estourava `UnboundLocalError` DEPOIS de a
        # certidão estar gravada. É o desenho do problema #84 outra vez — a
        # tela dizendo «erro» sobre um ato já praticado, e o balcão emitindo
        # de novo. Com selo à mão o sistema não conta folhas, e a frase fica
        # vazia, que é a verdade.
        folhas_contadas_msg = ""
        aguardando = False
        if not (request.form.get("selo_texto") or "").strip():
            try:
                # **A CERTIDAO DE MAIS DE UMA FOLHA SAO DOIS SELOS** —
                # 21/09/2026, medido nos 667 envelopes do acervo agrupados
                # pelo protocolo: `16.24.4` + `16.24.4.1` em 99 protocolos e
                # `16.24.1` + `16.24.2` em 94, com o item BASE sempre em 1 e o
                # numero das folhas no item da folha acrescida.
                #
                # **E ATE HOJE ESTA ROTA MANDAVA UM ITEM SO, COM UMA FOLHA.**
                # Ela lia `request.form.get("folhas")` e **nenhum modelo de
                # tela mandava esse campo** — argumento sem quem o passe, a
                # mesma familia do defeito que travou o CNIB inteiro, e que
                # varredor de funcao orfa nao pega porque a funcao TEM
                # chamador. Dos 667 envelopes reais, **92 cobraram mais de uma
                # folha**, ate doze. O campo nasceu na ficha em 21/09/2026.
                # FOLHAS CONTADAS PELO SISTEMA ANTES DO SELO - 22/09/2026.
                # Pedido: "antes de emitir as certidões o próprio já
                # contabilize quantas folhas irá ter". Na digitalização
                # conta o arquivo; no texto, o papel (PDF) / estimativa.
                # O campo da tela, se maior, ainda vale (capa/anexo).
                try:
                    _folhas_tela = int((request.form.get("folhas") or "").strip() or 0) or None
                except ValueError:
                    _folhas_tela = None
                folhas = CFOLHAS.decidir_folhas_antes_de_emitir(
                    fonte=fonte_pedida,
                    caminho_digi=(digi_info or {}).get("digi_path") if digi_info else None,
                    paginas_digi=locals().get("n_paginas"),
                    corpo_html=corpo,
                    folhas_informadas=_folhas_tela,
                    get_setting=db.get_setting,
                )
                folhas_contadas_msg = (
                    f" {folhas} folha(s) contabilizada(s) pelo sistema."
                    if folhas else "")
                pedido = _pedir_os_selos_da_certidao_do_ri(
                    certidao_id=certidao_id, tipo=tipo, folhas=folhas,
                    requerente=request.form.get("requerente"),
                    requerente_documento=request.form.get(
                        "requerente_documento"),
                    matricula=m["numero"], isento=isento,
                    motivo_isencao=motivo_isencao)
                recado_do_selo = _recado_dos_selos_da_certidao(pedido)
                aguardando = pedido["aguardando"]
            except (AS.AtoError, ValueError) as erro:
                recado_do_selo = f" SEM SELO: {erro}"

        motivo_selo = _motivo_da_falha_do_selo(recado_do_selo)
        if motivo_selo and aguardando:
            # AGUARDANDO COBERTURA NÃO É SELO RECUSADO (22/10/2026). Medido na
            # produção no dia da 3.7.0: a escrevente quitou o protocolo
            # 2026.10.61 e as certidões 83 e 84 da matrícula 3252 foram
            # CANCELADAS sozinhas, porque o protocolo não estava marcado como
            # «em atendimento». O selo nem chegou a ser pedido; cancelar
            # queimava um número por tentativa. A certidão fica de pé, sem
            # poder ser impressa (`ri_certidao_odt` recusa), e o botão
            # «Selar» da ficha pede o selo com as mesmas referências.
            audit("RI_CERTIDAO_AGUARDANDO_COBERTURA", "RI_CERTIDAO",
                  certidao_id, {"numero": numero, "ano": hoje.year,
                                "tipo": tipo, "matricula": m["numero"],
                                "motivo": motivo_selo,
                                **({"busca": busca} if busca else {})})
            flash(f"Certidão nº {numero}/{hoje.year} gravada, mas SEM SELO: "
                  f"{motivo_selo} Ela não pode ser impressa até o selo sair. "
                  "Ligue o protocolo pago e clique em «Selar» na lista de "
                  "certidões desta ficha.", "warning")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id)
                            + "#certidoes-da-ficha")
        if motivo_selo:
            quando = db.now()
            quem = app.extensions["usuario_nome"]()
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE ri_certidoes
                          SET cancelada=1, motivo_cancelamento=%s,
                              cancelada_em=%s, cancelada_por=%s
                        WHERE id=%s""",
                    (f"Selo não emitido: {motivo_selo}", quando, quem,
                     certidao_id))
            audit("RI_CERTIDAO_NAO_EMITIDA_SELO_FALHOU", "RI_CERTIDAO",
                  certidao_id, {"numero": numero, "ano": hoje.year,
                                "tipo": tipo, "matricula": m["numero"],
                                "hash": h, "motivo": motivo_selo})
            flash("Certidão NÃO emitida: o selo não saiu. "
                  f"Motivo: {motivo_selo}. Corrija o problema do "
                  "selo e tente de novo.",
                  "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))
        # A BUSCA SAI DEPOIS DA CERTIDÃO JÁ SELADA (15/10/2026). Com o selo
        # digitado à mão, a busca também é da mão — nada se pede ao aparelho.
        if busca and not (request.form.get("selo_texto") or "").strip():
            recado_do_selo += _selar_a_busca_da_certidao_do_ri(
                certidao_id=certidao_id, busca=busca,
                nome=request.form.get("requerente"),
                documento=request.form.get("requerente_documento"),
                matricula=m["numero"], isento=isento,
                motivo_isencao=motivo_isencao)
        with db.connect() as _c_frases:           # o titulo mora na base (LF06B)
            _nome_emitida = (RONIA.titulo(contexto.get("resultado_onus"),
                                          contexto.get("resultado_acoes"),
                                          con=_c_frases)
                             if tipo == "ONUS" else TIPOS_CERTIDAO[tipo])
        flash(f"{_nome_emitida} nº {numero}/{hoje.year} emitida. "
              f"Válida até {validade}. O teor foi congelado nesta data."
              f"{folhas_contadas_msg}"
              f"{recado_do_selo}",
              "success" if "SEM SELO" not in recado_do_selo else "warning")
        if RTRANS.recado_da_emissao(transcricao):
            flash(RTRANS.recado_da_emissao(transcricao).strip(), "warning")
        if tipo == "ONUS":
            por_palavra = [a["rotulo"] for a in contexto.get("onus") or []
                           if a.get("conferir")]
            if por_palavra:
                flash("Confira antes de entregar: "
                      f"{', '.join(por_palavra)} entrou na certidão de ônus "
                      "pela palavra do teor, sem natureza do título "
                      "reconhecida. Se não for ônus, cancele a certidão, "
                      "corrija a natureza do ato e emita de novo.", "warning")
        if tipo in TIPOS_DA_CADEIA:
            lista = ([a for b in contexto.get("cadeia_matriculas") or []
                      for a in b.get("atos") or []]
                     if tipo == "DOMINIAL" else
                     contexto.get("dominio_periodo") or [])
            por_palavra = [a["rotulo"] for a in lista if a.get("conferir")]
            if por_palavra:
                flash("Confira antes de entregar: "
                      f"{', '.join(por_palavra)} entrou na cadeia dominial "
                      "pela palavra do teor, sem natureza do título "
                      "reconhecida. Se não for transmissão de domínio, "
                      "cancele, corrija a natureza do ato e emita de novo.",
                      "warning")
            if contexto.get("origens_nao_encontradas"):
                flash("Matrícula de origem que NÃO entrou na cadeia: "
                      f"{'; '.join(contexto['origens_nao_encontradas'])}. "
                      "Só entra no papel a matrícula que existe no banco — "
                      "confira o número e, se for o caso, emita de novo.",
                      "warning")
        return redirect(url_for("ri_certidao_odt", certidao_id=certidao_id))

    def _etiqueta_da_certidao(c) -> str:
        """A etiqueta inteira do selo desta certidao. So LE.

            «o carimbo de certidao sempre precisa ir completo, com os
             emolumentos do ato, esta faltando ali» — o oficial, 17/09/2026

        **A COLUNA GUARDA O NUMERO; A ETIQUETA MORA NO RAZAO.** Medido na
        producao: `ri_certidoes.selo_texto` tem os **28 caracteres** do codigo,
        e `sd_selos.texto` tem os **264** com `Total R$ … Emol R$ … FERC R$ …`.
        O carimbo monta o que diz a partir do texto que recebe — com o numero
        ele nao tem de onde tirar os valores.

        **A CHAVE E `tabela` MAIS `ato_id`**: por `ato_id` sozinho vem selo de
        outra atribuicao (medido em 15/09 — tres reconhecimentos de firma de
        2022 responderam por ids de `ri_atos`). E a mesma leitura que a ficha
        ja faz para o ato e para a abertura.

        **E O NUMERO CONTINUA VALENDO** quando o razao nao tem o texto: selo
        digitado a mao pode nao ter etiqueta guardada, e ali o carimbo sai com
        o numero e sem a linha de valores — que e a verdade. Remontar a conta
        aqui seria imprimir num papel assinado um valor que o selo nao declara.
        """
        # **A LEITURA E A DA CASA** — `ato_selado.etiqueta_do_ato`, 17/09/2026.
        # Ela nasceu aqui e passou a servir as quatro certidoes; deixar uma
        # copia em cada uma daria quatro versoes do pedaco que decide de onde
        # vem o dinheiro impresso num papel assinado.
        numero = str(c["selo_texto"] or "").strip()
        if not numero:
            return ""
        with db.connect() as con:
            return AS.etiqueta_do_ato(
                con, "ri_certidoes", int(c["id"]), numero) or numero

    # **A CÓPIA DO QR QUE MORAVA AQUI FOI APAGADA — 17/09/2026.** Ela era uma
    # de TRÊS na casa (aqui, em `rc_certidao_odt` e em
    # `rc_certidao_inteiro_teor`), e o que vai DENTRO do QR de um papel
    # assinado não pode ter três versões. A que ficou é
    # `ri_odt.png_do_qr_do_selo`, importada no alto deste arquivo.
    #
    #   **APAGADA, E NÃO DESLIGADA**: função pronta sem chamador é a arma que
    #   alguém religa sem saber por que ela existia — seis vezes pagas neste
    #   projeto.

    def _assinatura_de_quem_emitiu(c) -> str:
        """A linha em que quem expediu a certidao assina. So monta o ODF.

            «precisa dar uma linha de espaco para quem emitiu a certidao
             assinar (...) precisa constar o nome e funcao do usuario logado»
              — o oficial, 16/09/2026

        O BRANCO DE CIMA TEM DONO: e onde a caneta passa. Em livro de registro
        espaco em branco e onde cabe uma linha que ninguem lavrou — aqui, no
        pe de uma certidao e depois do selo, ele e o lugar da assinatura, e
        sem ele a rubrica cai por cima do carimbo.

        **O NOME SO SAI SE ESTIVER GRAVADO.** As 372 certidoes anteriores a
        16/09/2026 tem `emitida_por` NULL, e saem com a linha e sem nome
        embaixo — que e a verdade. Escrever ali quem esta imprimindo faria a
        segunda via afirmar que ela foi expedida por quem so a reimprimiu.

        **O BRANCO DA CANETA SAIU EM 22/09/2026, E O NOME FICOU — 23/09/2026.**
        A ordem de 22/09 tirou da certidao o espaco de assinatura a mao («so na
        ficha»). O remendo daquele dia tirou esta chamada inteira da certidao
        por digitalizacao, e com o branco foram o nome e o titulo: o papel
        passou a sair sem dizer quem o expediu. O oficial decidiu em 23/09 que
        ele diz: sai o nome e o titulo, sem as duas linhas em branco.
        """
        from html import escape

        def _coluna(nome: str) -> str:
            try:
                return str(c[nome] or "").strip()
            except (KeyError, IndexError):
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


    def _corpo_ja_traz_quem_emitiu(corpo_html: str | None, quem: str) -> bool:
        """True se o corpo congelado já termina com o nome de quem emitiu.

        Evita nome 2× no papel: o molde grava quem responde pela serventia e
        `_assinatura_de_quem_emitiu` acrescentaria o emitente de novo. Quando
        for a mesma pessoa, fica uma assinatura.
        Pedido Beatriz 23/09/2026 (certidão 20/2026, matrícula 4019).
        """
        if not quem or not corpo_html:
            return False
        return quem.casefold() in (corpo_html or "")[-900:].casefold()

    @app.route("/registro-imoveis/certidoes/<int:certidao_id>.odt")
    @login_required
    def ri_certidao_odt(certidao_id):
        c = q1("SELECT * FROM ri_certidoes WHERE id=%s", (certidao_id,))
        if not c:
            abort(404)
        if not c["corpo"]:
            flash("Esta certidão foi importada do sistema antigo sem o teor. "
                  "Ela consta no livro, mas não pode ser reimpressa aqui.", "warning")
            return redirect(url_for("ri_certidoes"))
        # CERTIDÃO ESPERANDO SELO NÃO SAI EM PAPEL (22/10/2026). Na produção,
        # a certidão 83/2026 foi impressa duas vezes sem selo, depois de a
        # trava do selo pago a deixar sem cobertura. Papel de certidão sem selo
        # é papel que a serventia não pode entregar; quem resolve é o «Selar».
        if (not c["cancelada"] and not str(c["selo_texto"] or "").strip()
                and int(certidao_id) in _certidoes_aguardando_selo([certidao_id])):
            flash(f"A certidão nº {c['numero']}/{c['ano']} ainda está SEM SELO "
                  "(aguardando protocolo e pagamento) e não pode ser impressa. "
                  "Ligue o protocolo pago em «Selo e caixa» e clique em "
                  "«Selar».", "warning")
            return redirect(url_for("ri_ficha", matricula_id=c["matricula_id"])
                            + "#certidoes-da-ficha" if c["matricula_id"]
                            else url_for("ri_certidoes", busca=str(c["numero"])))

        fonte = None
        try:
            fonte = c["fonte_corpo"]
        except (KeyError, IndexError):
            fonte = None
        fonte = (fonte or "TEXTO").upper()
        if fonte == "DIGITALIZACAO":
            digi_path = None
            try:
                digi_path = c["digi_path"]
            except (KeyError, IndexError):
                digi_path = None
            if not digi_path or not Path(digi_path).is_file():
                flash("A digitalizacao desta certidao nao esta no disco. "
                      "Nao e possivel reimprimir a reproducao.", "danger")
                return redirect(url_for("ri_certidoes"))
            selo_qr_bytes = None
            selo_qr_mime = None
            if c["selo_qr"]:
                try:
                    selo_qr_bytes = base64.b64decode(c["selo_qr"])
                    selo_qr_mime = c["selo_qr_mime"] or "image/png"
                except Exception:
                    selo_qr_bytes = None
            if not selo_qr_bytes:
                # **O QR SE DERIVA DO NUMERO DO SELO** — 17/09/2026. Medido:
                # `ri_certidoes.selo_qr` esta vazia em **375 de 375**, e sem
                # ela a certidao por reproducao saia **sem o quadradinho**: o
                # papel levava o numero, os valores e o link escrito, e nada
                # de QR. A coluna existe e nunca foi escrita por ninguem.
                #
                #   O QR NAO PRECISA SER GUARDADO: ele e derivado, e e por
                #   isso que a segunda via de amanha traz o mesmo de hoje. O
                #   que estiver gravado continua ganhando — QR colado do
                #   portal e escolha de alguem, e o derivado e o caminho de
                #   quando nao ha nada.
                etiqueta_do_qr = _etiqueta_da_certidao(c)
                numero_do_selo = ""
                try:
                    import selo_no_papel as _SNP
                    numero_do_selo = str(
                        (_SNP.ler(etiqueta_do_qr) or {}).get("codigo") or "")
                except Exception:                            # noqa: BLE001
                    numero_do_selo = ""
                numero_do_selo = (numero_do_selo.strip()
                                  or str(c["selo_texto"] or "").strip())
                selo_qr_bytes = png_do_qr_do_selo(numero_do_selo)
                selo_qr_mime = "image/png" if selo_qr_bytes else None
            # O MODELO DA CASA DA REPROGRAFICA (substituta, 20/10/2026; LH02):
            # o papel identifica a matricula (livro, folha, CNM), a data da
            # emissao e quem assina, e o cabecalho le o cadastro da serventia.
            # So LE; o teor congelado nao muda.
            _m_repro = (q1("SELECT numero, livro, folha, cnm FROM ri_matriculas "
                           "WHERE id=%s", (c["matricula_id"],))
                        if c["matricula_id"] else None)
            _ident_repro = (RDIGI.identificacao_da_matricula(
                _m_repro["numero"], _m_repro["livro"], _m_repro["folha"],
                _m_repro["cnm"]) if _m_repro else "")
            try:
                # o CERTIFICO e o fecho moram na base (LF06B; `RI_REPROGRAFICA_*`)
                with db.connect() as _c_frases:
                    arquivo = RDIGI.odt_da_digitalizacao(
                        Path(digi_path),
                        con=_c_frases,
                        identificacao=_ident_repro,
                        data_emissao=str(c["data_emissao"] or c["emitida_em"] or "")[:10],
                        signatario=(str(c["emitida_por_nome"] or "").strip()
                                    if "emitida_por_nome" in c.keys() else "",
                                    str(c["emitida_por_funcao"] or "").strip()
                                    if "emitida_por_funcao" in c.keys() else ""),
                        serventia=dados_serventia(db.get_settings),
                        selo_texto=_etiqueta_da_certidao(c),
                        selo_qr=selo_qr_bytes,
                        selo_qr_mime=selo_qr_mime,
                        nome=f'certidao-{c["numero"]}-{c["ano"]}',
                        rotulo_selo="SELO DA CERTIDAO",
                        # Quem expediu, sem o branco da caneta - 23/09/2026.
                        assinatura_odf=(
                            "" if _corpo_ja_traz_quem_emitiu(
                                c["corpo"] if "corpo" in c.keys() else None,
                                (str(c["emitida_por_nome"] or "").strip()
                                 if "emitida_por_nome" in c.keys() else ""))
                            else _assinatura_de_quem_emitiu(c)),
                        # Titulo na 1a folha + fecho (protocolo aberto) no final.
                        corpo_html=(c["corpo"] if "corpo" in c.keys() else None))
            except ValueError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("ri_certidoes"))
            audit("RI_CERTIDAO_IMPRESSA", "RI_CERTIDAO", certidao_id,
                  {"numero": c["numero"], "ano": c["ano"],
                   "fonte": "DIGITALIZACAO"})
            return IMPW.resposta_do_papel(
                arquivo, nome=f'certidao-{c["numero"]}-{c["ano"]}',
                get_setting=db.get_setting, voltar_para=url_for("ri_certidoes"))

        # CARIMBOS DO CORPO = MESMA ESTRUTURA DA FICHA — 22/09/2026.
        # O HTML congelado traz `carimbo_compacto_html` (caixa+QR). Passar
        # isso cru por `html_para_odf` virava só parágrafo, sem caixa e sem
        # QR. Convertemos cada carimbo para `carimbo_compacto_odf` antes.
        imagens_dos_carimbos: dict = {}
        # Sem espaço de assinatura da FICHA no papel da certidão (22/09/2026).
        corpo_limpo = sem_linha_de_assinatura_a_mao(c["corpo"])
        if c["corpo_formato"] == "html":
            corpo_html, frags_carimbo, imagens_dos_carimbos = (
                carimbos_do_html_para_odf(corpo_limpo))
            corpo_odf = html_para_odf(corpo_html, fragmentos=frags_carimbo)
        else:
            corpo_odf = texto_para_odf(corpo_limpo)
        # A LINHA ENTRE OS ATOS SE DESENHA NA IMPRESSAO, e nao ao emitir.
        #
        # O corpo da certidao e CONGELADO com sha256 — e o teor certificado
        # tem de continuar sendo exatamente o que foi certificado. Desenhando
        # aqui, as 369 certidoes ja emitidas ganham a separacao ao serem
        # reimpressas **sem uma letra do teor mudar**.
        #
        # O numero da matricula vem da propria certidao — `matricula_numero`,
        # preenchida em 369 de 369 (medido em 31/08/2026). Sem ele
        # `separar_atos` nao marca nada, que e o certo: rotulo sem matricula
        # para comparar pode ser de outra ficha.
        corpo_odf = separar_atos(corpo_odf, c["matricula_numero"])
        # O MESMO CARIMBO DA FICHA — ordem do oficial em 15/09/2026 —, e
        # **COM O QR**, desde 16/09: «preciso que o carimbo da certidão saia
        # completo com qr code, link, emolumentos».
        #
        #   A chamada passava `None` no lugar do nome da imagem, e das quatro
        #   chamadas deste carimbo na casa esta era a unica assim — a ficha do
        #   cartao de autografo, a certidao do RCPN e a ficha da digitalizacao
        #   sempre passaram a imagem.
        #
        #   UM QR POR SELO: ha certidao com dois, e um QR so poria o codigo do
        #   primeiro debaixo do segundo — conferir o selo errado com cara de
        #   conferido e pior que nao conferir.
        # A ETIQUETA INTEIRA, E NAO O NUMERO — ver `_etiqueta_da_certidao`.
        # E dela que saem os emolumentos que o carimbo imprime.
        #
        # **O CARIMBO COMPLETO, E ELE E O MESMO DAS QUATRO CERTIDOES** —
        # 17/09/2026. A montagem (um QR por selo, as imagens do pacote, a
        # largura inteira) mora em `ri_odt.carimbo_da_certidao_odf`: ela
        # servia so o RI, e agora serve tambem o RCPN de inteiro teor, o
        # Protesto e o RCPJ/RTD, que ate hoje nao tinham carimbo nenhum.
        etiqueta = _etiqueta_da_certidao(c)
        frag_do_selo, imagens_do_selo = carimbo_da_certidao_odf(etiqueta)
        corpo_odf += frag_do_selo
        # Espaço de assinatura à mão ficou só na FICHA (22/09/2026).
        #
        # E O NOME DE QUEM EXPEDIU VOLTOU — 23/09/2026, decisão do oficial.
        # Estava escrito aqui que «a certidão identifica quem expediu no
        # molde», e não identifica: o molde de fábrica termina com quem
        # RESPONDE pela serventia (registrador ou substituta), e a ordem de
        # 16/09 manda constar quem EXPEDIU — o escrevente logado. Sem esta
        # linha o papel saía sem ele. Volta o nome e o título, e o branco da
        # caneta continua fora (`_assinatura_de_quem_emitiu` não o abre mais).
        _quem_emit = ""
        try:
            _quem_emit = str(c["emitida_por_nome"] or "").strip()
        except (KeyError, IndexError, TypeError):
            _quem_emit = ""
        _assin_odf = _assinatura_de_quem_emitiu(c)
        if _assin_odf and not _corpo_ja_traz_quem_emitiu(
                c["corpo"] if "corpo" in c.keys() else None, _quem_emit):
            corpo_odf += _assin_odf

        # Inteiro teor por TEXTO: cabecalho do cartorio, sem moldura — pedido
        # 16/09/2026 (compacto). Em 23/09/2026 ele disse «o cabeçalho não está
        # completo» e aprovou em imagem o COMPLETO (República, Estado, Comarca,
        # Serventia, endereço, contato, titular, substituta, CNS), o mesmo da
        # certidão do Livro 3. Nao usa a grade RI_CABECALHO da ficha.
        from ri_odt import cabecalho_certidao_completo_odf
        cab_odf = ""
        cab_imgs: dict = {}
        # HOTFIX-2026-10-09-03 (pedido da Carla, 09/10/2026, onus da 1771):
        # o timbre completo vale tambem para ONUS e PROPRIEDADE por TEXTO, e
        # nao so para o inteiro teor. Calculado na impressao: as ja emitidas
        # ganham o timbre ao reimprimir, sem mudar o corpo congelado.
        # HOTFIX-2026-10-09-05 (Carla, 09/10/2026, negativa de imovel sem
        # timbre): o timbre completo vale para TODO tipo de certidao RI por
        # TEXTO (inteiro teor, onus, propriedade, negativa de imovel,
        # dominial...), e nao para uma lista que esquece o tipo novo.
        if True:
            try:
                sv = dados_serventia(db.get_settings)
                cab_odf, cab_imgs = cabecalho_certidao_completo_odf(sv)
            except Exception:
                cab_odf, cab_imgs = "", {}
        # AS IMAGENS DO CABECALHO E AS DO SELO VAO NO MESMO PACOTE: o
        # `.odt` e um zip so, e uma segunda chamada sobrescreveria a primeira.
        todas_as_imagens = dict(cab_imgs or {})
        todas_as_imagens.update(imagens_dos_carimbos)
        todas_as_imagens.update(imagens_do_selo)
        if cab_odf:
            arquivo = gerar_odt(
                corpo_odf,
                cabecalho_odf=cab_odf,
                imagens=todas_as_imagens or None,
                cabecalho_altura_min="2.0cm",
                cabecalho_margem_baixo="0.25cm",
                cabecalho_borda=False)
        else:
            arquivo = gerar_odt(corpo_odf, imagens=todas_as_imagens or None)

        audit("RI_CERTIDAO_IMPRESSA", "RI_CERTIDAO", certidao_id,
              {"numero": c["numero"], "ano": c["ano"]})
        return IMPW.resposta_do_papel(
            arquivo, nome=f'certidao-{c["numero"]}-{c["ano"]}',
            get_setting=db.get_setting, voltar_para=url_for("ri_certidoes"))


    def encerrar_prenotacao_do_ato_apos_arquivamento(con, ato_id: int) -> dict | None:
        """Depois do selo 16.39 ok: encerra a prenotação amarrada ao ato. ESCREVE.

        Pedido da substituta em 23/09/2026: arquivamento = título esgotado para
        aquela prenotação. Diferente de `amarrar_prenotacao`, que NÃO encerra no
        primeiro ato (fica aberta para atos sucessivos do mesmo título). Aqui o
        gatilho é só o arquivamento.

        NÃO FALHA O FLUXO: sem protocolo no ato, protocolo inexistente, ou já
        encerrado — devolve None / recado e segue. Não mexe em selos.
        """
        bd = banco(con)
        row = bd.um(
            "SELECT protocolo FROM ri_atos WHERE id=%s", (int(ato_id),)
        )
        if not row:
            return None
        bruto = str(row["protocolo"] or "").strip()
        if not bruto:
            return None
        dig = "".join(ch for ch in bruto if ch.isdigit())
        # Le a situacao e grava na MESMA linha: o `FOR UPDATE` faz o segundo
        # arquivamento esperar o primeiro e ler «já encerrada», em vez de
        # contar ao balcao que encerrou o que outro ja tinha encerrado.
        bd._escrita()
        linha = bd.um(
            """SELECT id, numero, situacao FROM ri_protocolos
                WHERE CAST(numero AS TEXT)=%s
                   OR REPLACE(CAST(numero AS TEXT), '.', '')=%s
                ORDER BY id DESC LIMIT 1 FOR UPDATE""",
            (bruto, dig or bruto),
        )
        if linha is None:
            return {"achou": False, "numero": bruto}
        if str(linha["situacao"] or "") != "ABERTO":
            return {
                "achou": True,
                "numero": linha["numero"],
                "ja_encerrada": True,
                "situacao": linha["situacao"],
            }
        bd.escrever(
            """UPDATE ri_protocolos
                  SET situacao='ENCERRADO',
                      situacao_anterior=COALESCE(situacao_anterior, situacao)
                WHERE id=%s AND situacao='ABERTO'""",
            (int(linha["id"]),),
        )
        return {
            "achou": True,
            "numero": linha["numero"],
            "encerrou": True,
            "protocolo_id": int(linha["id"]),
        }

    def recado_do_encerramento_por_arquivamento(r) -> str:
        """Frase curta para o flash após arquivamento. Só calcula."""
        if not r:
            return ""
        if r.get("encerrou"):
            return (f" Prenotação {r['numero']} ENCERRADA pelo arquivamento.")
        if r.get("ja_encerrada"):
            return (f" Prenotação {r['numero']} já estava "
                    f"{str(r.get('situacao') or '').lower()}.")
        if r.get("achou") is False:
            return ""
        return ""

    def amarrar_prenotacao(con, protocolo_escrito, *, matricula_id, ato_id):
        """Liga a prenotacao ao primeiro ato que saiu dela. ESCREVE.

        O DEBITO QUE ISTO PAGA, do backlog de agosto: «prenotacao nao vinculada
        ao ato lavrado». Medido no banco de producao: `ri_protocolos.ato_id`
        NULL em **784 de 784**, e `matricula_id` tambem.

        POR QUE ISSO IMPORTA, e nao e cadastro: a prenotacao e o que garante a
        PRIORIDADE do titulo — Lei 6.015/1973, art. 186. Quando dois titulos
        disputam o mesmo imovel, a pergunta e qual prenotacao veio antes **e
        qual ato saiu dela**. Sem a ligacao, a segunda metade se responde a mao,
        comparando datas e teores.

        NAO ENCERRA A PRENOTACAO NO LAVRAR. Pedido da substituta em 23/09/2026:
        um titulo de dominio (e o georreferenciamento, e o destaque) gera AV de
        destaque, abertura, R-01, AV-02 e atos sucessivos na mesma prenotacao.
        Encerrar no primeiro ato sumia a 11.548 da lista e travava a
        continuidade. O balcao ainda encerra na ficha do protocolo; e, a partir
        de 23/09/2026, o selo de arquivamento (16.39) tambem encerra — ver
        `encerrar_prenotacao_do_ato_apos_arquivamento`. O lavrar em si nao fecha.

        NAO DERRUBA O ATO. Protocolo digitado errado, ou de outra serventia, ou
        de um titulo que ja fechou — nada disso pode impedir a lavratura: o ato
        e o que importa, e a amarracao e o registro dele. Devolve o que
        aconteceu, para a tela contar.

        E NAO REABRE O QUE JA FECHOU: so amarra protocolo ABERTO, e so se ele
        ainda nao tem ato. O primeiro ato guarda a prioridade; os seguintes
        usam a mesma prenotacao aberta sem roubar esse elo.
        """
        numero = str(protocolo_escrito or "").strip()
        if not numero:
            return None
        bd = banco(con)
        # `numero` e inteiro no banco: o que nao e numero nao acha prenotacao
        # nenhuma (o SQLite comparava e nao achava; o PostgreSQL recusaria).
        #   LE E GRAVA A MESMA LINHA, e o `FOR UPDATE` a segura ate o fim da
        #   transacao: sem o BEGIN IMMEDIATE do SQLite, dois atos lavrados ao
        #   mesmo tempo passariam os dois pelo `ato_id` vazio, e o segundo
        #   roubaria do primeiro o elo da prioridade.
        #   E O NUMERO TEM TAMANHO (`numero_digitado`, LD10): o que nao cabe
        #   no banco nao acha prenotacao nenhuma, em vez de derrubar a rota.
        linha = None
        procurado = numero_digitado(numero)
        if procurado is not None:
            bd._escrita()
            linha = bd.um(
                """SELECT id, situacao, ato_id FROM ri_protocolos
                    WHERE numero = %s ORDER BY id DESC LIMIT 1 FOR UPDATE""",
                (procurado,))
        if linha is None:
            return {"achou": False, "numero": numero}
        # «Título registrado» no Acompanhamento do ONR: o ato que citou esta
        # prenotação ABERTA (o gancho confere a situação), na transação do ato.
        # Sobe só depois do selo — `onr_acompanhamento.conferir_o_fato`.
        ACOMP.anotar_registro(bd, int(linha["id"]), ato_id=int(ato_id), agora=db.now())
        if linha["ato_id"]:
            return {"achou": True, "numero": numero, "ja_tinha_ato": True}
        if str(linha["situacao"] or "") != "ABERTO":
            return {"achou": True, "numero": numero,
                    "situacao": linha["situacao"]}
        bd.escrever(
            """UPDATE ri_protocolos
                  SET ato_id = %s, matricula_id = COALESCE(matricula_id, %s)
                WHERE id = %s""", (ato_id, matricula_id, linha["id"]))
        return {"achou": True, "numero": numero, "amarrou": True}

    def recado_da_prenotacao(r) -> str:
        """O que a tela diz sobre a amarracao. So calcula.

        CADA CASO TEM A SUA FRASE, e nenhuma delas e «erro»: digitar um
        protocolo que nao existe e engano de digitacao, e o escrevente conserta
        na hora se souber. Silencio aqui deixaria a prenotacao aberta para
        sempre sem ninguem ver.
        """
        if not r:
            return ""
        if r.get("amarrou"):
            return (f" A prenotação {r['numero']} ficou amarrada a este ato e "
                    f"permanece aberta para os atos seguintes do mesmo título. "
                    f"Encerre na ficha do protocolo quando o título estiver "
                    f"esgotado.")
        if not r.get("achou"):
            return (f" O protocolo {r['numero']} ficou anotado no ato, mas não "
                    f"existe prenotação com esse número — confira o que foi "
                    f"digitado.")
        if r.get("ja_tinha_ato"):
            return (f" A prenotação {r['numero']} já estava amarrada ao "
                    f"primeiro ato (prioridade) e continua aberta: use-a nos "
                    f"atos seguintes do mesmo título.")
        return (f" A prenotação {r['numero']} está "
                f"{str(r.get('situacao') or '').lower()} e não foi amarrada.")

    @app.route("/registro-imoveis/<int:matricula_id>/cnm", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_gravar_cnm(matricula_id: int):
        """Grava o CNM calculado numa matrícula antiga que não o tinha. ESCREVE.

        NÃO SOBRESCREVE O QUE JÁ ESTÁ LÁ. O código do acervo é o que a casa
        emitiu; se ele divergir do calculado, quem manda é o emitido — e a
        divergência é assunto para o oficial, não para um `UPDATE`.
        """
        m = q1("SELECT * FROM ri_matriculas WHERE id=%s", (matricula_id,))
        if not m:
            abort(404)
        if (m["cnm"] or "").strip():
            flash("Esta matrícula já tem CNM gravado.", "warning")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))
        codigo = _cnm_da_matricula(m["livro_norm"], m["numero"])
        if not codigo:
            flash("Não foi possível montar o CNM — confira o CNS da serventia "
                  "em Administrativo → Configurações e o número da matrícula.",
                  "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))
        with db.transaction() as con:
            banco(con).escrever("UPDATE ri_matriculas SET cnm=%s WHERE id=%s "
                        "AND COALESCE(cnm,'')=''", (codigo, matricula_id))
        audit("RI_CNM_GRAVADO", "RI_MATRICULA", matricula_id, {"cnm": codigo})
        flash(f"CNM {codigo} gravado. Ele não foi inventado: é o CNS, o livro "
              f"e o número desta matrícula, com o verificador que reproduz os "
              f"1.656 códigos que esta casa já emitiu.", "success")
        return redirect(url_for("ri_ficha", matricula_id=matricula_id))

    @app.route("/registro-imoveis/certidoes/<int:certidao_id>/cancelar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def ri_cancelar_certidao(certidao_id):
        """Cancela a certidão emitida. ESCREVE. O teor fica.

        A MESMA ROTA SERVE ÀS DUAS TELAS, e quem cancela volta para onde estava
        — relato #81, 17/09/2026. O formulário da lista de certidões e o da
        ficha da matrícula postam os dois aqui; sem o `voltar`, quem cancelava
        da ficha era jogado na lista e perdia o imóvel que estava conferindo.

        O destino é uma ESCOLHA ENTRE DUAS, e não um endereço que vem de fora:
        só a palavra `ficha` desvia, e qualquer outra coisa volta para a lista.
        Campo de redirecionamento livre é porta aberta, e esta rota mexe no
        registro de um papel que já está na mão de alguém.
        """
        certidao = q1("SELECT * FROM ri_certidoes WHERE id=%s", (certidao_id,))
        if not certidao:
            abort(404)
        # `matricula_id` vazio cai na lista: certidão órfã não tem ficha para
        # onde voltar, e um `url_for` sem id estouraria na cara do balcão.
        para_a_ficha = (request.form.get("voltar") == "ficha"
                        and certidao["matricula_id"])

        def de_volta():
            if para_a_ficha:
                return redirect(url_for("ri_ficha",
                                        matricula_id=certidao["matricula_id"]))
            return redirect(url_for("ri_certidoes"))

        if int(certidao["cancelada"] or 0):
            flash("Esta certidão já está cancelada.", "warning")
            return de_volta()
        motivo = (request.form.get("motivo") or "").strip()
        # A RÉGUA DO MOTIVO É COMPARTILHADA — relato #81, 17/09/2026. O RCPN
        # exigia dez letras e o RI exigia as mesmas dez escritas de novo, aqui
        # dentro: dois números iguais em dois arquivos divergem no primeiro
        # conserto, e o que diverge é o campo que explica o cancelamento.
        if CANC.motivo_curto(motivo):
            flash(CANC.MOTIVO_CURTO, "danger")
            return de_volta()
        if not CANC.declaracao_confirmada(
                request.form.get("selo_cancelado_tjma")):
            flash(CANC.MENSAGEM_DECLARACAO_OBRIGATORIA, "danger")
            return de_volta()
        quando = db.now()
        # O NOME, E NÃO O LOGIN — correção de 17/09/2026, e ela só apareceu
        # porque a ficha passou a MOSTRAR este campo.
        #
        #   A rota gravava `_usuario_atual()`, que devolve o login («mario»).
        #   `emitida_por_nome`, na linha de cima da mesma tabela, grava o nome
        #   («MARIO EXEMPLO DOS SANTOS») — e é o nome o que a certidão imprime
        #   embaixo da assinatura. Duas convenções na MESMA linha é como elas
        #   divergem, e quem lê anos depois pergunta «quem cancelou isto?»: o
        #   login não responde. É a régua do rastro da minuta e da reabertura,
        #   e é a mesma do RCPN (`usuario_nome()`), que o relato #81 mandou
        #   imitar.
        #
        #   O `_usuario_atual()` continua valendo onde ele nasceu: a ata do
        #   expurgo e o rascunho.
        quem = (app.extensions["usuario_nome"]() or "").strip() or None
        with db.transaction() as con:
            banco(con).escrever(
                """UPDATE ri_certidoes
                      SET cancelada=1, motivo_cancelamento=%s, cancelada_em=%s,
                          cancelada_por=%s, declaracao_selo_tjma_em=%s,
                          declaracao_selo_tjma_por=%s
                    WHERE id=%s""",
                (motivo, quando, quem, quando, quem, certidao_id))
            resultado = CANC.concluir(
                con, tabela="ri_certidoes", ato_id=certidao_id,
                motivo=motivo, agora=quando, usuario=quem)
        audit("RI_CERTIDAO_CANCELADA", "RI_CERTIDAO", certidao_id,
              {"motivo": motivo, "declaracao_selo_tjma": True,
               **resultado})
        folhas = resultado.get("folhas_recuperadas") or []
        recado = (f" Folha(s) {', '.join(folhas)} devolvida(s) ao estoque."
                  if folhas else "")
        flash("Certidão cancelada. O registro permanece no livro, com o motivo."
              + recado, "warning")
        return de_volta()

    @app.route("/registro-imoveis/importar", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_importar():
        """Carga do acervo pela propria interface.

        Roda dentro do servidor, entao usa a mesma conexao e o mesmo travamento
        do SQLite que o resto do sistema - diferente de mexer no arquivo por fora,
        que com o WAL ativo arriscaria corromper o banco.
        """
        atual = q1("""SELECT
            (SELECT COUNT(*) FROM ri_matriculas WHERE origem='EOFICIO') matriculas,
            (SELECT COUNT(*) FROM ri_atos WHERE origem='EOFICIO') atos,
            (SELECT COUNT(*) FROM ri_partes WHERE origem='EOFICIO') partes,
            (SELECT COUNT(*) FROM ri_protocolos WHERE origem='EOFICIO') protocolos,
            (SELECT COUNT(*) FROM ri_cnib_ordens) cnib,
            (SELECT COUNT(*) FROM ri_matriculas WHERE origem='MANUAL') manuais,
            (SELECT COUNT(*) FROM ri_atos WHERE origem='MANUAL') atos_manuais""")

        pasta_da_casa = app.extensions["pasta_da_casa"]

        def _da_casa(candidata: dict) -> bool:
            try:
                pasta_da_casa(candidata["caminho"])
                return True
            except PDC.ForaDaCasa:
                return False

        if request.method == "GET":
            # A tela só oferece a pasta que a importação aceita (LX12): uma
            # sugestão que o POST recusaria é um clique para nada.
            return render_template("ri_importar.html", atual=atual,
                                   candidatas=[c for c in procurar_exportacoes()
                                               if _da_casa(c)])

        # SÓ PASTA DA CASA (LS02 A3; LX12, 19/10/2026). O teor HTML que esta
        # carga grava é o que a ficha mostra (o C6 do LS02 entrava por aqui),
        # e `\\maquina\x` levava o servidor, como SYSTEM, à rede.
        try:
            pasta = pasta_da_casa((request.form.get("pasta") or "").strip())
        except PDC.ForaDaCasa as recusa:
            flash(str(recusa), "danger")
            return redirect(url_for("ri_importar"))
        if not (pasta / "matriculas.jsonl").exists():
            flash(f"Não encontrei matriculas.jsonl em {pasta}. "
                  f"Confira o caminho da pasta exportada.", "danger")
            return redirect(url_for("ri_importar"))

        substituir = request.form.get("substituir") == "1"
        if substituir:
            uid = session.get("user_id")
            u = db.get_user(int(uid)) if uid else None
            papel = (u["role"] if u else "") or ""
            if papel not in ("ADMIN", "MANAGER"):
                flash("Substituir a carga anterior continua restrito ao "
                      "administrador ou gerente. Para importar matrícula sem "
                      "apagar carga anterior, deixe essa opção desmarcada.",
                      "danger")
                return redirect(url_for("ri_importar"))
        if (atual["matriculas"] or atual["protocolos"] or atual["cnib"]) and not substituir:
            flash("Já existe carga anterior do E-Ofício. Marque a opção de substituir "
                  "para refazer, ou o acervo entraria em duplicidade.", "danger")
            return redirect(url_for("ri_importar"))

        import shutil
        from ri_import import Importador

        # O NÚMERO DE QUEM CARREGA, E NÃO O NOME (19/10/2026). O Importador o
        # grava em ri_importacoes.usuario_id, ri_matriculas.criado_por,
        # ri_atos.lavrado_por e ri_numeracao.fixado_por — as quatro são id de
        # `users`. Com o nome, o SQLite aceitava (as 2.014 matrículas da carga
        # antiga ficaram com o nome em `criado_por`); no PostgreSQL a coluna é
        # bigint e a carga inteira cai na primeira linha.
        usuario_id = app.extensions["usuario_id"]()
        # Copia de seguranca antes de mexer: snapshot consistente pelo proprio SQLite.
        # Fora da pasta do banco — ordem do oficial em 11/10/2026.
        import pasta_das_copias
        marca = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        copia = pasta_das_copias.destino_da_copia(Path(f"antes_carga_RI_{marca}.sqlite3"), Path(db.db_path))
        with db.connect() as origem_con:
            alvo = sqlite3.connect(copia)
            origem_con.backup(alvo)
            alvo.close()

        try:
            with db.transaction() as con:
                if substituir:
                    bd = banco(con)
                    # Preserva o que foi lavrado aqui; remove so o que veio do E-Oficio.
                    bd.escrever("DELETE FROM ri_partes WHERE origem='EOFICIO'")
                    bd.escrever("DELETE FROM ri_atos WHERE origem='EOFICIO'")
                    bd.escrever("DELETE FROM ri_imagens WHERE matricula_id IN "
                                "(SELECT id FROM ri_matriculas WHERE origem='EOFICIO')")
                    bd.escrever("DELETE FROM ri_protocolos WHERE origem='EOFICIO'")
                    # O CNIB TAMBEM TEM AS DUAS ORIGENS DESDE 18/09/2026 — o
                    # atualizador da Central grava `origem='CNIB'`, e so o que
                    # veio do E-Oficio se substitui.
                    #
                    #   Estas duas linhas estavam SEM FILTRO, contra o
                    #   comentario logo acima: apagavam o espelho INTEEIRO a
                    #   cada carga. Nunca apareceu porque as 50.054 ordens de
                    #   hoje sao todas do E-Oficio — e apareceria no dia em que
                    #   a Central trouxesse a primeira ordem nova, levando
                    #   junto as que o atualizador acabou de gravar.
                    #
                    #   As pessoas saem antes das ordens por causa da chave
                    #   estrangeira de `ri_cnib_pessoas.ordem_id`.
                    bd.escrever("DELETE FROM ri_cnib_pessoas WHERE origem='EOFICIO'")
                    bd.escrever("DELETE FROM ri_cnib_ordens WHERE origem='EOFICIO'")
                    bd.escrever("DELETE FROM ri_rejeitados")
                    bd.escrever("DELETE FROM ri_matriculas WHERE origem='EOFICIO'")
                imp = Importador(con, usuario_id)
                relatorio = imp.executar(pasta)
        except Exception as erro:
            audit("RI_IMPORTACAO_FALHOU", "RI_IMPORTACAO", None, {"erro": str(erro)[:400]})
            flash(SEGWEB.recado_de_erro(
                erro, "ri_importar", "A importação falhou e nada foi gravado; "
                "o detalhe ficou no registro do servidor.")
                  + f" O banco anterior está salvo em {copia.name}.", "danger")
            return redirect(url_for("ri_importar"))

        audit("RI_IMPORTACAO", "RI_IMPORTACAO", None, relatorio)
        # AS PRESERVADAS APARECEM, E SO QUANDO EXISTEM. O numero ao lado de
        # «ordens da CNIB» conta o que a carga ESCREVEU; quando a Central ja
        # atualizou uma ordem, o arquivo do E-Oficio nao a sobrescreve, e ela
        # nao entra ali. Dizer so o numero menor, sem a razao, faria o operador
        # procurar um defeito que nao houve — e zero nesta conta nao e novidade,
        # e por isso a frase nao aparece quando nao ha nenhuma.
        preservadas = relatorio.get("cnib_ordens_preservadas", 0)
        nota_cnib = (f" ({preservadas} já atualizadas pela Central e mantidas)"
                     if preservadas else "")
        flash(f"Carga concluída: {relatorio['matriculas_gravadas']} matrículas, "
              f"{relatorio['atos_gravados']} atos, {relatorio['partes_gravadas']} partes, "
              f"{relatorio.get('protocolos_gravados', 0)} protocolos e "
              f"{relatorio.get('cnib_ordens', 0)} ordens da CNIB{nota_cnib}. "
              f"{relatorio['rejeitados']} em quarentena. Cópia de segurança: {copia.name}.",
              "success")
        return redirect(url_for("ri_importacoes"))

    # ------------------------------------------- matriculas digitadas em Word

    @app.route("/registro-imoveis/matriculas-doc", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_matriculas_doc():
        """Confere as matrículas digitadas em Word contra o acervo.

        O arquivo vem do EXTRAIR_MATRICULAS_DOC.cmd, que roda na máquina da
        serventia — os documentos estão numa pasta sincronizada em modo sob demanda e
        não se leem de fora.
        """
        # Fica na pasta de arquivos do sistema, que o backup ja varre.
        raiz = Path(db.get_setting("archive_root", "").strip()
                    or (Path(db.db_path).parent / "arquivos")) / "ri"
        raiz.mkdir(parents=True, exist_ok=True)
        destino = raiz / "matriculas_doc.jsonl"
        pasta = (db.get_setting("ri_pasta_matriculas_doc", "") or "").strip()

        # Ler a pasta e reescrever o JSONL. Antes isto era um .cmd solto que
        # alguem tinha de lembrar de rodar; agora e um botao, e o resultado
        # fica onde o sistema procura.
        if request.method == "POST" and request.form.get("acao") == "extrair":
            escolhida = (request.form.get("pasta") or pasta).strip()
            if not escolhida:
                flash("Informe a pasta onde estão os arquivos digitados.", "danger")
                return redirect(url_for("ri_matriculas_doc"))
            # SÓ PASTA DA CASA (LS02 A3; LX12, 19/10/2026) — a régua de
            # `pastas_da_casa.dentro_da_casa`, a mesma das outras importações.
            try:
                app.extensions["pasta_da_casa"](escolhida)
            except PDC.ForaDaCasa as recusa:
                flash(str(recusa), "danger")
                return redirect(url_for("ri_matriculas_doc"))
            try:
                res = extrair_doc(escolhida, destino)
            except FileNotFoundError as erro:
                flash(f"{erro}", "danger")
                return redirect(url_for("ri_matriculas_doc"))
            except Exception as erro:                     # noqa: BLE001
                flash(SEGWEB.recado_de_erro(
                    erro, "ri_matriculas_doc", "A leitura falhou; o detalhe "
                    "ficou no registro do servidor."), "danger")
                return redirect(url_for("ri_matriculas_doc"))
            if escolhida != pasta:
                db.set_settings({"ri_pasta_matriculas_doc": escolhida})
            audit("RI_DOC_EXTRAIDO", "RI_MATRICULA", None, res)
            aviso = (f"{res['arquivos_lidos']} arquivo(s) lido(s) de "
                     f"{res['numeros']} número(s). {res['descartados']} nome(s) sem "
                     f"número reconhecível e {res['sem_texto']} sem texto.")
            if res["doc_pendentes"]:
                aviso += (f" {res['doc_pendentes']} arquivo(s) .doc ficaram de fora"
                          + ("" if res["libreoffice"] else " — o LibreOffice não foi"
                             " encontrado nesta máquina.") + ".")
            flash(aviso, "success" if not res["doc_pendentes"] else "warning")
            return redirect(url_for("ri_matriculas_doc"))

        arquivo = destino if destino.exists() else None
        if not arquivo:
            achados = procurar_arquivos("matriculas_doc.jsonl")
            arquivo = achados[0] if achados else None
        informado = (request.values.get("arquivo") or "").strip()
        if informado:
            # O ARQUIVO INFORMADO TAMBÉM (LS02 A3; LX12): lê-se qualquer JSONL
            # que o serviço alcance, e por GET — o link basta.
            try:
                arquivo = app.extensions["pasta_da_casa"](informado)
            except PDC.ForaDaCasa as recusa:
                flash(str(recusa), "danger")
                return redirect(url_for("ri_matriculas_doc"))

        if not arquivo or not arquivo.exists():
            return render_template("ri_matriculas_doc.html", arquivo=None, linhas=[],
                                   resumo={}, filtro="", pagina=1, paginas=1,
                                   total=0, pasta=pasta)

        acervo = q("SELECT id, numero, teor, tipo_ficha, conferido, livro FROM ri_matriculas ORDER BY id")
        no_sistema, vistos, ambiguos = {}, set(), set()
        for r in acervo:
            n = str(r["numero"])
            # O mesmo numero em dois livros: cada livro reinicia a numeracao,
            # entao o numero sozinho nao identifica a matricula.
            if n in vistos:
                ambiguos.add(n)
            vistos.add(n)
            no_sistema[n] = dict(r)
        linhas = conferir_doc(arquivo, no_sistema, ambiguos)
        res = resumo_doc(linhas)

        if request.method == "POST" and request.form.get("acao") == "importar":
            escolhidos = set(request.form.getlist("numero"))
            # AMPLIADA entra junto: o texto do sistema esta inteiro dentro do
            # texto do Word, entao substituir acrescenta e nao apaga. DIVERGENTE
            # continua de fora — ali os dois se contradizem.
            novas = [l for l in linhas
                     if l["numero"] in escolhidos
                     and l["situacao"] in ("NOVA", "SO_NO_DOC", "AMPLIADA")]
            if not novas:
                flash("Nenhuma matrícula marcada.", "warning")
                return redirect(url_for("ri_matriculas_doc"))

            gravadas = atualizadas = 0
            with db.transaction() as con:
                bd = banco(con)
                for l in novas:
                    corpo = teor_html_doc(l["texto"])
                    if l["matricula_id"]:
                        # Volta a NAO CONFERIDA: o teor mudou, e conferencia
                        # antiga nao vale para texto novo.
                        bd.escrever("""UPDATE ri_matriculas
                                       SET teor=%s, teor_formato='html',
                                           conferido=0, atualizado_em=%s
                                       WHERE id=%s""",
                                    (corpo, db.now(), l["matricula_id"]))
                        atualizadas += 1
                    else:
                        bd.escrever(
                            """INSERT INTO ri_matriculas
                               (numero, complemento, tipo_ficha, situacao, conferido,
                                livro, livro_norm, teor, teor_formato, observacao,
                                origem, origem_chave, criado_em)
                               VALUES (%s, '', 'ACERVO', 'ATIVA', 0, %s, %s, %s, 'html', %s,
                                       'DOC', %s, %s)""",
                            (l["numero"], "2", "2", corpo,
                             f"Digitada em Word: {l['arquivo']}", l["arquivo"], db.now()))
                        gravadas += 1
            audit("RI_DOC_IMPORTADO", "RI_MATRICULA", None,
                  {"novas": gravadas, "atualizadas": atualizadas})
            flash(f"{gravadas} matrícula(s) criada(s) e {atualizadas} completada(s), "
                  f"todas como NÃO CONFERIDAS. O texto entrou como veio do Word — "
                  f"a conferência contra o livro continua sendo obrigatória.", "success")
            return redirect(url_for("ri_matriculas_doc"))

        filtro = (request.args.get("situacao") or "").strip().upper()
        if filtro:
            linhas = [l for l in linhas if l["situacao"] == filtro]
        # LD13: «abc» e o «²» no endereço eram 500 (o recorte é em Python).
        pagina = max(1, numero_digitado(request.args.get("pagina"),
                                        maximo=PAGINA_MAIS_ALTA) or 1)
        total = len(linhas)
        paginas = max(1, (total + POR_PAGINA - 1) // POR_PAGINA)
        recorte = linhas[(pagina - 1) * POR_PAGINA: pagina * POR_PAGINA]
        for l in recorte:
            l["previa"] = (l["texto"] or "")[:600]
        return render_template("ri_matriculas_doc.html", arquivo=str(arquivo),
                               linhas=recorte, resumo=res, filtro=filtro,
                               pagina=pagina, paginas=paginas, total=total,
                               pasta=pasta)

    # --------------------------------------------------------- delegatarios

    SUGESTAO_DELEGATARIOS = (
        # nome, cargo, tratamento, titulo, inicio, fim, de onde veio a informacao
        # A FORMA DOS DOIS NOMES É A DE 16/09/2026 — ver `database.py`.
        # VAZIA desde 09/10/2026 (sanitização para o código aberto): eram os
        # três nomes desta casa, e eles já estão gravados em `ri_delegatarios`.
        # Instalação nova cadastra os seus pela tela.
    )

    @app.route("/registro-imoveis/delegatarios", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER")
    def ri_delegatarios():
        """Quem respondia pela serventia em cada período.

        É daqui que a ficha tira o nome de quem praticou cada ato antigo. Sem
        período cadastrado, o ato sai sem fecho — de propósito.
        """
        if request.method == "POST":
            acao = request.form.get("acao") or "salvar"

            if acao == "sugerir":
                with db.transaction() as con:
                    bd = banco(con)
                    for nome, cargo, trat, titulo, ini, fim, obs in SUGESTAO_DELEGATARIOS:
                        ja = bd.um("SELECT id FROM ri_delegatarios WHERE nome=%s",
                                   (nome,))
                        if ja:
                            continue
                        bd.escrever(
                            """INSERT INTO ri_delegatarios
                               (nome, cargo, tratamento, titulo, inicio, fim,
                                confirmado, observacao, criado_em)
                               VALUES (%s,%s,%s,%s,%s,%s,0,%s,%s)""",
                            (nome, cargo, trat, titulo, ini or None, fim or None,
                             obs, db.now()))
                audit("RI_DELEGATARIOS_SUGESTAO", "RI_DELEGATARIO", None, {})
                flash("Cadastro inicial criado. Os períodos estão por confirmar — "
                      "enquanto não forem, a ficha sai sem o nome de quem praticou.",
                      "warning")
                return redirect(url_for("ri_delegatarios"))

            if acao == "novo":
                nome = (request.form.get("nome") or "").strip()
                if not nome:
                    flash("O nome é obrigatório.", "danger")
                    return redirect(url_for("ri_delegatarios"))
                with db.transaction() as con:
                    banco(con).escrever(
                        """INSERT INTO ri_delegatarios
                           (nome, cargo, tratamento, titulo, inicio, fim, confirmado,
                            observacao, criado_em)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (nome, request.form.get("cargo") or "TITULAR",
                         request.form.get("tratamento") or "O",
                         (request.form.get("titulo") or "").strip() or None,
                         (request.form.get("inicio") or "").strip() or None,
                         (request.form.get("fim") or "").strip() or None,
                         1 if request.form.get("confirmado") else 0,
                         (request.form.get("observacao") or "").strip() or None,
                         db.now()))
                audit("RI_DELEGATARIO_NOVO", "RI_DELEGATARIO", None, {"nome": nome})
                flash("Delegatário cadastrado.", "success")
                return redirect(url_for("ri_delegatarios"))

            if acao == "excluir":
                did = request.form.get("id")
                with db.transaction() as con:
                    banco(con).escrever("DELETE FROM ri_delegatarios WHERE id=%s", (did,))
                audit("RI_DELEGATARIO_EXCLUIDO", "RI_DELEGATARIO", did, {})
                flash("Removido do cadastro. Atos já lavrados não mudam: o nome "
                      "deles ficou gravado no próprio ato.", "success")
                return redirect(url_for("ri_delegatarios"))

            # salvar em lote
            with db.transaction() as con:
                bd = banco(con)
                for d in delegatarios():
                    pref = f"d{d['id']}_"
                    if not any(k.startswith(pref) for k in request.form):
                        continue
                    bd.escrever(
                        """UPDATE ri_delegatarios SET nome=%s, cargo=%s, tratamento=%s,
                           titulo=%s, inicio=%s, fim=%s, confirmado=%s, observacao=%s
                           WHERE id=%s""",
                        ((request.form.get(pref + "nome") or d["nome"]).strip(),
                         request.form.get(pref + "cargo") or d["cargo"],
                         request.form.get(pref + "tratamento") or d["tratamento"],
                         (request.form.get(pref + "titulo") or "").strip() or None,
                         (request.form.get(pref + "inicio") or "").strip() or None,
                         (request.form.get(pref + "fim") or "").strip() or None,
                         1 if request.form.get(pref + "confirmado") else 0,
                         (request.form.get(pref + "observacao") or "").strip() or None,
                         d["id"]))
            audit("RI_DELEGATARIOS_SALVOS", "RI_DELEGATARIO", None, {})
            flash("Cadastro atualizado.", "success")
            return redirect(url_for("ri_delegatarios"))

        lista = delegatarios()

        # Quantos atos do acervo ja trazem o fecho dentro do proprio teor —
        # e o numero que mostra que nao ha o que cadastrar para o passado.
        # **`SUM()` SOBRE ZERO LINHAS DEVOLVE NULL, E A TELA FAZIA CONTA COM
        # ELE** — achado em 07/09/2026 ao varrer as rotas para outra coisa:
        # `acervo.total - acervo.com_fecho` estourava com
        # «unsupported operand type(s) for -: 'int' and 'NoneType'».
        #
        # **Na produção não aparece**, porque há 1.245 atos com teor; aparece
        # em INSTALAÇÃO NOVA, que é justamente onde ninguém está olhando —
        # e a regra da casa é que instalação nova nasce funcionando.
        #
        # O conserto é no SQL e não na tela: `COALESCE` aqui vale para todo
        # mundo que ler esta consulta, e uma guarda no template deixaria a
        # próxima tela que a usasse com o mesmo defeito.
        acervo = q1("""SELECT COUNT(*) total,
                              COALESCE(SUM(CASE WHEN teor ILIKE '%%ou f%%'
                                                THEN 1 ELSE 0 END), 0)::bigint com_fecho
                       FROM ri_atos WHERE teor IS NOT NULL AND teor <> ''""")
        faixa = q1("""SELECT MIN(data_ato) primeiro, MAX(data_ato) ultimo
                      FROM ri_atos WHERE data_ato IS NOT NULL""")
        return render_template("ri_delegatarios.html", lista=lista, acervo=acervo,
                               faixa=faixa, sugestao=SUGESTAO_DELEGATARIOS)

    # ------------------------------------------------------------------ CTP

    @app.route("/registro-imoveis/ctp", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "AUDITOR")
    # O AUDITOR ve a tela; o que ela GRAVA (POST) exige papel que pratica ato.
    @roles_required("ADMIN", "MANAGER", metodos=("POST",))
    def ri_ctp():
        """CTP — Comunicação de Transações às Prefeituras (CENSEC / CNB-CF).

        Uma carga por competência mensal. A tela mostra TODOS os atos do mês,
        inclusive os que não entram na carga, com o motivo ao lado: ato que
        some da tela é ato que ninguém confere.
        """
        hoje = date.today()
        competencia = (request.values.get("competencia") or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}", competencia):
            competencia = hoje.strftime("%Y-%m")
        cns = db.get_setting("ri_cns", "")
        ibge = codigo_ibge_da_casa(db.get_setting)
        tipo_servico = db.get_setting("ri_ctp_tipo_servico", "1")
        tipo_ato_ctp = db.get_setting("ri_ctp_tipo_ato", "1")

        remessa = q1("SELECT * FROM ri_ctp_remessas WHERE competencia=%s", (competencia,))
        fechada = bool(remessa and remessa["situacao"] == "FECHADA")

        atos = q("""SELECT a.*, m.numero matricula_numero, m.id mid
                    FROM ri_atos a JOIN ri_matriculas m ON m.id = a.matricula_id
                    WHERE a.cancelado = 0 AND substr(a.data_ato, 1, 7) = %s
                    ORDER BY a.data_ato,
                             coalesce(substring(m.numero FROM '^[0-9]+')::bigint, 0),
                             a.numero, a.id""",
                 (competencia,))

        salvos = {r["ato_id"]: r for r in
                  q("SELECT * FROM ri_ctp_itens WHERE competencia=%s", (competencia,))}

        if request.method == "POST" and not fechada:
            acao = request.form.get("acao") or "salvar"

            if acao == "sem_transacoes":
                with db.transaction() as con:
                    banco(con).escrever(
                        """INSERT INTO ri_ctp_remessas
                           (competencia, situacao, quantidade, sem_transacoes,
                            observacao, gerado_em, gerado_por, fechado_em, fechado_por)
                           VALUES (%s, 'FECHADA', 0, 1, %s, %s, %s, %s, %s)
                           ON CONFLICT(competencia) DO UPDATE SET
                             situacao='FECHADA', quantidade=0, sem_transacoes=1,
                             observacao=excluded.observacao,
                             fechado_em=excluded.fechado_em,
                             fechado_por=excluded.fechado_por""",
                        (competencia, (request.form.get("observacao") or "").strip() or None,
                         db.now(), None, db.now(), None))
                audit("RI_CTP_SEM_TRANSACOES", "RI_CTP", None, {"competencia": competencia})
                flash(f"Competência {competencia} fechada como «sem transações no mês». "
                      f"Guarde o comprovante do fechamento na CENSEC.", "success")
                return redirect(url_for("ri_ctp", competencia=competencia))

            # Grava o que foi digitado, ato a ato.
            with db.transaction() as con:
                bd = banco(con)
                for a in atos:
                    pref = f"i{a['id']}_"
                    if not any(k.startswith(pref) for k in request.form):
                        continue
                    dados = {k[len(pref):]: (request.form.get(k) or "").strip()
                             for k in request.form if k.startswith(pref)}
                    operacao = dados.get("operacao") or ""
                    incluir = 1 if request.form.get(f"incluir_{a['id']}") else 0
                    bd.escrever(
                        """INSERT INTO ri_ctp_itens
                           (competencia, ato_id, matricula_id, operacao, dados,
                            incluir, atualizado_em)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT(competencia, ato_id) DO UPDATE SET
                             operacao=excluded.operacao, dados=excluded.dados,
                             incluir=excluded.incluir,
                             atualizado_em=excluded.atualizado_em""",
                        (competencia, a["id"], a["matricula_id"], operacao,
                         json.dumps(dados, ensure_ascii=False), incluir, db.now()))
            salvos = {r["ato_id"]: r for r in
                      q("SELECT * FROM ri_ctp_itens WHERE competencia=%s", (competencia,))}

            if acao == "salvar":
                flash("Dados da CTP guardados.", "success")
                return redirect(url_for("ri_ctp", competencia=competencia))

        # Monta as linhas da tela — e, de quebra, o que iria no arquivo.
        linhas, registros, com_pendencia = [], [], 0
        for a in atos:
            ato = dict(a)
            m = dict(q1("SELECT * FROM ri_matriculas WHERE id=%s", (ato["matricula_id"],)))
            partes = [dict(p) for p in
                      q("""SELECT * FROM ri_partes
                           WHERE ato_id=%s OR (ato_id IS NULL AND matricula_id=%s)
                           ORDER BY id""", (ato["id"], ato["matricula_id"]))]

            salvo = salvos.get(ato["id"])
            dados = json.loads(salvo["dados"]) if salvo and salvo["dados"] else {}
            incluir = bool(salvo["incluir"]) if salvo else True

            sugerida, origem_sugestao = operacao_sugerida(ato)
            if not dados.get("operacao"):
                dados["operacao"] = sugerida
            if not dados.get("data_negocio"):
                dados["data_negocio"] = ato.get("data_ato") or ""

            pendencias = conferir(ato, m, partes, dados) if dados.get("operacao") else []
            entra = bool(incluir and dados.get("operacao") and not pendencias)
            if incluir and dados.get("operacao") and pendencias:
                com_pendencia += 1
            if entra:
                registros.append(montar_registro(ato, m, partes, dados, cns, ibge,
                                                 tipo_servico, tipo_ato_ctp))

            linhas.append({
                "ato": ato, "m": m, "partes": partes, "dados": dados,
                "incluir": incluir, "pendencias": pendencias, "entra": entra,
                "origem_sugestao": origem_sugestao,
                # O QUE A DOI PEDE E A CTP NÃO — a folha do ato, a natureza do
                # título, o valor pago a prazo… (DOI de 09/2026). Mostra-se
                # aqui, pré-preenchido do teor, porque é aqui que se digita.
                "doi": RDOI.com_sugestoes(ato, m, dados),
                "doi_pendencias": (RDOI.pendencias(ato, m, dados)
                                   if dados.get("operacao") else []),
                # Ato herdado do E-Ofício não tem transmitente nem adquirente:
                # a carga veio com todas as partes como "proprietário". A tela
                # precisa dizer isso, senão a pendência parece defeito.
                "acervo": (ato.get("origem") or "") != "MANUAL",
                "rotulo": rotulo_ato(ato["tipo"], ato["numero"], m["numero"]),
            })

        if request.method == "POST" and not fechada and \
                (request.form.get("acao") in ("gerar", "fechar")):
            if not registros:
                flash("Nenhum ato está pronto para entrar na carga.", "warning")
                return redirect(url_for("ri_ctp", competencia=competencia))
            conteudo = gerar_carga(registros, cns, competencia)
            arquivo = nome_ctp(cns, competencia)
            fechar = request.form.get("acao") == "fechar"
            with db.transaction() as con:
                banco(con).escrever(
                    """INSERT INTO ri_ctp_remessas
                       (competencia, situacao, quantidade, sem_transacoes,
                        arquivo_nome, arquivo_hash, conteudo, gerado_em, gerado_por,
                        fechado_em)
                       VALUES (%s,%s,%s,0,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT(competencia) DO UPDATE SET
                         situacao=excluded.situacao, quantidade=excluded.quantidade,
                         sem_transacoes=0,
                         arquivo_nome=excluded.arquivo_nome,
                         arquivo_hash=excluded.arquivo_hash,
                         conteudo=excluded.conteudo,
                         gerado_em=excluded.gerado_em,
                         fechado_em=excluded.fechado_em""",
                    (competencia, "FECHADA" if fechar else "ABERTA", len(registros),
                     arquivo, hashlib.sha256(conteudo.encode("utf-8")).hexdigest(),
                     conteudo, db.now(), None, db.now() if fechar else None))
            audit("RI_CTP_GERADA", "RI_CTP", None,
                  {"competencia": competencia, "registros": len(registros),
                   "fechada": fechar})
            return Response(conteudo.encode("utf-8"), mimetype="application/json",
                            headers={"Content-Disposition":
                                     f'attachment; filename="{arquivo}"'})

        meses = q("""SELECT substr(data_ato, 1, 7) c, COUNT(*) qtd FROM ri_atos
                     WHERE data_ato IS NOT NULL AND cancelado = 0
                     GROUP BY 1 ORDER BY c DESC LIMIT 24""")
        remessas = q("SELECT * FROM ri_ctp_remessas ORDER BY competencia DESC LIMIT 24")

        return render_template(
            "ri_ctp.html", competencia=competencia, linhas=linhas, meses=meses,
            remessa=remessa, remessas=remessas, fechada=fechada, cns=cns, ibge=ibge,
            prontos=len(registros), com_pendencia=com_pendencia,
            TIPO_OPERACAO=TIPO_OPERACAO, FORMA_PAGAMENTO=FORMA_PAGAMENTO,
            TIPO_IMOVEL_CTP=TIPO_IMOVEL_CTP, MOTIVO_SEM_NI=MOTIVO_SEM_NI,
            TIPO_PARTE=TIPO_PARTE_TRANSACIONADA,
            NATUREZA_TITULO_DOI=RDOI.NATUREZA_TITULO)

    # ================================================== DOI — Receita Federal
    #
    # A DOI e a CTP nascem do MESMO dado digitado, guardado em ri_ctp_itens.
    # O que muda e o destinatario, o prazo e a prova: a CENSEC fecha o mes; a
    # Receita devolve recibo. Digitar duas vezes seria pedir para divergirem.
    #
    # A tela e organizada por competencia em ABERTO, e nao pelos atos do mes,
    # porque a inspecao cobra tambem os MESES SEM ATO — e mes vazio nao aparece
    # em lista nenhuma justamente por estar vazio.

    @app.route("/registro-imoveis/doi", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "AUDITOR")
    # O AUDITOR ve a tela; o que ela GRAVA (POST) exige papel que pratica ato.
    @roles_required("ADMIN", "MANAGER", metodos=("POST",))
    def ri_doi():
        """DOI — Declaração sobre Operações Imobiliárias (Receita Federal)."""
        hoje = date.today().isoformat()
        competencia = (request.values.get("competencia") or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}", competencia):
            competencia = hoje[:7]
        cns = db.get_setting("ri_cns", "")
        ibge = codigo_ibge_da_casa(db.get_setting)

        remessa = q1("SELECT * FROM ri_doi_remessas WHERE competencia=%s", (competencia,))
        entregue = bool(remessa and remessa["situacao"] == "ENTREGUE")

        if request.method == "POST" and not entregue:
            acao = request.form.get("acao") or ""
            agora = db.now()

            if acao == "negativa":
                with db.transaction() as con:
                    banco(con).escrever(
                        """INSERT INTO ri_doi_remessas
                           (competencia, situacao, quantidade, negativa, prazo,
                            observacao, gerado_em, entregue_em)
                           VALUES (%s, 'ENTREGUE', 0, 1, %s, %s, %s, %s)
                           ON CONFLICT(competencia) DO UPDATE SET
                             situacao='ENTREGUE', quantidade=0, negativa=1,
                             observacao=excluded.observacao,
                             entregue_em=excluded.entregue_em""",
                        (competencia, NDOI.prazo_de_entrega(f"{competencia}-01"),
                         (request.form.get("observacao") or "").strip() or None,
                         agora, agora))
                audit("RI_DOI_NEGATIVA", "RI_DOI", None, {"competencia": competencia})
                flash(f"Competência {competencia} registrada como mês sem ato "
                      f"imobiliário. Guarde o comprovante do fechamento negativo "
                      f"da DOI-Web junto ao AUDITUS.", "success")
                return redirect(url_for("ri_doi", competencia=competencia))

            if acao == "recibo":
                # O RECIBO É A PROVA DA ENTREGA, e prova sem o que provar não é
                # prova — débito do backlog do balcão: «recibo DOI diz sucesso
                # sem remessa».
                #
                #   O `UPDATE` não conferia se havia remessa daquela
                #   competência. Sem ela, ele mudava **zero linhas** e a tela
                #   dizia «Recibo da DOI registrado» do mesmo jeito. O
                #   escrevente ia embora achando que a obrigação estava
                #   cumprida, e o mês continuava em aberto — e a DOI é
                #   obrigação com multa da Receita Federal.
                #
                #   `rowcount` é a resposta do banco, e não a nossa suposição.
                numero = (request.form.get("recibo") or "").strip()
                if not numero:
                    flash("Informe o número do recibo que a Receita devolveu. "
                          "Recibo sem número não prova entrega nenhuma.",
                          "danger")
                    return redirect(url_for("ri_doi", competencia=competencia))
                with db.transaction() as con:
                    bd = banco(con)
                    bd.escrever(
                        """UPDATE ri_doi_remessas
                              SET situacao='ENTREGUE', recibo=%s, protocolo=%s,
                                  entregue_em=COALESCE(entregue_em, %s)
                            WHERE competencia=%s""",
                        (numero,
                         (request.form.get("protocolo") or "").strip() or None,
                         agora, competencia))
                    quantas = bd.linhas_afetadas
                if not quantas:
                    flash(f"Não há remessa da DOI de {competencia} neste "
                          f"sistema, e por isso o recibo não foi guardado — "
                          f"ele ficaria solto, sem dizer de que arquivo é. "
                          f"Gere a remessa primeiro, e depois anote o recibo.",
                          "danger")
                    return redirect(url_for("ri_doi", competencia=competencia))
                audit("RI_DOI_ENTREGUE", "RI_DOI", None,
                      {"competencia": competencia, "recibo": numero})
                flash(f"Recibo {numero} guardado na remessa de {competencia}.",
                      "success")
                return redirect(url_for("ri_doi", competencia=competencia))

        # ---- monta as declarações a partir do que já foi digitado para a CTP
        atos = q("""SELECT a.*, m.numero matricula_numero
                    FROM ri_atos a JOIN ri_matriculas m ON m.id = a.matricula_id
                    WHERE a.cancelado = 0 AND substr(a.data_ato, 1, 7) = %s
                    ORDER BY a.data_ato,
                             coalesce(substring(m.numero FROM '^[0-9]+')::bigint, 0),
                             a.numero, a.id""",
                 (competencia,))
        salvos = {r["ato_id"]: r for r in
                  q("SELECT * FROM ri_ctp_itens WHERE competencia=%s", (competencia,))}

        # ------------------- AS ESCRITURAS DO TABELIONATO ENTRAM NO MESMO
        #
        # «Consta apenas DOI e CTP no registro de imóveis, deveríamos ter para
        #  as escrituras também, com intercomunicabilidade para que o arquivo
        #  da DOI seja possível gerar único, com tudo da serventia.»
        #                                        — o oficial, 27/08/2026
        #
        # E ele decidiu em 28/08: **um arquivo só, das duas atribuições**. É o
        # que a Receita espera — uma declaração por serventia por mês —, e esta
        # casa tem um CNS só, de ofício único.
        #
        # POR QUE AS DUAS FONTES E NÃO DUAS TELAS: duas telas gerariam dois
        # arquivos e alguém mandaria um só. O prazo é do mês, e quem controla o
        # prazo tem de ver o mês inteiro num lugar.
        # A COMPETENCIA VAI COMO FAIXA DE DATAS, e nao recortando os sete
        # primeiros caracteres dentro do SQL. O recorte de texto no SQL tem
        # teto por modulo em `tests/test_portabilidade.py`, e o teto pegou
        # este — modulo antigo pode diminuir, nunca aumentar.
        #
        # E o varredor conta o ARQUIVO, e nao o codigo: escrever a funcao
        # proibida dentro de um comentario para explica-la ja conta como uso.
        # Foi o que aconteceu comigo aqui, e por isso este comentario a
        # descreve por extenso em vez de escreve-la.
        #
        # A faixa ainda usa o indice de data, que o recorte descartaria.
        ano, mes = int(competencia[:4]), int(competencia[5:7])
        primeiro = f"{ano:04d}-{mes:02d}-01"
        seguinte = (f"{ano + 1:04d}-01-01" if mes == 12
                    else f"{ano:04d}-{mes + 1:02d}-01")
        escrituras = q("""SELECT * FROM nt_atos
                           WHERE tipo = 'ESCRITURA' AND com_imovel = 1
                             AND COALESCE(situacao,'') <> 'SEM_EFEITO'
                             AND data >= %s AND data < %s
                           ORDER BY data, id""", (primeiro, seguinte))

        linhas, registros, impedidas = [], [], []
        for e in escrituras:
            ato = dict(e)
            partes_e = [dict(x) for x in q(
                "SELECT * FROM nt_ato_partes WHERE ato_id=%s ORDER BY id",
                (ato["id"],))]
            # A MONTAGEM E A CONFERÊNCIA DA ESCRITURA MORAM EM
            # `notas_doi.declaracao_da_escritura` desde 22/10/2026: a CTP da
            # CENSEC declara as mesmas escrituras, e o montador é um só.
            reg_e, problemas = NDOI.declaracao_da_escritura(ato, partes_e, cns, ibge)
            rotulo_e = (f"Escritura {ato.get('numero_ordem') or ato['id']}"
                        f" — {ato.get('natureza') or 'sem natureza'}")
            if problemas:
                # NÃO ENTRA, E DIZ O QUE FALTA. Declaração incompleta é recusada
                # pela Receita sem dizer qual linha — e a multa é da serventia.
                impedidas.append({"ato": ato | {"rotulo": rotulo_e},
                                  "problemas": problemas})
            else:
                registros.append(reg_e)
            # A OPERACAO VAI COMO TEXTO PORQUE `TIPO_OPERACAO` E TABELA DE
            # TEXTO. A coluna e INTEGER, e o `11` volta do banco como numero:
            # `TIPO_OPERACAO.get(11)` nao acha nada, e a tela mostrava o
            # codigo cru — «11» na cara de quem confere, em vez de «Compra e
            # venda». Mesma armadilha da afinidade, agora do lado da tela.
            linhas.append({"ato": ato, "m": {"numero": ato.get("doi_matricula")},
                           "dados": {"operacao": str(ato.get("doi_transacao") or "")},
                           "incluir": True, "problemas": problemas,
                           "entra": not problemas, "rotulo": rotulo_e,
                           "do_tabelionato": True})

        for a in atos:
            ato = dict(a)
            salvo = salvos.get(ato["id"])
            dados = json.loads(salvo["dados"]) if salvo and salvo["dados"] else {}
            incluir = bool(salvo["incluir"]) if salvo else True
            m = dict(q1("SELECT * FROM ri_matriculas WHERE id=%s", (ato["matricula_id"],)))
            partes = [dict(p) for p in
                      q("""SELECT * FROM ri_partes
                           WHERE ato_id=%s OR (ato_id IS NULL AND matricula_id=%s)
                           ORDER BY id""", (ato["id"], ato["matricula_id"]))]

            problemas = NDOI.conferir_do_ctp(ato, m, partes, dados)
            # A DECLARAÇÃO DO RI É DO DOI-WEB, E NÃO DA CTP — 22/10/2026. Até
            # aqui saía `montar_registro`, o montador da CENSEC, com serviço
            # «Notarial», sem livro, natureza nem registro, e com a folha da
            # matrícula: ver `ri_doi`. E ela passa pelo layout oficial antes de
            # entrar no arquivo — o que ele recusar, a Receita recusaria.
            if dados.get("operacao"):
                problemas += [NDOI.Impedimento("doi", x)
                              for x in RDOI.pendencias(ato, m, dados)]
            reg = None
            if incluir and dados.get("operacao") and not problemas:
                reg = RDOI.montar(ato, m, partes, dados, cns, ibge)
                problemas += [NDOI.Impedimento("layout", x)
                              for x in RDOI.conferir_layout(reg)]
            entra = bool(incluir and dados.get("operacao") and not problemas)
            if entra:
                registros.append(reg)
            elif incluir:
                impedidas.append({"ato": ato, "problemas": [x.como_dict()
                                                            for x in problemas]})
            linhas.append({"ato": ato, "m": m, "dados": dados, "incluir": incluir,
                           "problemas": problemas, "entra": entra,
                           "rotulo": rotulo_ato(ato["tipo"], ato["numero"],
                                                m["numero"])})

        if request.method == "POST" and not entregue and \
                request.form.get("acao") == "gerar":
            if not registros:
                flash("Nenhuma declaração está pronta. Veja as pendências, ou "
                      "registre o mês como sem ato imobiliário.", "warning")
                return redirect(url_for("ri_doi", competencia=competencia))
            conteudo = NDOI.gerar_carga(registros, cns, competencia)
            arquivo = NDOI.nome_arquivo(cns, competencia)
            with db.transaction() as con:
                banco(con).escrever(
                    """INSERT INTO ri_doi_remessas
                       (competencia, situacao, quantidade, negativa, prazo,
                        arquivo_nome, arquivo_hash, conteudo, gerado_em)
                       VALUES (%s, 'GERADA', %s, 0, %s, %s, %s, %s, %s)
                       ON CONFLICT(competencia) DO UPDATE SET
                         situacao='GERADA', quantidade=excluded.quantidade,
                         negativa=0, arquivo_nome=excluded.arquivo_nome,
                         arquivo_hash=excluded.arquivo_hash,
                         conteudo=excluded.conteudo,
                         gerado_em=excluded.gerado_em""",
                    (competencia, len(registros),
                     NDOI.prazo_de_entrega(f"{competencia}-01"), arquivo,
                     hashlib.sha256(conteudo.encode("utf-8")).hexdigest(),
                     conteudo, db.now()))
            audit("RI_DOI_GERADA", "RI_DOI", None,
                  {"competencia": competencia, "declaracoes": len(registros)})
            return Response(conteudo.encode("utf-8"), mimetype="application/json",
                            headers={"Content-Disposition":
                                     f'attachment; filename="{arquivo}"'})

        # ---- o que ainda deve satisfação à Receita, mês a mês
        com_ato = [r["c"] for r in
                   q("""SELECT substr(data_ato, 1, 7) c FROM ri_atos
                        WHERE data_ato IS NOT NULL AND cancelado = 0
                        GROUP BY 1 ORDER BY c""")]
        resolvidas = {r["competencia"] for r in
                      q("SELECT competencia FROM ri_doi_remessas "
                        "WHERE situacao='ENTREGUE'")}
        em_aberto = NDOI.competencias_em_aberto(com_ato, resolvidas, hoje)

        meses = q("""SELECT substr(data_ato, 1, 7) c, COUNT(*) qtd FROM ri_atos
                     WHERE data_ato IS NOT NULL AND cancelado = 0
                     GROUP BY 1 ORDER BY c DESC LIMIT 24""")
        remessas = q("SELECT * FROM ri_doi_remessas ORDER BY competencia DESC LIMIT 24")

        return render_template(
            "ri_doi.html", competencia=competencia, linhas=linhas, meses=meses,
            remessa=remessa, remessas=remessas, entregue=entregue, cns=cns,
            prontas=len(registros),
            resumo=NDOI.resumo_impedimentos(impedidas),
            em_aberto=em_aberto, hoje=hoje,
            prazo=NDOI.prazo_de_entrega(f"{competencia}-01"),
            esquema_conferido=NDOI.ESQUEMA_CONFERIDO,
            TIPO_OPERACAO=TIPO_OPERACAO)

    @app.route("/registro-imoveis/doi/<competencia>/arquivo")
    @roles_required("ADMIN", "MANAGER", "AUDITOR")
    def ri_doi_arquivo(competencia):
        """Rebaixa o arquivo como foi gerado. O que vale é o que foi entregue."""
        r = q1("SELECT * FROM ri_doi_remessas WHERE competencia=%s", (competencia,))
        if not r or not r["conteudo"]:
            abort(404)
        return Response(r["conteudo"].encode("utf-8"), mimetype="application/json",
                        headers={"Content-Disposition":
                                 f'attachment; filename="{r["arquivo_nome"]}"'})

    @app.route("/registro-imoveis/ctp/<competencia>/arquivo")
    @roles_required("ADMIN", "MANAGER", "AUDITOR")
    def ri_ctp_arquivo(competencia):
        """Rebaixa o arquivo já gerado, exatamente como foi gerado.

        Regerar poderia produzir conteúdo diferente se algum cadastro mudou
        no meio do caminho — e o que vale é o que foi transmitido."""
        r = q1("SELECT * FROM ri_ctp_remessas WHERE competencia=%s", (competencia,))
        if not r or not r["conteudo"]:
            abort(404)
        return Response(r["conteudo"].encode("utf-8"), mimetype="application/json",
                        headers={"Content-Disposition":
                                 f'attachment; filename="{r["arquivo_nome"]}"'})

    # tbRI_TipoImovel do E-Oficio: intID -> descricao.
    TIPO_IMOVEL_EOFICIO = {
        0: "Casa", 1: "Apartamento", 2: "Loja", 3: "Sala/Conjunto", 4: "Terreno/fração",
        5: "Galpão", 6: "Prédio comercial", 7: "Prédio residencial",
        8: "Fazenda/Sítio/Chácara", 9: "Outros",
    }

    @app.route("/registro-imoveis/importacoes", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    # O AUDITOR ve a tela; o que ela GRAVA (POST) exige papel que pratica ato.
    @roles_required("ADMIN", "MANAGER", "USER", metodos=("POST",))
    def ri_importacoes():
        if request.method == "POST" and request.form.get("acao") == "tipo_imovel":
            # A carga do acervo descartou tbRI.intTipoImovel, que esta
            # preenchido em quase todas as matriculas do E-Oficio. Sem ele o
            # Indicador Real do ONR e a CTP saem com o tipo generico.
            #
            # Roda aqui dentro, e nao por script: o banco fica em ProgramData
            # e o servico e quem o abre. Por fora exigiria administrador, e foi
            # justamente ai que a primeira tentativa se perdeu.
            achados = procurar_arquivos("matriculas.jsonl")
            arquivo = achados[0] if achados else None
            if not arquivo:
                flash("Não encontrei o matriculas.jsonl da exportação do E-Ofício. "
                      "Rode o EXPORTAR_RI.cmd antes.", "danger")
                return redirect(url_for("ri_importacoes"))

            por_chave: dict[str, str] = {}
            sem_tipo = 0
            with arquivo.open(encoding="utf-8", errors="replace") as fh:
                for linha in fh:
                    if not linha.strip():
                        continue
                    try:
                        reg = json.loads(linha)
                    except ValueError:
                        continue
                    nome = TIPO_IMOVEL_EOFICIO.get(reg.get("intTipoImovel"))
                    if nome:
                        por_chave[str(reg.get("intChave"))] = nome
                    else:
                        sem_tipo += 1

            alvo = q("""SELECT id, origem_chave FROM ri_matriculas
                        WHERE origem='EOFICIO'
                          AND COALESCE(TRIM(tipo_imovel),'')=''
                        ORDER BY id""")
            pares = [(por_chave[r["origem_chave"]], r["id"])
                     for r in alvo if r["origem_chave"] in por_chave]
            if pares:
                with db.transaction() as con:
                    bd = banco(con)
                    for par in pares:
                        bd.escrever("UPDATE ri_matriculas SET tipo_imovel=%s WHERE id=%s",
                                    par)
            audit("RI_TIPO_IMOVEL_COMPLETADO", "RI_MATRICULA", None,
                  {"atualizadas": len(pares), "sem_tipo_na_origem": sem_tipo})
            flash(f"{len(pares)} matrícula(s) receberam o tipo do imóvel. "
                  f"{len(alvo) - len(pares)} continuam sem tipo — o E-Ofício também "
                  f"não tinha. Nada além desse campo foi tocado.", "success")
            return redirect(url_for("ri_importacoes"))

        sem_tipo = q1("""SELECT COUNT(*) n FROM ri_matriculas
                         WHERE COALESCE(TRIM(tipo_imovel),'')=''""")["n"]
        imps = q("SELECT * FROM ri_importacoes ORDER BY id DESC")
        rej = q("""SELECT entidade, motivo, COUNT(*) qtd FROM ri_rejeitados
                   GROUP BY entidade, motivo ORDER BY qtd DESC, entidade, motivo""")
        detalhe = q("""SELECT * FROM ri_rejeitados ORDER BY id DESC LIMIT 300""")
        # **O PADRÃO DE OUTRO SISTEMA TAMBÉM ENTRA POR AQUI** — as duas
        # espécies do RI (`importar_padrao.py`, relato #31): matrícula e
        # registro do Livro 3, com origem='IMPORTACAO'. É acervo de fora, e
        # não a carga do E-Ofício de cima; a tela mostra os dois, porque quem
        # procura "as importações do RI" não sabe de antemão qual dos dois
        # caminhos gravou um registro específico.
        manuais_matricula = q(
            """SELECT id, numero, livro, folha, criado_em FROM ri_matriculas
               WHERE origem=%s ORDER BY id DESC LIMIT 50""",
            (IMPP.MARCA_DA_ORIGEM,))
        manuais_livro3 = q(
            """SELECT id, numero, natureza, titulo_numero, criado_em
               FROM ra_registros WHERE origem=%s ORDER BY id DESC LIMIT 50""",
            (IMPP.MARCA_DA_ORIGEM,))
        return render_template(
            "ri_importacoes.html", imps=imps, rej=rej, detalhe=detalhe,
            sem_tipo=sem_tipo, manuais_matricula=manuais_matricula,
            manuais_livro3=manuais_livro3)

    # ------------------- o formulário manual (padrão de outro sistema)

    def _chave_manual(especie: str, numero: str) -> str:
        return f"RI-MANUAL:{especie}:{numero}"

    @app.route("/registro-imoveis/importacoes/manual/<especie>",
              methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_importacao_manual(especie):
        """Um registro de cada vez, digitado — sem escrever JSON.

        **É O MESMO CAMINHO DE `importar_padrao.py`**, só que a tela pergunta
        campo por campo em vez de pedir o arquivo pronto: por trás, monta o
        mesmo JSON de um registro só e chama `IMPP.conferir()`/`IMPP.
        importar()` — a mesma régua de "campo desconhecido não passa calado"
        e "conferir não grava" vale aqui, porque é o MESMO módulo, e não uma
        cópia que divergiria no primeiro conserto.

        **Só as duas espécies do RI** — pedido do oficial foi "nas
        importações do RI", e abrir aqui as outras quatro (RCPN, RCPJ/RTD,
        Notas, Protesto) faria esta tela responder por atribuição que não é a
        dela; elas continuam servidas por `/importar-padrao`.
        """
        if especie not in ("RI_MATRICULA", "LIVRO3_REGISTRO"):
            flash("Esta tela só importa matrícula ou registro do Livro 3.",
                  "danger")
            return redirect(url_for("ri_importacoes"))

        with db.connect() as con:
            lista_de_campos = [c for c in IMPP.campos(con, especie)
                              if c["nome"] != "valor_centavos"]
            tem_valor = any(c["nome"] == "valor_centavos"
                           for c in IMPP.campos(con, especie))

        erro = ""
        quadro = None
        texto = ""
        valores_digitados: dict[str, str] = {}

        if request.method == "POST":
            acao = request.form.get("acao", "conferir")
            if acao == "importar":
                texto = request.form.get("texto_pronto", "")
                if not texto.strip():
                    erro = ("Nada para importar — confira o registro de "
                           "novo antes.")
                else:
                    try:
                        with db.transaction() as con:
                            quadro = IMPP.importar(
                                con, texto, agora=db.now(),
                                por=app.extensions["usuario_nome"]())
                        audit("IMPORTACAO_PADRAO_MANUAL", quadro["tabela"],
                              None,
                              {"entraram": quadro["entraram"],
                               "recusados": len(quadro["recusados"])})
                        if quadro["entraram"]:
                            flash(f"Registro importado — entrou em "
                                 f"«{quadro['o_que_e']}».", "success")
                            return redirect(url_for("ri_importacoes"))
                        elif quadro["repetidos"]:
                            flash("Este registro já tinha entrado antes — "
                                 "nada foi gravado de novo.", "warning")
                        else:
                            erro = (quadro["recusados"][0]["porque"]
                                   if quadro["recusados"] else
                                   "O registro foi recusado.")
                    except IMPP.ImportacaoError as e:
                        erro = str(e)
                    except sqlite3.Error as e:
                        erro = SEGWEB.recado_de_erro(
                            e, "ri_importacoes", "O banco recusou o registro; o "
                            "detalhe ficou no registro do servidor.")
            else:
                numero = (request.form.get("campo_numero") or "").strip()
                valores: dict[str, str] = {}
                for c in lista_de_campos:
                    v = (request.form.get(f"campo_{c['nome']}") or "").strip()
                    valores_digitados[c["nome"]] = v
                    if v:
                        valores[c["nome"]] = v
                if tem_valor:
                    valor_reais = (request.form.get("campo_valor_reais")
                                  or "").strip()
                    valores_digitados["valor_reais"] = valor_reais
                    if valor_reais:
                        valores["valor_centavos"] = centavos(valor_reais)
                if not numero:
                    erro = "Informe o «numero» — é ele que vira a chave."
                else:
                    registro = dict(valores)
                    registro["numero"] = numero
                    registro[IMPP.CAMPO_DA_CHAVE] = _chave_manual(
                        especie, numero)
                    texto = json.dumps(
                        {"formato": IMPP.FORMATO, "versao": IMPP.VERSAO,
                         "especie": especie,
                         "de_onde_veio": "Digitado à mão em "
                                        "/registro-imoveis/importacoes",
                         "registros": [registro]}, ensure_ascii=False)
                    try:
                        with db.connect() as con:
                            quadro = IMPP.conferir(con, texto)
                    except IMPP.ImportacaoError as e:
                        erro = str(e)

        modelo = IMPP.MODELOS[especie]
        # **OS VOCABULÁRIOS CONTROLADOS SÃO OS DO MÓDULO DE DOMÍNIO**, e não
        # uma lista escrita de novo aqui — a mesma lição de `campos()`: lista
        # à mão envelhece na tarde em que se escreve.
        vocabularios: dict[str, dict[str, str]] = {}
        if especie == "LIVRO3_REGISTRO":
            vocabularios["natureza"] = RA3.NATUREZAS
            vocabularios["situacao"] = {s: s for s in RA3.SITUACOES}
        elif especie == "RI_MATRICULA":
            vocabularios["tipo_ficha"] = {t: ROTULO_TIPO_FICHA.get(t, t)
                                          for t in RI_TIPO_FICHA}
            vocabularios["situacao"] = {s: s for s in RI_SITUACOES}
        return render_template(
            "ri_importacao_manual.html", especie=especie,
            nome_da_especie=modelo["nome"], campos=lista_de_campos,
            tem_valor=tem_valor, quadro=quadro, erro=erro, texto=texto,
            valores=valores_digitados, vocabularios=vocabularios)


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
