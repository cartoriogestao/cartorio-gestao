from __future__ import annotations

import io
import hashlib
import hmac
import json
import os
import secrets
import socket
import sys
import threading
import webbrowser
import zipfile
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from tempfile import TemporaryDirectory

import modulos as MOD
import titulo_aba as TITULOABA
import nome_humano as NOMEHUM
import centrais_cred as CENTCRED
import impressao_pdf as IMPPDF
import cenprot_web
import resolve_web
import protesto_cobranca_web
import cra21_web
import wa_web
import robo_web
import modulos_ligados as MODLIG
import pastas_da_casa as PDC
import tetos_de_entrada as TETOS
import ri_web
import tarefa_processo as TP
import tarefa_suspensao as TS
from flask import Flask, Response, abort, flash, g, redirect, render_template, request, send_file, session, url_for
import backup as BKP
from waitress import serve

from bd_nativo import banco
from database import Database
from serventia import dados as dados_serventia
from security import new_csrf_token, new_secret_key
import arquivo_visivel as ARQVIS
import html_sem_script as HSS
import login_espera as LESP
import identidade_do_robo as IDR
import seguranca_web as SEGWEB
from storage import hash_file, safe_component, save_upload
from network_discovery import DiscoveryResponder, best_local_ip_for, lan_ipv4_addresses
from update_manager import (
    UpdateError,
    inspect_staged,
    installed_app_dir,
    launch_windows_updater,
    load_staged,
    mark_approved,
    pode_aplicar_sozinho,
    validate_and_stage,
)

APP_NAME = "Gestão Integrada da Serventia"
# O NÚMERO AQUI É O QUE O `/saude` RESPONDE, e ele tem de bater com o do
# `VERSAO.txt` — que é o que o instalador carimba no `install.json`. Em
# 16/09/2026 a 3.6.138 saiu com este literal ainda em 3.6.137, e o reinício do
# servidor avisou «quem respondeu está na versão 3.6.137, e a instalada é
# 3.6.138» sobre uma atualização que tinha funcionado (504 de 505 arquivos
# batendo byte a byte). `tests/test_os_dois_carimbos_da_versao.py` guarda isso.
VERSION = "3.7.4"
# 3.6.286 - 06/10/2026 Release do sandbox para o oficial: centrais (fila/log/trava), A3, editor/motor de modelos, produtividade, selo robo, F10-F12 do RI, SIRC (cancelados)
# 3.6.285 - CENPROT: POST /token com form usuario/senha (x-www-form-urlencoded)
# 3.6.284 - Projetos lista: coluna Atualizado (DD/MM/AA - HH:MM, fuso local)
# 3.6.281 - Modal pós-login: X circular (hover/focus); grade avisos sem borda externa
# 3.6.280 - Configurações: Política de senhas — form-row no mínimo de caracteres
# 3.6.279 - CRA diagnóstico: `<erro>` no `<return>` não conta como lista OK
# 3.6.277 - Configurações/CRA API: selects em form-row (rótulo ao lado)
# 3.6.276 - Configurações: layout legível (form-grid ~22rem, Centrais)
# 3.6.275 - Remessa CRA: copy alinhada (TXT 600 pos + XML conferir/receber)
# 3.6.274 - CRA API: botão Testar ligação na mesma linha do ambiente
# 3.6.273 - CRA API: layout legível (selects, consultas agrupadas, CSS escopado)
# 3.6.272 - CRA slice 4: E2E TXT (pytest) + tela CRA alinhada pós-medicao Conf/Retorno
# 3.6.271 - CRA slice 3: envio automático Confirmação/Retorno SOAP (sandbox)
# 3.6.270 - CRA slice 2: recepção XML + origem_xml_* na transação do lote
# 3.6.269 - CRA slice 1: origem_xml_* em pt_remessas + SOAP &quot; em cra21_api
# 3.6.268 - REURB tipo S/E/MISTO + isento auto REURB-S (prenot/atos RI)
# 3.6.260 - avisos admin: checkbox-label + secao recorrencia agrupada
# 3.6.255 — 29/09/2026 Avisos UI: remove texto redundante «só ADMIN encerra» (detalhe/lista).
# 3.6.254 — 29/09/2026 Avisos v2 sandbox: faixas vermelha/verde acima do título; recorrência importante; layout compacto global.
# 3.6.252 — 29/09/2026 Avisos admin: lista unificada /avisos; ativar/desativar; UI form/lista.
# 3.6.251 — 29/09/2026 Avisos: sem badge topbar; admin IMPORTANTE; form novo.
# 3.6.249 — 29/09/2026 Aviso disputa de escrita compacto (Ver detalhes), como implantação.
# 3.6.248 — 29/09/2026 Avisos UX: modal fecha ao ir à lista; CRUD título+descrição; sandbox modal todo login.
# 3.6.247 — 29/09/2026 Remove overlay FERJ/FERC fixo; só módulo nu_avisos (ADMIN).
# 3.6.246 — 29/09/2026 Módulo avisos ADMIN (CRUD) + /avisos + modal/dispensa diária + barra N.
# 3.6.245 — 29/09/2026 Aviso FERJ/FERC: ADMIN PAGO (global) vs Dispensar aviso (só admin); USER Avisei (só user).
# 3.6.243 — 29/09/2026 Aviso overlay FERJ/FERC (segunda 08h; sandbox/teste; dispensa user/admin).
# 3.6.242 — 29/09/2026 CGU fila Ajuda #72–#110 (tarefas #107–#110, RI #85–#89, inventário #73): espelho sandbox→oficial.
# 3.6.241 — 29/09/2026 Ajuda: estado dev NECESSARIO_TESTE (badge «Necessário teste») + notas #91–#95.
# 3.6.240 — 28/09/2026 Ajuda #91–#95 sandbox: termo comparecimento autenticidade, folha RCPN obrigatória, CIB rural, busca atos por livro/folha/termo.
# 3.6.239 — 28/09/2026 RCPN HC: PRAZO_DO_EDITAL 5 d (L6015 art. 67 §1º), aviso revisão jurídica na ficha/edital ODT; pytest.
# 3.6.238 — 28/09/2026 RCPN HC↔casamento: CTA lavrar com pré-preenchimento, ficha assento→HC, anti-duplicidade assento; pytest fluxo.
# 3.6.237 — 28/09/2026 RCPN casamento: seed HC celebrada `ensaio-revisao-modular-rcpn-casamento-habilitacao` ligada ao assento modular; pytest + E2E sandbox.
# 3.6.236 — 28/09/2026 RCPN casamento: ensaio idempotente `ensaio-revisao-modular-rcpn-casamento`, termo congelado + certidão resumo; testes E2E sandbox.
# 3.6.235 — 28/09/2026 RCPN nascimento: ensaio idempotente `ensaio-revisao-modular-rcpn-nascimento`, termo congelado + certidão; testes E2E sandbox.
# 3.6.232 — 28/09/2026 RCPN óbito: ensaio idempotente `ensaio-revisao-modular-rcpn-obito`, termo congelado + certidão resumo; testes E2E sandbox.
# 3.6.231 — 28/09/2026 Notas atas: Jinja `testemunhas` no preenchimento; ensaio idempotente NT-ATA-NOTARIAL + testes E2E sandbox.
# 3.6.230 — 28/09/2026 Notas procurações: fecho legal nos modelos SISTEMA (não «escritura»); ensaio idempotente NT-PROC-PUBLICA (#3) + testes E2E sandbox.
# 3.6.229 — 27/09/2026 Livro 2 L2-CERT-01: certidões RI ensaio alinhadas ao molde RI_CERTIDAO.
# 3.6.228 — 27/09/2026 Livro 3 L3-CERT-01: emissão/reemissão certidão usa o mesmo molde da prévia (`claros_certidao_livro3`); ensaio #2 remonta teor; HIPOTECA em `RA.NATUREZAS`.
# 3.6.227 — 27/09/2026 Livro 3 P2: modelos ficha/certidão mais completos; ensaio registro HIPOTECA alinhado à prévia.
# 3.6.226 — 27/09/2026 Notas: minuta/traslado/termo sem repetir o nome do ato no início do teor.
# 3.6.225 — 26/09/2026 Livro 3: editor de modelos (ficha/certidão) com prévia ao vivo em `/livro3/modelos`.
# 3.6.224 — 26/09/2026 Modelos: visualização real ao editar em `/modelos` (prévia ao vivo).
# 3.6.223 — 26/09/2026 Modelos: deep link `?editar=` resolve atribuição e rola ao editor.
# 3.6.222 — 26/09/2026 Modelos: acesso USER alinhado (menu + submódulos), filtro atribuição na edição.
# 3.6.221 ? 26/09/2026 Modelos: cat?logo por atribui??o (`modelos_papeis`) + seed ensaio AT/PT.
# 3.6.219 — 26/09/2026 RI-01: rota `/ficha.odt` entrega ODF; PDF explícito com `?formato=pdf`.
# 3.6.218 — 26/09/2026 Livro 2 sandbox: selo certidão RI alinhado (#75); seed ri_certidoes ensaio.
# 3.6.217 — 25/09/2026 Pós-CGU: menu bolinha (summary/submenu), cache-bust app.css, ficha RI flex.
# 3.6.204 - 25/09/2026 Beatriz: ficha.odt AttributeError em .get natureza_titulo (contexto_ficha).
# 3.6.212 — 25/09/2026 RI fatia 2 (L3/US/ONR): títulos de aba usucapião; lembrete revisão junto ao selar L3.
# 3.6.211 — 25/09/2026 Livros e acervo revisão: título ficha livro núcleo; importar padrão/RI alinhados ao menu; h1 E-Ofício e implantação.
# 3.6.210 — 25/09/2026 Malote revisão: títulos de aba (inspeções, ficha inspeção, tarefa, prontos encerrar); empty state inspeções.
# 3.6.215 — 25/09/2026 Ajuda/Problemas: filtro ?ambiente= oficial/sandbox (só sandbox :8899).
# 3.6.213 — 25/09/2026 Ajuda/Problemas: id sandbox = id oficial na importação; badge Oficial/Sandbox.
# 3.6.209 — 25/09/2026 RCPN revisão: títulos de aba (ficha, certidões, CPF, papel, averbações, novo).
# 3.6.206 — 25/09/2026 Administrativo revisão: títulos de aba WhatsApp, Robôs e Selador (R1).
# 3.6.205 — 25/09/2026 Protesto revisão: título ficha/novo, instrumentos UTF-8, aviso pendências CENPROT em «A protestar».
# 3.6.204 — 24/09/2026 Notas consulta/livros/DOI: atalhos painel (sinais), link núcleo↔livros, link DOI na ficha.
# 3.6.203 — 24/09/2026 Notas instrumentos: filtros lista atos (em lavratura / sem selo) + atalhos painel.
# 3.6.202 — 24/09/2026 Notas balcão: aviso legal autenticação vs reconhecimento (NT-03).
# 3.6.215 — 24/09/2026 Notas: painel selos pendentes (aut/atos), badges na ficha, roteiro escrituras, aviso import sandbox.
# 3.6.200 — 24/09/2026 Visão geral: KPIs clicáveis, vista VENCIDAS no Malote, painel mais compacto, copy Malote vs atos.
# 3.6.199 — 24/09/2026 ficha RI: menos espaço antes da linha tracejada (atos → termos/certidões); app.css compacto.
# 3.6.198 — 24/09/2026 sync sandbox ↔ oficial: RI P1 do sandbox (certidão de ônus inclui R-;
# CNIB gravada na lavratura; prenotação suspender/retomar prazo; rotas sensíveis do RI só
# ADMIN/MANAGER). A 3.6.194/3.6.195 do sandbox eram outra linha, sem relação com as daqui.
# 3.6.197 — 24/09/2026 Beatriz: certidão inteiro teor — risca entre atos
# em largura total (borda ODF/HTML, não traçinhos pela metade); sem traço/
# espaço de assinatura à mão na certidão (fica só na ficha); nome de quem
# lavrou preservado. Ficha RI também em texto corrido (mat. 4001 OCR);
# multi-selo na impressão; assinatura à mão permanece na ficha.
# 3.6.196 — 24/09/2026 Beatriz: certidão RI — multi-selo do razão (LOTDES/16.5 na 4001) + teor em texto corrido (sem <p> por linha OCR); linha entre atos; vale para todas as certidões RI.
# 3.6.195 — 24/09/2026 Beatriz: multi-selo RI — base/caminho por item (16.5=sem-valor mesmo com valor no ato); completar selos faltantes em ato ja parcialmente selado (AV-01/4001).
# 3.6.194 — 24/09/2026 Beatriz: multi-selo (item+qtd) tambem no lavrar da ficha RI (matricula 4001); antes so em «Selar este ato».
# 3.6.193 — Livro 3: ficha .odt com cabeçalho da serventia (brasão, grade livro/folha/registro) e claros completos no corpo.
# 3.6.192 — Escrituras: selo 16.39 opcional na lavratura; folha 1v/2v no traslado/termo; título único no cabeçalho; depósito na lavratura = baixa no caixa.
# 3.6.191 - 23/09/2026 Beatriz: varios selos por ato RI (ex. 16.22.8.1 + 16.5 x2 no desmembramento).
# 3.6.191 — 23/09/2026 Beatriz: selo 16.39 (arquivamento) encerra a prenotação do ato; 11546 encerrada no DB.

PRIORITIES = ["CRITICA", "ALTA", "MEDIA", "BAIXA"]
TASK_STATUSES = list(TP.SITUACOES)
EXPEDIENT_STAGES = ["RECEBIDO", "TRIADO", "DISTRIBUIDO", "EM_CUMPRIMENTO", "AGUARDANDO_TERCEIRO", "RESPONDIDO", "ARQUIVADO"]

# O EXPEDIENTE E A TAREFA — relato #24 do oficial, 27/08/2026:
#
#   «nao tem botao para encerrar expediente. encerrei a tarefa e o expediente
#    segue ativo.»
#
# Ele estava certo nas duas. HAVIA como encerrar — `update_expediente_stage`
# grava `completed_at` quando a etapa vira RESPONDIDO ou ARQUIVADO —, e o que
# nao havia era BOTAO: a tela oferecia uma caixa com sete nomes de etapa e um
# «Atualizar etapa». Quem procura «encerrar» nao acha «ARQUIVADO» numa lista.
#
# Medido em 29/08/2026: 13 expedientes, TODOS em RECEBIDO, nenhum com data de
# conclusao — e o expediente 6 com a tarefa dele ja CONCLUIDA.
import expediente_tarefa as EXPT
ROLES = ["ADMIN", "MANAGER", "USER", "AUDITOR"]
FREQUENCIES = ["DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "SEMIANNUAL", "ANNUAL"]


def get_data_dir() -> Path:
    override = os.environ.get("CARTORIO_GESTAO_DATA")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform.startswith("win"):
        # Instalacoes convencionais usam ProgramData para que o servidor possa
        # iniciar automaticamente sem depender do usuario logado.
        program_data = os.environ.get("PROGRAMDATA")
        if program_data:
            candidate = Path(program_data) / "CartorioGestao"
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                return candidate
            except OSError:
                pass
        base = Path(os.environ.get("APPDATA", Path.home()))
        return base / "CartorioGestao"
    return Path.home() / ".cartorio_gestao"


def parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_date(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    date.fromisoformat(value)
    return value


def calc_deadline(start: str | None, days: int | None) -> str | None:
    if not start or days is None:
        return None
    return (date.fromisoformat(start) + timedelta(days=days)).isoformat()


def fmt_date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return date.fromisoformat(value[:10]).strftime("%d/%m/%Y")
    except Exception:
        return value


def fmt_dt(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return value


def json_list(value: str, fallback: list[str]) -> list[str]:
    try:
        data = json.loads(value)
        if isinstance(data, list):
            return [str(x) for x in data if str(x).strip()]
    except Exception:
        pass
    return fallback


def create_app(test_config: dict | None = None) -> Flask:
    data_dir = Path((test_config or {}).get("DATA_DIR", get_data_dir()))
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "arquivos").mkdir(parents=True, exist_ok=True)
    # A PASTA `backups` NÃO NASCE MAIS AO LADO DO BANCO — ordem do oficial em
    # 11/10/2026, no dia em que o banco foi apagado no meio das cópias. Quem
    # precisa dela pede `backup_dir()`, que a cria onde `pasta_das_copias` manda.

    secret_file = data_dir / "secret.key"
    if secret_file.exists():
        secret_key = secret_file.read_text(encoding="utf-8").strip()
    else:
        secret_key = new_secret_key()
        secret_file.write_text(secret_key, encoding="utf-8")

    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    app = Flask(
        __name__,
        template_folder=str(bundle_dir / "templates"),
        static_folder=str(bundle_dir / "static"),
    )
    app.config.update(
        SECRET_KEY=secret_key,
        DATA_DIR=data_dir,
        # A VERSAO TAMBEM NA CONFIG, e nao so na variavel do modulo. Um modulo
        # de tela que precise dela — `ajuda_web`, para dizer em que versao o
        # problema aconteceu — nao pode importar `app`: seria import circular.
        VERSION=VERSION,
        MAX_CONTENT_LENGTH=200 * 1024 * 1024,
        # O TETO DOS CAMPOS DE TEXTO DO FORMULÁRIO (sem contar os arquivos,
        # que vão para disco). O Werkzeug 3.1 passou a limitar isso em 500 KB
        # por conta própria e respondia 413 ao escrevente logado que colasse
        # um teor longo — achado colateral da revisão de segurança de
        # 22/10/2026. Dezesseis megabytes cabem o maior teor da casa e
        # continuam sendo um teto; o anônimo tem o dele em `tetos_de_entrada`.
        MAX_FORM_MEMORY_SIZE=16 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)

    db = Database(data_dir / "cartorio_gestao.sqlite3")
    app.extensions["db"] = db
    app.extensions["backup_checked"] = False
    # OS ARQUIVOS DE SEGREDO SÓ PARA O SERVIÇO (LX14; B6 do LS03): a chave do
    # cookie, as chaves dos cofres, os `.cred` e o `servidor.log`. Falhar é
    # aviso no log (`permissao_local`) — o servidor sobe assim mesmo.
    import permissao_local
    permissao_local.proteger_segredos(data_dir)

    def current_user():
        """Quem está logado — e só enquanto o cadastro dele estiver ATIVO.

        DESATIVAR TEM DE TIRAR DA TELA QUEM JÁ ESTÁ NELA (LS01, 19/10/2026).
        A sessão é um cookie assinado que mora no navegador; desativar só
        barrava o PRÓXIMO login (`authenticate`). Quem já estava dentro seguia
        lavrando, gastando selo e lendo o acervo com o usuário desativado —
        e o prazo de inatividade não o tirava, porque cada clique o renovava.
        Desativação é o que a casa faz quando alguém sai; ela vale na hora.
        """
        uid = session.get("user_id")
        user = db.get_user(int(uid)) if uid else None
        if user and not user["active"]:
            return None
        return user

    def carimbo_da_senha(uid) -> str:
        """A versão da credencial que a sessão leva (M3 do LS01, lote LX11).

        REDEFINIR A SENHA NÃO TIRAVA QUEM JÁ ESTAVA DENTRO. Com a senha vazada,
        o ADMIN a redefinia e o cookie de quem entrou com ela seguia valendo até
        a inatividade. A sessão guarda este carimbo no login; a senha nova muda
        o carimbo, e o `before_request` encerra toda sessão com o carimbo
        velho. É um HMAC do hash, com a chave da sessão: o cookie não leva
        nada da senha, nem o hash dela.
        """
        with db.connect() as con:
            linha = banco(con).um("SELECT password_hash FROM users WHERE id=%s",
                                  (int(uid),))
        if not linha:
            return ""
        return hmac.new(secret_key.encode("utf-8"),
                        f"{int(uid)}:{linha['password_hash']}".encode("utf-8"),
                        hashlib.sha256).hexdigest()[:32]

    def prazo_absoluto_horas() -> int:
        """B7: a sessão acaba depois de N horas, mesmo com clique o tempo
        todo — o prazo de inatividade sozinho se renova a cada clique."""
        return max(1, min(24 * 7, parse_int(db.get_setting("session_absolute_hours", "12")) or 12))

    # **PUBLICADA COMO AS OUTRAS QUATRO, E FALTAVA** — achado em 14/09/2026:
    # `retificacao_web.py` passou a pedir `app.extensions["current_user"]`,
    # no mesmo padrão de `usuario_nome`/`usuario_funcao`/`usuario_papel`/
    # `usuario_id` logo abaixo — só que `current_user` em si nunca tinha
    # sido publicada. `create_app()` inteiro quebrava com `KeyError:
    # 'current_user'`, o que derrubaria o sistema todo ao subir, não só
    # uma tela.
    app.extensions["current_user"] = current_user

    # =============================== QUEM PRATICOU O ATO, e em que função
    #
    # O DEFEITO QUE ISTO CORRIGE
    #     Os três módulos — notas, caixa e registro de imóveis — descobriam
    #     quem estava atendendo assim:
    #
    #         getattr(request, "usuario_nome", None) or get_setting("ri_substituta")
    #
    #     Só que NADA NO SISTEMA JAMAIS DEFINIU `request.usuario_nome`. Não é
    #     uma linha que quebrou: é uma linha que nunca existiu. O `getattr`
    #     devolvia None em toda requisição, sempre, e o `or` caía na
    #     substituta do registro de imóveis.
    #
    #     O resultado é que TODO ato novo saía assinado pela mesma pessoa,
    #     qualquer que fosse quem estava logado — e com a função "Escrevente",
    #     porque a busca seguinte procurava no cadastro pelo nome dela e
    #     caía no padrão. Reconhecimento de firma, autenticação de cópia, ato
    #     de livro, recibo, orçamento, protocolo: todos.
    #
    #     Cadastrar a função de cada usuário na tela Usuários não mudava nada,
    #     e não tinha como mudar — o nome que chegava ali nunca era o dele.
    #
    # POR QUE PELO ID DA SESSÃO, E NÃO PELO NOME
    #     A busca antiga era `WHERE full_name=? OR username=?`. Nome não
    #     identifica pessoa: dois escreventes homônimos casam na mesma linha, e
    #     um nome cadastrado com um acento a mais não casa em nenhuma. O id da
    #     sessão é quem a pessoa é.
    #
    # POR QUE UMA IMPLEMENTAÇÃO SÓ
    #     Havia três cópias — `notas_web`, `caixa_web` e `ri_web` — com o mesmo
    #     defeito escrito três vezes. Três cópias de uma regra é a garantia de
    #     que uma delas vai divergir; foi assim que este defeito se espalhou por
    #     todos os documentos que a serventia emite.
    def usuario_nome() -> str:
        """O nome de quem esta logado, para sair no ato.

        NUNCA devolve rotulo de robo/maquina. Em 21/09/2026 tres selos de
        nascimento sairam com escrevente/obtido_por = "Robo Nascimento RCPN"
        — o TJMA recebeu isso como quem praticou o ato. Maquina nao assina.

        E NINGUÉM ASSINA PELA MÁQUINA (23/10/2026, ordem do oficial, «solução
        1»). Até aqui a sessão de robô — ou sem ninguém — caía na substituta
        (`fallbacks_da_casa`), e o ato saía no nome de quem não o praticou: a
        troca que a revisão de segurança de 22/10 (A6) tirou do selo e tinha
        deixado aqui. Agora sai `NOMEHUM.MARCA_PENDENTE`: o ato fica pendente
        de quem assina, e quem selar assina (`ato_selado.vincular_ao_ato`).
        """
        import selo_robo as SR
        user = current_user()
        if user and not SR.usuario_e_robo(user):
            nome = (user["full_name"] or "").strip() or (user["username"] or "").strip()
            humano = NOMEHUM.nome_humano_para_ato(nome)
            if humano:
                return humano
        # Sessão de robô, cadastro com nome de máquina, ou ninguém logado.
        return NOMEHUM.MARCA_PENDENTE
    def usuario_funcao() -> str:
        """A função que a pessoa exerce, na forma da Lei 8.935/94, arts. 20 e 21.

        É o que sai impresso embaixo da assinatura. Não estando cadastrada na
        tela Usuários, cai no padrão da serventia — e a tela Usuários avisa
        quem está sem, porque documento assinado com a função errada é defeito
        de forma do ato, não detalhe de cadastro.
        """
        user = current_user()
        if user:
            funcao = ((user["funcao"] if "funcao" in user.keys() else "") or "").strip()
            if funcao:
                return funcao
        return db.get_setting("serventia_funcao_padrao", "") or "Escrevente"

    # Os módulos de notas, caixa e registro de imóveis pegam daqui. Publicadas
    # ANTES de `registrar_rotas` ser chamado, lá embaixo — é o mesmo objeto,
    # e não uma terceira cópia da regra.
    app.extensions["usuario_nome"] = usuario_nome
    app.extensions["usuario_funcao"] = usuario_funcao
    # O PAPEL de quem esta na tela, para o modulo decidir por acao e nao so
    # por rota. O `roles_required` protege a ROTA inteira; ha tela que o
    # AUDITOR precisa ver e onde ele nao pode praticar ato — a de notas e o
    # caso: ver o ato e conferencia, lancar no livro e gastar folha.
    def usuario_papel():
        # `current_user()` devolve a linha do banco, que NAO tem `.get` — a
        # primeira versao disto era um lambda com `(current_user() or {}).get`
        # e levantava AttributeError em toda requisicao autenticada.
        user = current_user()
        return user["role"] if user else None

    app.extensions["usuario_papel"] = usuario_papel

    # O ID de quem esta na tela, para os anexos: `db.add_attachment` grava quem
    # enviou o arquivo, e quem envia e quem responde por ele. Publicado aqui
    # pelo mesmo motivo dos outros tres — uma implementacao so, e nao uma copia
    # por modulo. As copias locais de `usuario_nome` ja custaram a esta casa
    # todo reconhecimento de firma saindo com o nome da substituta.
    def usuario_id():
        user = current_user()
        return int(user["id"]) if user else None

    app.extensions["usuario_id"] = usuario_id

    def audit(action: str, entity_type: str | None = None, entity_id: int | None = None, details=None):
        user = current_user()
        # QUEM GRAVA SEM NINGUEM LOGADO E O PROPRIO SERVIDOR (26/10/2026, ordem
        # do oficial: todo robo diz quem e e a mando de quem age). E um EVENTO
        # DO SERVIDOR: sem mandante, porque ninguem mandou a requisicao
        # anonima (revisao de seguranca, 26/10). Com conta de robo, a
        # identidade sai da conta (`identidade_do_robo.registrar`).
        ident = {} if user else {"agente": IDR.AGENTE_SERVIDOR}
        db.log(user["id"] if user else None, user["username"] if user else None, action, entity_type, entity_id, details, request.remote_addr if request else None, **ident)

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)
        return wrapped

    def roles_required(*roles, metodos=None):
        """Só estes papéis entram — ou, com `metodos`, só eles GRAVAM.

        `metodos=("POST",)` é para a tela que todo login VÊ e onde só quem
        pratica ato grava (M2 do LS01): o AUDITOR confere a lista de tarefas,
        mas não cria tarefa. O GET dessas rotas segue como era, com o login.
        """
        def deco(view):
            @wraps(view)
            def wrapped(*args, **kwargs):
                user = current_user()
                if not user:
                    return redirect(url_for("login"))
                if (metodos is None or request.method in metodos) and user["role"] not in roles:
                    abort(403)
                return view(*args, **kwargs)
            # OS PAPÉIS FICAM À VISTA NA FUNÇÃO (LX12, 19/10/2026): o
            # `/arquivo/<id>` abre o anexo pela regra da tela que o oferece, e
            # lê a regra daqui — copiar a lista de papéis para lá faria as
            # duas divergirem no dia em que a tela mudar. O `@wraps` de quem
            # embrulhar depois leva o atributo junto.
            wrapped.papeis_exigidos = tuple(roles)
            return wrapped
        return deco

    # QUEM PRATICA ATO — a régua das rotas que o AUDITOR vê e não grava (M2).
    PRATICA = SEGWEB.PRATICA

    def settings_dict():
        s = db.get_settings()
        return s

    def archive_root() -> Path:
        configured = db.get_setting("archive_root", "").strip()
        root = Path(configured).expanduser() if configured else data_dir / "arquivos"
        root.mkdir(parents=True, exist_ok=True)
        return root

    # ONDE OS ARQUIVOS DA CASA MORAM — exposto aos modulos de rota em vez de
    # recalculado neles. **Duas versoes do mesmo caminho divergiriam** no dia em
    # que o oficial mudasse `archive_root` na configuracao, e metade dos anexos
    # iria para a pasta velha sem ninguem ver.
    #
    # **E A EXPOSICAO VEM DEPOIS DA DEFINICAO.** Eu a pus vinte e cinco linhas
    # antes, e toda tela do sistema estourou com «cannot access local variable»:
    # a funcao ainda nao existia naquele ponto. Quem pegou foi o teste de tela,
    # na primeira execucao.
    app.extensions["archive_root"] = archive_root

    def pasta_da_casa(caminho) -> Path:
        """O caminho DIGITADO NA TELA, resolvido, se mora na casa; senão
        `PDC.ForaDaCasa` com a mensagem pronta (LS02 A1–A3, LX12).

        Uma implementação só, publicada como `archive_root`: Assinaturas,
        Importar acervo, Livro 3 e Matrículas digitadas pedem a mesma régua.
        """
        return PDC.dentro_da_casa(caminho, PDC.raizes_da_casa(
            data_dir=data_dir, archive_root=db.get_setting("archive_root", ""),
            importacao=db.get_setting("pastas_de_importacao", "")))

    app.extensions["pasta_da_casa"] = pasta_da_casa

    def backup_dir() -> Path:
        import pasta_das_copias
        return pasta_das_copias.pasta_de_backups(data_dir, db.get_setting("backup_dir", ""))

    def full_backup(target: Path, com_arquivos: bool = True) -> Path:
        """Gera o pacote de backup.

        O COMO ESTA EM `backup.py`, E POR UM MOTIVO.
            Esta funcao vivia aninhada aqui dentro e escrevia DIRETO no nome
            final. O diario do projeto registra, desde a primeira tentativa,
            que backup interrompido assim deixa arquivo corrompido com cara de
            backup bom — e a correcao anotada la nunca chegou a este codigo.

            Agora o modulo grava num `.parcial`, fecha, reabre, confere o zip e
            o SHA-256 do banco, e so entao renomeia. E, por ser modulo, o
            `BACKUP_AGORA.cmd` usa a mesma implementacao: uma so, para nao
            divergirem.
        """
        # A CIFRA E O ACERVO SÃO OPÇÕES DA CASA (LX14), e as duas nascem como
        # era: sem cifra, e com o acervo no completo. A senha da cifra mora no
        # cofre (`backup.cred`), e não no banco — senão viajaria no próprio
        # pacote que ela protege.
        sem_acervo = db.get_setting("backup_completo_sem_acervo", "0") == "1"
        return BKP.gerar_pacote(db, target, archive_root(),
                                com_arquivos=com_arquivos,
                                app_nome=APP_NAME, versao=VERSION,
                                acervo=(None if sem_acervo
                                        else data_dir / "acervo_eoficio.sqlite3"),
                                senha_da_cifra=BKP.senha_da_cifra(data_dir) or None)

    def automatic_backup_once():
        """Backup diario do banco e backup completo semanal.

        Racional: o banco muda todo dia e comprime bem; as digitalizacoes nao
        mudam nunca. Guardar 30 copias identicas de 161 MB gastaria ~4,8 GB
        para proteger exatamente o mesmo conteudo que uma copia ja protege.
        """
        if app.extensions.get("backup_checked"):
            return
        app.extensions["backup_checked"] = True
        if db.get_setting("auto_backup", "1") != "1":
            return

        hoje = date.today()
        pasta = backup_dir()

        diario = pasta / f"backup_banco_{hoje.isoformat()}.zip"
        if not diario.exists():
            try:
                full_backup(diario, com_arquivos=False)
                db.log(None, "SISTEMA", "AUTO_BACKUP_BANCO", "BACKUP", None,
                       {"path": str(diario), "bytes": diario.stat().st_size,
                        "cifrado": BKP.e_cifrado(diario)}, agente="backup automático", a_mando_de=IDR.PELO_RESPONSAVEL)
            except Exception as exc:
                db.log(None, "SISTEMA", "AUTO_BACKUP_FAILURE", "BACKUP", None,
                       {"error": str(exc), "tipo": "banco"}, agente="backup automático", a_mando_de=IDR.PELO_RESPONSAVEL)

        # Completo no dia da semana configurado (padrao: domingo), uma vez por semana.
        try:
            dia_semana = int(db.get_setting("backup_completo_dia", "6"))
        except ValueError:
            dia_semana = 6
        ja_tem_semana = any(
            datetime.fromtimestamp(p.stat().st_mtime).date() >= hoje - timedelta(days=6)
            for p in pasta.glob("backup_completo_*.zip")
        )
        if hoje.weekday() == dia_semana and not ja_tem_semana:
            completo = pasta / f"backup_completo_{hoje.isoformat()}.zip"
            try:
                full_backup(completo, com_arquivos=True)
                db.log(None, "SISTEMA", "AUTO_BACKUP_COMPLETO", "BACKUP", None,
                       {"path": str(completo), "bytes": completo.stat().st_size,
                        "cifrado": BKP.e_cifrado(completo)}, agente="backup automático", a_mando_de=IDR.PELO_RESPONSAVEL)
            except Exception as exc:
                db.log(None, "SISTEMA", "AUTO_BACKUP_FAILURE", "BACKUP", None,
                       {"error": str(exc), "tipo": "completo"}, agente="backup automático", a_mando_de=IDR.PELO_RESPONSAVEL)

        def expurgar(padrao: str, manter: int):
            achados = sorted(pasta.glob(padrao), key=lambda p: p.stat().st_mtime, reverse=True)
            for velho in achados[max(1, manter):]:
                velho.unlink(missing_ok=True)

        try:
            expurgar("backup_banco_*.zip", max(3, int(db.get_setting("backup_retention", "30"))))
            expurgar("backup_completo_*.zip",
                     max(2, int(db.get_setting("backup_completo_retencao", "8"))))
            # Formato antigo: um unico arquivo com tudo. Some por retencao.
            expurgar("backup_automatico_*.zip", 2)
        except Exception:
            pass

    def papel_de_quem_esta_logado():
        """O papel do usuario da sessao, ou None. So LE.

        **`current_user()` devolve a linha do banco, e ela nao tem `.get`** — o
        primeiro conserto escreveu `(current_user() or {}).get("role")` e
        estourou em toda tela. Row indexa por nome e levanta `IndexError` na
        coluna que falta; por isso o acesso e por `keys()`.
        """
        u = current_user()
        if not u:
            return None
        return u["role"] if "role" in u.keys() else None

    def funcao_de_quem_esta_logado():
        """A função CADASTRADA do usuário da sessão, ou None. Só LÊ.

        Não é `usuario_funcao()`, que cai no padrão da serventia quando falta
        cadastro: aqui a falta tem de continuar falta (21/10/2026 — a guarda
        do Protesto fecha pela função «Auxiliar», e o padrão inventaria uma).
        """
        u = current_user()
        if not u:
            return None
        return u["funcao"] if "funcao" in u.keys() else None

    @app.before_request
    def before_request():
        if request.endpoint == "static":
            return
        # O CORPO DO POST SEM LOGIN TEM TETO, E ELE VALE ANTES DE LER (LS02
        # M5; LX12, 19/10/2026). O token de formulário, logo abaixo, lê
        # `request.form` — e com isso qualquer máquina da rede fazia o servidor
        # ler e gravar em temporário até 200 MB (o `MAX_CONTENT_LENGTH` de
        # quem está logado e sobe anexo) antes da primeira recusa. Login e
        # setup cabem em poucos KB. Pelo `Content-Length`, recusa sem ler; sem
        # ele (corpo em pedaços), o mesmo teto vale na leitura. A ponte do CCN
        # fica de fora: só atende a própria máquina e traz o lote inteiro.
        if (request.method == "POST" and not session.get("user_id")
                and request.endpoint != "ccn_ponte_resultado"):
            teto = TETOS.valor("corpo_anonimo_bytes")
            if (request.content_length or 0) > teto:
                abort(413)
            request.max_content_length = teto
        automatic_backup_once()
        # A LEITURA DIARIA DO CNIB, na mesma porta do backup automatico — e
        # pela mesma razao: e aqui que se sabe que a casa abriu hoje. Ela e
        # buscada em `app.extensions` porque nasce la embaixo, quando
        # `cnib_web` registra as rotas; e a chamada e protegida porque **tela
        # nao cai por causa de rotina de fundo**.
        rotina_cnib = app.extensions.get("cnib_uma_vez_por_dia")
        if rotina_cnib:
            try:
                rotina_cnib()
            except Exception:
                pass
        if not db.has_users() and request.endpoint not in {"setup", "static", "health"}:
            return redirect(url_for("setup"))
        if session.get("user_id"):
            # A SESSÃO DE QUEM FOI DESATIVADO (ou apagado) ACABA AQUI — e não
            # rota a rota: `login_required` só olha o cookie. Ver `current_user`.
            if current_user() is None:
                session.clear()
                flash("Sessão encerrada: este usuário foi desativado.", "warning")
                return redirect(url_for("login"))
            # A SENHA MUDOU DEPOIS DO LOGIN (M3) — ou a sessão é de antes do
            # carimbo existir: as duas acabam aqui, e quem é o dono entra de novo.
            carimbo = session.get("cred")
            if not carimbo or not secrets.compare_digest(
                    str(carimbo), carimbo_da_senha(session["user_id"])):
                session.clear()
                flash("Sessão encerrada: a senha desta conta foi trocada. "
                      "Entre de novo.", "warning")
                return redirect(url_for("login"))
            now = datetime.now()
            # O PRAZO ABSOLUTO (B7): conta do login, e não do último clique.
            try:
                inicio = datetime.fromisoformat(session.get("inicio") or "")
            except ValueError:
                inicio = None
            horas = prazo_absoluto_horas()
            if inicio is None or now - inicio > timedelta(hours=horas):
                session.clear()
                flash(f"Sessão encerrada: passou do prazo de {horas} horas "
                      f"desde a entrada. Entre de novo.", "warning")
                return redirect(url_for("login"))
            timeout = max(10, parse_int(db.get_setting("session_timeout_minutes", "60")) or 60)
            last = session.get("last_activity")
            if last:
                try:
                    elapsed = now - datetime.fromisoformat(last)
                    if elapsed.total_seconds() > timeout * 60:
                        session.clear()
                        flash("Sessão encerrada por inatividade.", "warning")
                        return redirect(url_for("login"))
                except Exception:
                    pass
            session["last_activity"] = now.isoformat(timespec="seconds")
            # O ROBÔ NÃO ENTRA NO QUE É DE GENTE (revisão de segurança de
            # 22/10/2026, A6). Até aqui a única guarda do robô era a do selo
            # automático; com a credencial dele — que mora num script — se
            # abria usuários, atualizações, backup e caixa. A lista das rotas
            # vedadas mora em `selo_robo.ROTAS_VEDADAS_AO_ROBO`, ao lado da
            # regra que já dizia que robô não sela.
            #
            # E DESDE 26/10/2026 A RÉGUA É FECHADA (revisão de segurança dos
            # PRs abertos, achado transversal 1): a lista de vedadas não pegava
            # rota nova, e cinco PRs traziam rotas que o robô alcançaria sem
            # ninguém ter decidido. Agora o robô só entra no que está em
            # `rotas_do_robo.ROTAS_PERMITIDAS_AO_ROBO`; o resto é 403. As
            # vedadas continuam por cima — vedada vence permitida.
            import selo_robo as SR
            _quem = current_user()
            if _quem is not None and SR.usuario_e_robo(_quem) and \
                    not SR.rota_permitida_ao_robo(request.endpoint):
                abort(403)
        # Isentas do token de formulário: quem as chama não tem a sessão, e
        # cada uma se autentica por conta própria — o webhook pela assinatura
        # da Meta; a ponte do CCN (13/10/2026) pelo código do lote, e só
        # atende a própria máquina (`ccn_web._so_desta_maquina`).
        if request.method == "POST" and request.endpoint not in ("whatsapp_webhook",
                                                                 "ccn_ponte_resultado"):
            expected = session.get("csrf_token")
            received = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not expected or not received or not secrets.compare_digest(str(expected), str(received)):
                abort(400, "Token CSRF inválido.")
        # MODULO DESLIGADO NAO ABRE, E A GUARDA E AQUI — nao no menu.
        #
        # Tirar o link e deixar a rota de pe esconde a porta sem tranca-la:
        # quem tiver o endereco nos favoritos entra e lavra. A regra de «de
        # que modulo e esta tela» e a de `modulos.py`, a MESMA do menu — ha
        # teste que roda as duas contra todas as rotas.
        qual = MOD.modulo_da_tela(request.endpoint)
        quem = papel_de_quem_esta_logado()
        funcao = funcao_de_quem_esta_logado()
        if not MODLIG.pode_entrar(db.get_setting, qual, quem, funcao):
            flash(MODLIG.motivo(qual, MODLIG.alcance(db.get_setting, qual),
                                quem, funcao),
                  "warning")
            return redirect(url_for("dashboard"))
        manutencao_do_dia()

    @app.after_request
    def cabecalhos_de_seguranca(resposta):
        """Os cabeçalhos que o navegador obedece (B1 do LS01, lote LX11).

        SAMEORIGIN deixa as prévias em `<iframe>` da própria casa e barra a
        página de fora que põe o sistema num quadro invisível para o clique
        cair no botão errado. `nosniff` não deixa o navegador «adivinhar» que
        um anexo é HTML. O Referer não leva o endereço da tela (com id de ato)
        para site de fora. A CSP vai só como RELATÓRIO: as telas têm script e
        estilo na própria página, e uma CSP que bloqueia quebraria o balcão —
        o relatório mostra no console o que teria sido barrado.
        `setdefault`: a rota que já escolheu o seu cabeçalho fica com ele.
        """
        h = resposta.headers
        h.setdefault("X-Frame-Options", "SAMEORIGIN")
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "same-origin")
        h.setdefault("Content-Security-Policy-Report-Only",
                     "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                     "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                     "object-src 'none'; base-uri 'self'; form-action 'self'; "
                     "frame-ancestors 'self'")
        # TODA EXPORTAÇÃO FICA NA AUDITORIA (revisão de segurança de
        # 22/10/2026, M9): CSV, planilha e ZIP saem da casa, e até aqui só
        # algumas rotas anotavam quem os pediu. Num lugar só, para a rota
        # nova já nascer anotada. O papel de quem exporta não muda aqui.
        import re as _re
        _disp = str(h.get("Content-Disposition") or "")
        if ("attachment" in _disp.lower() and session.get("user_id")
                and _re.search(r"\.(csv|xlsx|zip)\b", _disp, _re.I)):
            try:
                audit("EXPORTACAO", "ARQUIVO", None, {
                    "rota": request.endpoint, "arquivo": _disp[:200],
                    "status": resposta.status_code})
            except Exception:                              # noqa: BLE001
                pass
        return resposta

    def manutencao_do_dia():
        """As duas rotinas diarias, uma vez por dia, SEM PERDER DIA.

        O QUE ISTO CORRIGE
            `ensure_recurring_tasks` e `ensure_overdue_escalations` rodavam em
            TODA requisicao, inclusive nos GET. As duas abrem
            `db.transaction()`, que e `BEGIN IMMEDIATE`: tomavam o lock de
            ESCRITA do banco inteiro para abrir qualquer tela.

            Medido: com outro balcao dentro de uma transacao de escrita, onze
            telas de leitura devolviam HTTP 500 depois de dez segundos cada.
            Depois desta mudanca, 200 em centesimos de segundo.

        POR QUE O `while`, E POR QUE ELE NAO E DETALHE
            `ensure_recurring_tasks` avanca UM vencimento por chamada. A
            primeira versao disto rodava uma vez por dia e pronto — e com isso
            uma obrigacao DIARIA nunca recuperava dia perdido: todo fim de
            semana atrasava dois dias, para sempre. Em oito semanas de uso a
            deriva medida foi de quinze dias.

            Entao roda ate nao criar mais nada. Ai sim uma passagem por dia
            equivale a mil: o que muda e o numero de vezes, nao o resultado.
            O teto de 400 voltas e trava de laco, nao regra de negocio — mais
            de um ano de atraso e problema de outra natureza.

        POR QUE A RESERVA E ATOMICA
            A marca em `settings` sozinha e ler-e-depois-escrever: dois
            balcoes abrindo o sistema na mesma manha passavam os dois pela
            verificacao e rodavam as duas rotinas em paralelo, criando tarefa
            futura em duplicidade. O `UPDATE ... WHERE value <> valor` decide no
            banco, dentro de uma transacao: quem alterar a linha ganhou o dia.

        POR QUE A FALHA FICA REGISTRADA
            Antes, falhar era HTTP 500 e o cartorio descobria na hora. Uma
            manutencao que so escreve no log do servidor falha em silencio para
            sempre. Agora o erro e a data ficam em `settings`, onde a tela de
            integridade e o diagnostico podem perguntar.
        """
        if not session.get("user_id"):
            return
        hoje = date.today().isoformat()
        if app.extensions.get("manutencao_em") == hoje:
            return
        anterior = ""
        try:
            with db.transaction() as con:
                bd = banco(con)
                bd.escrever(
                    "INSERT INTO settings(key, value) VALUES(%s, '') "
                    "ON CONFLICT DO NOTHING",
                    ("manutencao_diaria_em",))
                linha = bd.um(
                    "SELECT value FROM settings WHERE key=%s",
                    ("manutencao_diaria_em",))
                anterior = (linha["value"] if linha else "") or ""
                ganhou = len(bd.escrever(
                    "UPDATE settings SET value=%s WHERE key=%s AND value<>%s "
                    "RETURNING key",
                    (hoje, "manutencao_diaria_em", hoje)))
            app.extensions["manutencao_em"] = hoje
            if not ganhou:
                return

            criadas = 0
            for _ in range(400):
                novas = db.ensure_recurring_tasks()
                criadas += novas
                if not novas:
                    break
            db.ensure_overdue_escalations()
            # A VOLTA DAS SUSPENSÕES POR PRAZO (relato #132): a cobrança já
            # volta na leitura; aqui fica o rastro e se limpam as colunas.
            db.encerrar_suspensoes_vencidas()
            if criadas:
                app.logger.info("manutenção diária: %s tarefa(s) recorrente(s)",
                                criadas)
            db.set_settings({"manutencao_diaria_erro": ""})
        except Exception as erro:                                  # noqa: BLE001
            # Manutencao nao derruba tela. A requisicao segue; a proxima tenta
            # de novo, porque a marca do dia sai junto com o rollback quando a
            # falha e na propria transacao da reserva.
            # DEVOLVE O DIA. A reserva ja comitou quando a falha aconteceu
            # nas rotinas; deixa-la de pe perderia o dia inteiro em silencio, e
            # e exatamente o dia em que alguma coisa esta errada.
            app.extensions.pop("manutencao_em", None)
            try:
                db.set_settings({"manutencao_diaria_em": anterior})
            except Exception:                                      # noqa: BLE001
                pass
            recado = f"{date.today().isoformat()} {type(erro).__name__}: {erro}"
            app.logger.warning("manutenção diária adiada: %s", recado)
            try:
                db.set_settings({"manutencao_diaria_erro": recado})
            except Exception:                                      # noqa: BLE001
                pass

    @app.context_processor
    def inject_globals():
        s = settings_dict()
        alert_days = parse_int(s.get("alert_days", "5")) or 5
        global_stats = db.dashboard_stats(alert_days) if session.get("user_id") else {}
        atrib = request.args.get("atribuicao", "")
        ctx_modulo = MOD.contexto(request.endpoint, atrib)
        return {
            # O que o balcao NAO ve. O menu pergunta a mesma funcao que a
            # guarda do `before_request` usa — uma regra so.
            # O que o menu NAO oferece a ESTE operador — depende de quem
            # esta olhando desde que o interruptor virou alcance.
            "MODULOS_ESCONDIDOS": MODLIG.escondidos(
                db.get_setting, papel_de_quem_esta_logado(),
                funcao_de_quem_esta_logado()),
            "APP_NAME": APP_NAME,
            "VERSION": VERSION,
            "user": current_user(),
            "csrf_token": session.setdefault("csrf_token", new_csrf_token()),
            "unit_name": s.get("unit_name", "Serventia Extrajudicial"),
            # Identificacao completa da serventia, disponivel em qualquer tela
            # (serventia.py). O balcao confere o timbre antes de imprimir.
            "sv": dados_serventia(settings_dict),
            "fmt_date": fmt_date,
            "fmt_dt": fmt_dt,
            "global_stats": global_stats,
            "PRIORITIES": PRIORITIES,
            "TASK_STATUSES": TASK_STATUSES,
            # O HISTORICO DA TAREFA EM PORTUGUES — relato #59.
            #
            #   A linha do tempo mostrava a palavra crua do histórico —
            #   «ALTEROU_STATUS», «ALTEROU_EVIDENCE_REQUIRED»,
            #   «ESCALONAMENTO_AUTOMATICO» — para quem trabalha no balcão:
            #   medido em 17/09/2026, as **7** palavras de ação gravadas na
            #   produção apareciam assim. Vai no contexto GLOBAL como o
            #   `fmt_dt`: o dossiê da tarefa também desenha a linha do tempo, e
            #   ligada tela a tela a segunda nasceria em jargão.
            "rotulo_da_acao": TP.rotulo_da_acao,
            # O SELO DA SUSPENSÃO (relato #132) — global pelo mesmo motivo: a
            # lista de tarefas, a de processos, o expediente e a ficha o
            # desenham, e ligado tela a tela a próxima nasceria sem ele.
            "suspensao_de": TS.situacao,
        "TIPOS_ANDAMENTO": TP.TIPOS_ANDAMENTO,
        "rotulo_do_tipo_andamento": TP.rotulo_do_tipo_andamento,
            "EXPEDIENT_STAGES": EXPEDIENT_STAGES,
            # A COR DO MODULO EM QUE A TELA ESTA — relato #32 do oficial.
            #
            #   Vai no contexto GLOBAL, e nao tela a tela: ligada uma a uma, a
            #   primeira que alguem criasse amanha nasceria sem cor, e **sem
            #   aviso de que nasceu** — foi o que aconteceu com a janela da
            #   ajuda antes de ela ir para o `base.html`.
            #
            #   `folha_de_estilo` traz as cores de TODOS os modulos, e nao so
            #   a do atual: o menu pinta a marca de cada grupo, e ele mostra os
            #   oito ao mesmo tempo.
            **ctx_modulo,
            "cores_dos_modulos": MOD.folha_de_estilo(),
            "MODULOS": MOD.MODULOS,
            # A DERIVACAO DA SECAO vai como FUNCAO, e nao como lista pronta: as
            # secoes estao escritas uma a uma no menu, e uma lista exigiria que
            # alguem renumerasse tudo ao inserir uma no meio.
            "cor_da_secao": MOD.cor_da_secao,
            "titulo_aba": TITULOABA.sugerir(
                request.endpoint,
                atribuicao=atrib,
                modulo_nome=ctx_modulo.get("modulo_nome", ""),
            ),
        }

    @app.template_filter("forte")
    def _forte(texto):
        """`**assim**` vira negrito de verdade na tela, e não asteriscos.

        POR QUE ESTE FILTRO EXISTE. Os módulos de norma — `rr_tjma`, `rt_tjma`,
        `us_tjma`, `rc_funai` — guardam a regra com a parte que decide marcada
        em `**`, porque quem lê o CÓDIGO precisa ver o que pesa. Essas mesmas
        constantes vão para a TELA, e ali os asteriscos apareciam no meio da
        frase: «o livro **corrente em uso na serventia**».

        As duas saídas ruins eram tirar a marcação (e perder o destaque para
        quem lê o código) ou reescrever a frase duas vezes (e as duas divergem no
        primeiro conserto — a lição da `normalizar_nome`). Este filtro é a
        terceira: uma fonte só, e o destaque chega aos dois lados.

        **ESCAPA ANTES DE MARCAR.** O texto vem de constante do projeto, e não do
        balcão — mas um filtro que devolve HTML sem escapar é a porta que alguém
        usa amanhã com texto de fora.
        """
        import re
        from markupsafe import Markup, escape
        pedaco = str(texto or "")
        return Markup(re.sub(r"\*\*(.+?)\*\*", r"<strong>\g<1></strong>",
                             str(escape(pedaco))))

    @app.template_filter("sem_script")
    def _sem_script(conteudo):
        """O teor escrito no balcão, na tela — no lugar do `|safe` (LS02).

        O `|safe` dizia «isto é da casa», e o teor é de quem o digitou:
        script gravado no teor rodava na sessão do oficial. Pelo decorador, e
        não por `add_template_filter`, porque é dele que
        `tools/conferir_antes_de_atualizar.py` tira os filtros que existem.
        """
        return HSS.sem_script(conteudo)

    @app.template_filter("so_http")
    def _so_http(valor):
        """O link que veio de central, só se for `http(s):` (LX12, M9 do LS02).

        Vazio = não vira link: `javascript:` vindo da central rodaria no
        clique. Pelo decorador, pela mesma razão do `sem_script`.
        """
        return HSS.endereco_da_web(valor)

    @app.template_filter("centavos_reais")
    def _centavos_reais(valor):
        """Centavos inteiros -> '1.234,56'. O caixa conta em centavos; a tela mostra em reais."""
        from caixa_schema import reais
        try:
            return reais(int(valor))
        except (TypeError, ValueError):
            return valor

    @app.template_filter("fromjson")
    def fromjson(value):
        try:
            return json.loads(value) if value else []
        except (TypeError, ValueError):
            return [value] if value else []

    @app.template_filter("filesize")
    def filesize(value):
        n = int(value or 0)
        for unit in ["B", "KB", "MB", "GB"]:
            if n < 1024 or unit == "GB":
                return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
            n /= 1024
        return str(value)

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        if db.has_users():
            return redirect(url_for("login"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            full_name = request.form.get("full_name", "").strip()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm", "")
            if not username or not full_name:
                flash("Informe nome e usuário.", "danger")
            elif password != confirm:
                flash("As senhas não conferem.", "danger")
            else:
                ok, msg = db.validate_password(password)
                if not ok:
                    flash(msg, "danger")
                else:
                    uid = db.create_user(username, full_name, password, "ADMIN")
                    inspection_id = db.seed_inspection()
                    db.log(uid, username, "INITIAL_SETUP", "SYSTEM", None, {"inspection_id": inspection_id})
                    if inspection_id:
                        flash("Administrador criado. O plano de ação da inspeção foi importado; defina a data-base dos prazos na aba Inspeção.", "success")
                    else:
                        flash("Administrador criado.", "success")
                    return redirect(url_for("login"))
        return render_template("setup.html")

    def abrir_sessao(row, detalhes=None):
        """A sessão de quem provou quem é — pela senha, ou pela senha e o código.

        Uma só para os dois caminhos (LG02): o segundo passo da verificação em
        duas etapas termina aqui também, e uma cópia dela em `dois_fatores_web`
        divergiria no primeiro conserto da sessão.
        """
        session.clear()
        session["csrf_token"] = new_csrf_token()
        session["user_id"] = int(row["id"])
        agora_iso = datetime.now().isoformat(timespec="seconds")
        session["last_activity"] = agora_iso
        session["inicio"] = agora_iso
        session["cred"] = carimbo_da_senha(row["id"])
        db.log(int(row["id"]), row["username"], "LOGIN_SUCCESS", "SESSION", None, detalhes, request.remote_addr)

    app.extensions["abrir_sessao"] = abrir_sessao

    def cadastro_pelo_login(username: str):
        """O usuário com este login, ativo ou não — ou None. Só LÊ.

        É só para o rastro e a espera do login: a senha quem confere é o
        `db.authenticate`, com a régua dele.
        """
        if not username:
            return None
        with db.connect() as con:
            return banco(con).um(
                "SELECT id, username FROM users WHERE username = %s "
                "COLLATE public.cg_nocase ORDER BY id LIMIT 1", (username,))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            ip = request.remote_addr
            alvo = cadastro_pelo_login(username)
            # O RASTRO SÓ GUARDA O USUÁRIO QUE EXISTE (B5): quem digita a senha
            # no campo do usuário não a deixa escrita na auditoria.
            rastro = alvo["username"] if alvo else LESP.INEXISTENTE
            chave = LESP.chave(secret_key, username)
            uid_alvo = int(alvo["id"]) if alvo else None
            # Da leitura da espera até o erro gravado, uma tentativa por vez
            # para este usuário nesta máquina (`LESP.na_vez`).
            with db.connect() as con, LESP.na_vez(con, chave, ip):
                fim = LESP.espera(con, chave, ip, uid_alvo)
                if fim:
                    # Em espera, a senha nem é conferida — e a tentativa não conta.
                    db.log(None, rastro, LESP.EM_ESPERA, "SESSION", None,
                           LESP.detalhes(chave, ate=fim.isoformat()), ip,
                           agente=IDR.AGENTE_SERVIDOR)   # evento: ninguém mandou
                    row = None
                else:
                    # `authenticate` gasta o mesmo PBKDF2 para o usuário que
                    # não existe (B4): o tempo não diz quem é cadastrado.
                    row = db.authenticate(username, request.form.get("password", ""))
                    if not row:
                        # O `db.log` desiste em 800 ms se a trava única do banco
                        # não vier, e aí este erro não entra na contagem: sob
                        # carga a espera fica mais branda, nunca mais dura.
                        db.log(None, rastro, LESP.FALHA, "SESSION", None,
                               LESP.detalhes(chave), ip,
                               agente=IDR.AGENTE_SERVIDOR)   # evento: ninguém mandou
                        depois = LESP.espera(con, chave, ip, uid_alvo)
            if fim:
                flash(LESP.recado(fim), "danger")
                return render_template("login.html"), 429
            if not row:
                if depois:
                    flash("Usuário ou senha inválidos. " + LESP.recado(depois), "danger")
                else:
                    flash("Usuário ou senha inválidos.", "danger")
            else:
                # Só caminho DESTE sistema (M1): `next=//fora.exemplo` levava
                # quem acabou de entrar para uma página que imita esta.
                destino = SEGWEB.destino_interno(request.args.get("next"), "")
                # A SENHA SÓ NÃO BASTA para quem ativou a verificação em duas
                # etapas, ou cujo papel o Gestor a exigiu (LG02): aí a entrada
                # vira meia-sessão e segue para o código. Sem nenhum dos dois,
                # o desvio devolve None e a entrada é a de sempre.
                desvio = app.extensions["dois_fatores_depois_da_senha"](
                    row, destino)
                if desvio is not None:
                    return desvio
                abrir_sessao(row)
                return redirect(destino or url_for("dashboard"))
        return render_template("login.html")

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        audit("LOGOUT", "SESSION")
        session.clear()
        return redirect(url_for("login"))

    @app.route("/conta/senha", methods=["GET", "POST"])
    @login_required
    def minha_senha():
        """«Trocar minha senha» — a senha atual, a nova e a confirmação (M4).

        Aberta a todo papel, AUDITOR incluído: é a conta da própria pessoa.
        A senha atual errada conta na MESMA espera do login (A4) — senão a
        sessão esquecida aberta no balcão viraria o lugar de adivinhar a
        senha sem freio. A força é a régua de sempre, `db.validate_password`.
        """
        if request.method == "POST":
            eu = current_user()
            atual = request.form.get("senha_atual", "")
            nova = request.form.get("nova_senha", "")
            ip = request.remote_addr
            chave = LESP.chave(secret_key, eu["username"])
            # A mesma vez do login: a senha atual errada é uma tentativa.
            with db.connect() as con, LESP.na_vez(con, chave, ip):
                fim = LESP.espera(con, chave, ip, int(eu["id"]))
                confere = not fim and db.authenticate(eu["username"], atual)
                if not fim and not confere:
                    db.log(int(eu["id"]), eu["username"], LESP.FALHA, "SESSION", None,
                           LESP.detalhes(chave, tela="minha_senha"), ip)
            if fim:
                flash(LESP.recado(fim), "danger")
            elif not confere:
                flash("A senha atual não confere.", "danger")
            elif nova != request.form.get("confirmacao", ""):
                flash("A nova senha e a repetição não conferem.", "danger")
            elif nova == atual:
                flash("A nova senha é igual à atual.", "danger")
            else:
                ok, msg = db.validate_password(nova)
                if not ok:
                    flash(msg, "danger")
                else:
                    db.reset_password(int(eu["id"]), nova)
                    # Esta sessão segue; as outras, com o carimbo velho, caem.
                    session["cred"] = carimbo_da_senha(eu["id"])
                    audit("PASSWORD_CHANGED", "USER", int(eu["id"]))
                    flash("Senha trocada. As outras sessões abertas com a senha "
                          "antiga foram encerradas.", "success")
                    return redirect(url_for("dashboard"))
            return redirect(url_for("minha_senha"))
        return render_template("conta_senha.html")

    @app.route("/")
    @login_required
    def dashboard():
        alert_days = parse_int(db.get_setting("alert_days", "5")) or 5
        stats = db.dashboard_stats(alert_days)
        # O PAINEL É COBRANÇA: a suspensa sai desta lista (relato #132) e
        # aparece contada à parte, no cartão «Suspensos».
        tasks = db.list_tasks("ABERTAS", limit=20, filtros={"suspensas": "OCULTAR"})
        inspections = db.list_inspections()
        # OS ATOS EM ANDAMENTO — relato #29 do oficial: «o painel deve focar
        # nos atos em andamento e tarefas pendentes, tudo em ordem de
        # relevância».
        #
        #   **A metade que faltava era «atos».** Tarefa e expediente são
        #   administrativos, e eram tudo o que o painel mostrava; a escritura em
        #   lavratura, a prenotação sem ato, o usucapião e a habilitação não
        #   apareciam em lugar nenhum da primeira tela. `inacabados` já os media
        #   — só que numa tela que se abre de propósito, e o painel é a que se
        #   abre sozinha.
        #
        #   **NÃO É UMA CÓPIA**: mede na hora, das nove tabelas onde os atos já
        #   moram, e ato concluído sai sozinho. Medido: 12 ms na produção.
        hoje = date.today().isoformat()
        andamento, andamento_erro = [], ""
        try:
            import inacabados as INAC
            with db.connect() as con:
                andamento = [x for x in INAC.resumo(con, hoje=hoje)
                             if x["quantos"] or x["erro"]]
            # A ORDEM DE RELEVÂNCIA É A DO APERTO: o que está parado há mais
            # tempo que o próprio prazo vem primeiro, e depois o que é maior.
            andamento.sort(key=lambda x: (-x["parados"], -x["quantos"]))
        except Exception as erro:                       # noqa: BLE001
            # **ZERO MEDIDO E ZERO POR ENGANO SÃO COISAS DIFERENTES.** Um
            # `except` que devolvesse lista vazia faria a primeira tela da casa
            # dizer «nada em andamento» no dia em que a medição quebrou.
            andamento_erro = f"não deu para medir: {erro}"
        # 13/10/2026: o bloco de expedientes saiu do painel (ordem do oficial —
        # «substituído por processos»), e com ele as duas leituras que só o
        # alimentavam. A entrada que espera decisão aparece em Processos.
        return render_template("dashboard.html", stats=stats, tasks=tasks, inspections=inspections, today=hoje, alert_days=alert_days, andamento=andamento, andamento_erro=andamento_erro)

    @app.route("/expedientes", methods=["GET", "POST"])
    @login_required
    @roles_required(*PRATICA, metodos=("POST",))
    def expedientes():
        s = settings_dict()
        categories = json_list(s.get("categories", "[]"), ["Outros"])
        sources = json_list(s.get("sources", "[]"), ["Outro"])
        sectors = json_list(s.get("sectors", "[]"), [])
        users = db.list_users(active_only=True)
        if request.method == "POST":
            deadline_start = parse_date(request.form.get("deadline_start"))
            deadline_days = parse_int(request.form.get("deadline_days"))
            due = calc_deadline(deadline_start, deadline_days)
            assigned = parse_int(request.form.get("assigned_user_id"))
            backup = parse_int(request.form.get("backup_user_id"))
            if db.get_setting("require_backup_assignee", "1") == "1" and assigned and not backup:
                flash("Defina também um responsável substituto para expedientes com responsável principal.", "danger")
            else:
                user = current_user()
                data = {
                    "source": request.form.get("source"), "external_reference": request.form.get("external_reference"),
                    "sender": request.form.get("sender"), "subject": request.form.get("subject"), "category": request.form.get("category"),
                    "sector": request.form.get("sector"), "received_at": parse_date(request.form.get("received_at")) or date.today().isoformat(),
                    "deadline_start": deadline_start, "deadline_days": deadline_days, "deadline_date": due,
                    "priority": request.form.get("priority"), "assigned_user_id": assigned, "backup_user_id": backup,
                    "notes": request.form.get("notes"),
                }
                exp_id = db.create_expediente(data, int(user["id"]))
                exp = db.get_expediente(exp_id)
                target = archive_root() / "Expedientes" / safe_component(data["category"] or "Outros") / safe_component(exp["internal_protocol"])
                for fs in request.files.getlist("files"):
                    if fs and fs.filename:
                        info = save_upload(fs, target)
                        db.add_attachment("EXPEDIENTE", exp_id, info, int(user["id"]), "Documento recebido")
                if deadline_days is not None or (data["category"] or "").lower() == "para cumprimento":
                    task_id = db.create_task({
                        "source_type": "EXPEDIENTE", "source_ref": exp["internal_protocol"], "title": data["subject"],
                        "description": f"Cumprir expediente {exp['internal_protocol']} recebido via {data['source']}.", "sector": data["sector"],
                        "system_name": data["source"], "priority": data["priority"], "start_date": deadline_start, "due_days": deadline_days,
                        "due_date": due, "assigned_user_id": assigned, "backup_user_id": backup, "linked_expediente_id": exp_id,
                    }, int(user["id"]))
                    audit("EXPEDIENTE_TASK_CREATED", "TASK", task_id, {"expediente_id": exp_id})
                audit("EXPEDIENTE_CREATED", "EXPEDIENTE", exp_id, data)
                flash(f"Expediente {exp['internal_protocol']} cadastrado.", "success")
                # VEIO DA TELA DE PROCESSOS (12/10/2026): volta para lá — para o
                # processo, se ele já nasceu; senão, para a decisão «abrir
                # processo» ou «só ciência», no alto da lista.
                if request.form.get("voltar") == "processos":
                    with db.connect() as _c:
                        criado = banco(_c).um(
                            "SELECT id FROM tasks WHERE linked_expediente_id=%s "
                            "ORDER BY id DESC LIMIT 1", (exp_id,))
                    return redirect(url_for("task_detail", task_id=criado["id"]) if criado
                                    else url_for("processos_lista"))
                return redirect(url_for("expediente_detail", expediente_id=exp_id))
        busca = (request.args.get("q") or "").strip()
        rows = db.list_expedientes(busca=busca or None)
        return render_template(
            "expedientes.html",
            rows=rows,
            categories=categories,
            sources=sources,
            sectors=sectors,
            users=users,
            today=date.today().isoformat(),
            busca=busca,
        )

    @app.route("/expedientes/<int:expediente_id>")
    @login_required
    def expediente_detail(expediente_id):
        row = db.get_expediente(expediente_id)
        if not row: abort(404)
        attachments = db.get_attachments("EXPEDIENTE", expediente_id)
        linked_tasks = [t for t in db.list_tasks(limit=1000) if t["linked_expediente_id"] == expediente_id]
        # O QUE FALTA PARA ENCERRAR — e é aviso, não trava: quem decide fechar
        # com tarefa aberta é o oficial.
        # `db.connect()` já devolve a conexão pronta — repetir
        # a linha aqui era supor que ela vem crua, e `app.py` nem importa
        # `sqlite3`. O teste de tela pegou.
        with db.connect() as _c:
            estado = EXPT.o_que_falta_para_encerrar(_c, expediente_id)
        return render_template("expediente_detail.html", row=row,
                               attachments=attachments, linked_tasks=linked_tasks,
                               estado=estado, COMO_ENCERRAR=EXPT.COMO_ENCERRAR)

    @app.route("/expedientes/prontos-para-encerrar")
    @login_required
    def expedientes_prontos():
        """Os expedientes abertos cujas tarefas já estão todas concluídas.

        É a lista do trabalho que acabou e ninguém fechou — o expediente 6
        desta casa está nela desde que a tarefa dele foi concluída. Sem ela,
        só apareceria a quem abrisse aquele expediente por acaso.
        """
        with db.connect() as con:
            prontos = EXPT.expedientes_com_tudo_concluido(con)
        return render_template("expedientes_prontos.html", prontos=prontos)

    @app.route("/expedientes/<int:expediente_id>/stage", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def expediente_stage(expediente_id):
        stage = request.form.get("stage", "")
        if stage not in EXPEDIENT_STAGES: abort(400)
        db.update_expediente_stage(expediente_id, stage, int(current_user()["id"]), request.form.get("response_reference"))
        audit("EXPEDIENTE_STAGE_CHANGED", "EXPEDIENTE", expediente_id, {"stage": stage})
        flash("Etapa atualizada.", "success")
        return redirect(url_for("expediente_detail", expediente_id=expediente_id))

    @app.route("/expedientes/<int:expediente_id>/evidence", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def expediente_evidence(expediente_id):
        exp = db.get_expediente(expediente_id)
        if not exp: abort(404)
        files = [f for f in request.files.getlist("file") if f and f.filename]
        if not files:
            flash("Selecione um arquivo.", "danger")
        else:
            target = archive_root() / "Expedientes" / safe_component(exp["category"]) / safe_component(exp["internal_protocol"])
            for fs in files:
                info = save_upload(fs, target)
                att = db.add_attachment("EXPEDIENTE", expediente_id, info, int(current_user()["id"]), request.form.get("description"))
                audit("ATTACHMENT_ADDED", "EXPEDIENTE", expediente_id, {"attachment_id": att, "sha256": info["sha256"]})
            if len(files) == 1:
                flash("Arquivo anexado.", "success")
            else:
                flash(f"{len(files)} arquivos anexados.", "success")
        return redirect(url_for("expediente_detail", expediente_id=expediente_id))

    @app.route("/tarefas", methods=["GET", "POST"])
    @login_required
    @roles_required(*PRATICA, metodos=("POST",))
    def tasks():
        s = settings_dict()
        sectors = json_list(s.get("sectors", "[]"), [])
        users = db.list_users(active_only=True)
        if request.method == "POST":
            start_date = parse_date(request.form.get("start_date"))
            due_days = parse_int(request.form.get("due_days"))
            due_date = parse_date(request.form.get("due_date")) or calc_deadline(start_date, due_days)
            assigned = parse_int(request.form.get("assigned_user_id"))
            backup = parse_int(request.form.get("backup_user_id"))
            if db.get_setting("require_backup_assignee", "1") == "1" and assigned and not backup:
                flash("Defina um responsável substituto.", "danger")
            elif not request.form.get("title", "").strip():
                flash("Informe o título da tarefa.", "danger")
            else:
                user = current_user()
                task_id = db.create_task({
                    "title": request.form.get("title"), "description": request.form.get("description"), "sector": request.form.get("sector"),
                    "system_name": request.form.get("system_name"), "priority": request.form.get("priority"), "start_date": start_date,
                    "due_days": due_days, "due_date": due_date, "assigned_user_id": assigned, "backup_user_id": backup,
                    "evidence_required": 1 if request.form.get("evidence_required") else 0, "legal_ref": request.form.get("legal_ref"),
                }, int(user["id"]))
                andamento0 = (request.form.get("andamento") or "").strip()
                if andamento0:
                    db.add_task_note(
                        task_id, int(user["id"]), andamento0,
                        tipo=request.form.get("tipo_andamento"),
                    )
                    audit("TASK_NOTE", "TASK", task_id, {"via": "cadastro"})
                audit("TASK_CREATED", "TASK", task_id)
                # O TIPO DO PROCESSO (12/10/2026): este é também o cadastro do
                # «Abrir processo interno» da tela de Processos — uma regra só de criar.
                especie = (request.form.get("especie") or "").strip()
                if especie:
                    import processo_especies as ESP
                    if especie in ESP.CATALOGO:
                        with db.transaction() as _c:
                            ESP.definir(_c, task_id, especie, agora=db.now(), por=int(user["id"]))
                flash("Tarefa criada.", "success")
                return redirect(url_for("task_detail", task_id=task_id))
        status = request.args.get("status", "ABERTAS")
        sector = request.args.get("sector") or None
        # AS VISTAS DO RELATO #59 — «o que esta comigo» e «o que passou por mim».
        # A lista precisa saber DE QUEM ela e, e a tela oferece as duas ao lado
        # das situacoes de sempre.
        usuario_id = int(current_user()["id"])
        with db.connect() as _c:
            contagem = TP.contagem_por_vista(_c, usuario_id, sector)
            # A PALAVRA FORA DO VOCABULARIO NAO SOME — ela sai das vistas de
            # proposito, e o numero dela aparece aqui. Sem isto, uma tarefa
            # como a #85 ficaria so em «Todas», que ninguem abre por acaso.
            fora_do_vocabulario = TP.tarefas_fora_do_vocabulario(_c, sector)
        # OS FILTROS E A ORDEM DE 13/10/2026 — os mesmos de Processos
        # (`tarefa_ordem`): responsável, substituto, prioridade, prazo, datas,
        # parado e ordenar por qualquer coluna.
        import tarefa_ordem as TO
        filtros = {k: (request.args.get(k) or "").strip() for k in TO.FILTROS}
        # A BUSCA POR TEXTO — relato #122 (07/10/2026): número, título,
        # descrição e responsável, convivendo com os filtros e a ordem.
        busca = (request.args.get("q") or "").strip()
        rows = db.list_tasks(status, sector, usuario_id=usuario_id,
                             filtros={k: v for k, v in filtros.items() if v}, busca=busca)
        ordem_pedida = TO.APELIDOS.get(filtros["ordem"].upper(), filtros["ordem"].upper())
        return render_template("tasks.html", rows=rows, sectors=sectors, users=users,
                               status_filter=status, sector_filter=sector or "",
                               filtros=filtros, ORDENS=TO.ordens_da_tela(tem_tipo=False),
                               busca=busca, SUSPENSAS=TO.SUSPENSAS,
                               PRAZOS=TO.PRAZOS, PARADOS=TO.PARADOS,
                               SEM_RESPONSAVEL=TO.SEM_RESPONSAVEL,
                               ordem_atual=ordem_pedida if ordem_pedida in TO.ORDENS else "",
                               vistas=TP.VISTAS_ESPECIAIS, rotulo_da_vista=TP.ROTULO_DA_VISTA,
                               contagem=contagem,
                               fora_do_vocabulario=fora_do_vocabulario,
                               ajuda_da_vista=TP.AJUDA_DA_VISTA.get(status, ""))

    @app.route("/tarefas/<int:task_id>", methods=["GET", "POST"])
    @login_required
    @roles_required(*PRATICA, metodos=("POST",))
    def task_detail(task_id):
        row = db.get_task(task_id)
        if not row: abort(404)
        if request.method == "POST":
            action = request.form.get("action")
            if action == "update":
                start_date = parse_date(request.form.get("start_date"))
                due_days = parse_int(request.form.get("due_days"))
                due_date = parse_date(request.form.get("due_date")) or calc_deadline(start_date, due_days)
                fields = {
                    "title": request.form.get("title"), "description": request.form.get("description"), "sector": request.form.get("sector"),
                    "system_name": request.form.get("system_name"), "priority": request.form.get("priority"), "status": request.form.get("status"),
                    "start_date": start_date, "due_days": due_days, "due_date": due_date, "assigned_user_id": parse_int(request.form.get("assigned_user_id")),
                    "backup_user_id": parse_int(request.form.get("backup_user_id")),
                    "legal_ref": request.form.get("legal_ref"),
                }
                if fields["status"] == "CONCLUIDA" and row["evidence_required"] and not db.get_attachments("TASK", task_id):
                    flash("Esta tarefa exige ao menos uma evidência antes da conclusão.", "danger")
                else:
                    db.update_task(task_id, fields, int(current_user()["id"]))
                    audit("TASK_UPDATED", "TASK", task_id, fields)
                    flash("Tarefa atualizada.", "success")
                    return redirect(url_for("task_detail", task_id=task_id))
            elif action in ("suspender", "retomar"):
                # SUSPENDER A COBRANÇA — relato #132, 14/10/2026: «permitir
                # suspender a exigência da tarefa ou expediente por tempo, ou
                # condicionar ao retorno de algo». Quem pode é quem edita a
                # tarefa (esta rota inteira é `login_required`); a regra mora em
                # `tarefa_suspensao`, e o rastro na linha do tempo e na auditoria.
                uid = int(current_user()["id"])
                # O AUDITOR SÓ VÊ — decisão do oficial em 15/10/2026: suspender
                # e retomar mudam a cobrança da casa, e quem fiscaliza não a
                # move. A guarda é aqui, na ação, porque a ficha ele precisa ver.
                if current_user()["role"] == "AUDITOR":
                    flash("O perfil de auditor só consulta: suspender ou retomar a "
                          "cobrança é de quem trabalha a tarefa.", "danger")
                    return redirect(url_for("task_detail", task_id=task_id))
                try:
                    with db.transaction() as con:
                        if action == "suspender":
                            feito = TS.suspender(
                                con, task_id, modo=request.form.get("modo", ""),
                                motivo=request.form.get("motivo", ""),
                                ate=request.form.get("ate") or None,
                                condicao=request.form.get("condicao") or None,
                                usuario_id=uid, agora=db.now())
                        else:
                            feito = TS.retomar(con, task_id, motivo=request.form.get("motivo", ""),
                                               usuario_id=uid, agora=db.now())
                except TS.SuspensaoError as erro:
                    flash(str(erro), "danger")
                else:
                    # `audit` abre transação própria: chame FORA do `with`.
                    audit("TASK_SUSPENSA" if action == "suspender" else "TASK_RETOMADA",
                          "TASK", task_id, feito)
                    if action == "suspender":
                        flash("Tarefa suspensa: ela sai da cobrança (painel, avisos, vencidas) "
                              + (f"até {feito['ate'][8:10]}/{feito['ate'][5:7]}/{feito['ate'][:4]}."
                                 if feito["ate"] else "até alguém marcar que a condição se cumpriu."),
                              "success")
                    elif feito.get("ja_tinha_voltado"):
                        flash("A suspensão já tinha terminado sozinha na data marcada; "
                              "o registro foi fechado.", "info")
                    else:
                        flash(f"Tarefa retomada depois de {feito['dias']} dia(s) suspensa — "
                              "o prazo voltou a correr.", "success")
                return redirect(url_for("task_detail", task_id=task_id))
            elif action == "evidencia":
                # EXIGIR OU NÃO A EVIDÊNCIA, COM UM CLIQUE — hotfix de 06/10/2026
                # («facilite a edicao para nao exigir mais evidencia quando
                # entender nao cabivel»). O motivo é opcional e vai à auditoria.
                exigir = 1 if request.form.get("exigir") == "1" else 0
                motivo = (request.form.get("motivo") or "").strip()
                db.update_task(task_id, {"evidence_required": exigir},
                               int(current_user()["id"]))
                audit("TASK_EVIDENCIA_ALTERADA", "TASK", task_id,
                      {"evidence_required": exigir, "motivo": motivo})
                flash("A tarefa passou a exigir evidência para ser concluída."
                      if exigir else "A tarefa não exige mais evidência para ser "
                      "concluída.", "success")
                return redirect(url_for("task_detail", task_id=task_id))
            elif action in ("concluir", "reabrir"):
                # CONCLUIR TEM DE SER UM BOTAO, e nao uma opcao dentro do
                # formulario de edicao.
                #
                #   Relatado pelo oficial em 27/08/2026: «nao estou achando o
                #   botao de concluir uma tarefa ou dar baixa». Nao havia: era
                #   preciso achar o campo «Status» no meio de treze campos,
                #   trocar para CONCLUIDA e clicar em «Salvar alteracoes» —
                #   tres passos para a acao mais comum da tela.
                #
                #   A REGRA DA EVIDENCIA CONTINUA VALENDO. Ela existe porque
                #   tarefa que a inspecao cobra sem prova anexada e tarefa que
                #   nao se demonstra ter sido feita; o botao nao pode ser um
                #   caminho por fora dela.
                if action == "reabrir":
                    # A METADE DE VOLTA DO RELATO #59 — e ela não é o inverso de
                    # concluir: é um ATO com motivo escrito, que fica na linha do
                    # tempo.
                    #
                    #   Até 17/09/2026 a rota escrevia a palavra `PENDENTE`, que
                    #   não existe no vocabulário do sistema (`TASK_STATUSES`):
                    #   a tarefa saía do filtro «Abertas» e não voltava a nenhum,
                    #   com o carimbo de conclusão ainda dentro dela. Medido na
                    #   produção: **uma** linha assim — a tarefa **#85**, que é o
                    #   próprio relato #59 —, e medido no pacote **3.6.141**
                    #   (`app.py`, linha **922**) qual linha a escrevia:
                    #   `novo = "CONCLUIDA" if action == "concluir" else "PENDENTE"`,
                    #   com a notícia «Tarefa reaberta como pendente.».
                    #   `tarefa_processo.reabrir` devolve a palavra conhecida e
                    #   apaga o carimbo, porque carimbo que fica depois de a tarefa
                    #   voltar a andar mente sobre o dia em que o serviço terminou.
                    #   `tools/normalizar_situacao_das_tarefas.py` tira a #85 do
                    #   limbo — só mede por padrão, e recusa o que não conhece.
                    try:
                        with db.transaction() as con:
                            volta = TP.reabrir(con, task_id,
                                               request.form.get("motivo", ""),
                                               int(current_user()["id"]), db.now())
                    except TP.ProcessoError as erro:
                        flash(str(erro), "danger")
                    else:
                        # `audit` abre transação própria: chame FORA do `with`.
                        audit("TASK_REABERTA", "TASK", task_id,
                              {"de": row["status"],
                               "status": TP.STATUS_DE_REABERTURA,
                               "motivo": volta["motivo"],
                               "carimbo_apagado": volta["carimbo_apagado"]})
                        flash("Tarefa reaberta. O motivo ficou no histórico"
                              + (" e o carimbo de conclusão saiu."
                                 if volta["carimbo_apagado"] else "."),
                              "success")
                    return redirect(url_for("task_detail", task_id=task_id))
                if (row["evidence_required"]
                        and not db.get_attachments("TASK", task_id)):
                    flash("Esta tarefa exige ao menos uma evidência antes da "
                          "conclusão. Anexe a evidência aqui ao lado e conclua "
                          "em seguida.", "danger")
                else:
                    db.update_task(task_id, {"status": "CONCLUIDA"},
                                   int(current_user()["id"]))
                    audit("TASK_CONCLUIDA", "TASK", task_id,
                          {"status": "CONCLUIDA"})
                    flash("Tarefa concluída.", "success")
                    # «ENCERREI A TAREFA E O EXPEDIENTE SEGUE ATIVO» — o
                    # relato #24. O sistema não fecha sozinho (o esquema
                    # permite várias tarefas por expediente, e fechar na
                    # primeira deixaria trabalho sem quem cobre), mas para de
                    # ficar calado: diz o que sobrou e manda ao lugar de
                    # encerrar.
                    with db.connect() as _c:
                        recado = EXPT.recado_da_tarefa_concluida(_c, task_id)
                    if recado and not recado["ja_encerrado"]:
                        flash(
                            f"Esta tarefa é do expediente "
                            f"{recado['protocolo']} — {recado['assunto']}. "
                            f"{recado['recado']}"
                            + ("" if recado["abertas"] else
                               " Encerre-o na ficha dele."),
                            "warning")
                return redirect(url_for("task_detail", task_id=task_id))
            elif action in ("passar", "passar_substituto", "devolver"):
                # O TRÂNSITO DE RESPONSABILIDADE — a segunda metade do #59, no
                # desenho simples: uma ação «Passar para…», com motivo escrito, e
                # o nome de quem passou na linha do tempo.
                #
                #   QUEM PASSA É QUEM TEM LOGIN, e não só quem responde: medido em
                #   17/09/2026, **79 das 95** tarefas não têm responsável definido,
                #   e uma regra do tipo «só quem responde passa» deixaria a maior
                #   parte do serviço sem ninguém que pudesse movê-lo. O que protege
                #   a casa é o rastro.
                #
                #   AS DUAS PORTAS DE UM TOQUE — «passar ao substituto» e «devolver
                #   a quem criou» — são o mesmo ato com o destino já escolhido; o
                #   motivo continua sendo escrito, e o domínio continua recusando
                #   destino inativo, destino vazio e motivo curto.
                if action == "passar_substituto":
                    destino = row["backup_user_id"]
                    faltando = ("Esta tarefa não tem substituto definido. Escolha a "
                                "pessoa em «Responsável substituto», salve, e passe "
                                "em seguida.")
                elif action == "devolver":
                    destino = row["created_by"]
                    faltando = ("Esta tarefa não tem quem a criou registrado — ela "
                                "veio do acervo ou foi criada pelo próprio sistema. "
                                "Escolha a pessoa na lista.")
                else:
                    destino = parse_int(request.form.get("para_user_id"))
                    faltando = "Escolha a pessoa que vai receber a tarefa."
                if destino is None:
                    flash(faltando, "danger")
                else:
                    try:
                        with db.transaction() as con:
                            passagem = TP.passar_para(
                                con, task_id, destino,
                                request.form.get("motivo", ""),
                                int(current_user()["id"]), db.now())
                    except TP.ProcessoError as erro:
                        flash(str(erro), "danger")
                    else:
                        audit("TASK_PASSADA", "TASK", task_id,
                              {"de": passagem["de"], "para": passagem["para"],
                               "status": passagem["status"],
                               "motivo": passagem["motivo"]})
                        flash(f"Tarefa passada para {passagem['para']}. "
                              "O motivo ficou no histórico.", "success")
                return redirect(url_for("task_detail", task_id=task_id))
            elif action == "note":
                note = request.form.get("note", "").strip()
                tipo_and = request.form.get("tipo_andamento")
                if not note:
                    flash("Escreva o andamento.", "danger")
                else:
                    # Anexo do cumprimento / andamento (07/10/2026, Beatriz):
                    # o mesmo formulário do histórico aceita PDF/imagem/doc e
                    # grava em attachments(TASK) + menciona o nome na nota.
                    anexos_info = []
                    files = [f for f in request.files.getlist("anexo_andamento")
                             if f and f.filename]
                    if files:
                        target = (archive_root() / "Evidencias"
                                  / safe_component(row["sector"] or "Geral")
                                  / f"Tarefa-{task_id:05d}")
                        desc = ("Documento do cumprimento"
                                if TP.normalizar_tipo_andamento(tipo_and) == "CUMPRIDO"
                                else "Anexo do andamento")
                        for fs in files:
                            info = save_upload(fs, target)
                            att = db.add_attachment(
                                "TASK", task_id, info,
                                int(current_user()["id"]), desc)
                            anexos_info.append(info["original_name"])
                            audit("TASK_ANDAMENTO_ANEXO", "TASK", task_id,
                                  {"attachment_id": att,
                                   "sha256": info["sha256"],
                                   "tipo": TP.normalizar_tipo_andamento(tipo_and)})
                        nomes = ", ".join(anexos_info)
                        note = f"{note}\nAnexo: {nomes}"
                    note = TP.texto_andamento_com_tipo(tipo_and, note)
                    destino = parse_int(request.form.get("para_user_id"))
                    atalho = request.form.get("passar_destino")
                    if atalho == "substituto":
                        destino = row["backup_user_id"]
                    elif atalho == "criador":
                        destino = row["created_by"]
                    notificar = parse_int(request.form.get("notificar_user_id"))
                    if notificar is None and destino is None:
                        with db.connect() as _c:
                            mencionados = TP.usuarios_mencionados_no_texto(_c, note)
                        if mencionados:
                            notificar = mencionados[0]
                    nota_ok = True
                    if destino is not None:
                        try:
                            with db.transaction() as con:
                                passagem = TP.passar_para(
                                    con, task_id, destino, note,
                                    int(current_user()["id"]), db.now())
                        except TP.ProcessoError as erro:
                            # Relato #109 — a resposta (andamento) não pode
                            # sumir quando a passagem falha: grava a NOTA
                            # limpa no histórico e avisa à parte sobre o
                            # trâmite que não andou.
                            db.add_task_note(task_id, int(current_user()["id"]),
                                             note, tipo=tipo_and)
                            audit("TASK_NOTE", "TASK", task_id,
                                  {"via": "andamento", "passagem": "recusada",
                                   "tipo": TP.normalizar_tipo_andamento(tipo_and)})
                            flash(
                                "Andamento registrado no histórico. "
                                f"A passagem não foi feita: {erro}",
                                "warning",
                            )
                        else:
                            audit("TASK_PASSADA", "TASK", task_id,
                                  {"de": passagem["de"], "para": passagem["para"],
                                   "status": passagem["status"],
                                   "motivo": passagem["motivo"],
                                   "via": "andamento"})
                            flash(f"Andamento registrado e tarefa passada para "
                                  f"{passagem['para']}.", "success")
                    elif notificar is not None:
                        try:
                            with db.transaction() as con:
                                aviso = TP.notificar_para(
                                    con, task_id, notificar, note,
                                    int(current_user()["id"]), db.now(),
                                    tipo=tipo_and)
                        except TP.ProcessoError as erro:
                            nota_ok = False
                            flash(str(erro), "danger")
                        else:
                            audit("TASK_NOTIFICACAO", "TASK", task_id,
                                  {"para": aviso["para_user_id"],
                                   "via": "andamento"})
                            flash(
                                f"Andamento registrado. {aviso['para']} verá "
                                "esta tarefa em «Pediram minha resposta» até "
                                "registrar a resposta.",
                                "success",
                            )
                    else:
                        db.add_task_note(task_id, int(current_user()["id"]), note,
                                         tipo=tipo_and)
                        audit("TASK_NOTE", "TASK", task_id,
                              {"tipo": TP.normalizar_tipo_andamento(tipo_and)})
                        flash("Andamento registrado.", "success")
                    # CUMPRIDO FECHA A PENDÊNCIA (07/10/2026, Beatriz):
                    # marcar Cumprido no histórico conclui a tarefa
                    # (CONCLUIDA) para ela sair de «Em aberto» / pendências.
                    # Anexo continua opcional; se veio neste POST, já foi
                    # gravado acima e conta como evidência.
                    if nota_ok and TP.normalizar_tipo_andamento(tipo_and) == "CUMPRIDO":
                        # Com ou sem anexo: Cumprido dá baixa na pendência
                        # (pedido Beatriz 07/10/2026). O anexo, se veio, já
                        # foi gravado acima.
                        atual = db.get_task(task_id)
                        if atual and atual["status"] not in (
                                "CONCLUIDA", "CANCELADA"):
                            db.update_task(
                                task_id, {"status": "CONCLUIDA"},
                                int(current_user()["id"]))
                            audit("TASK_CONCLUIDA", "TASK", task_id,
                                  {"status": "CONCLUIDA",
                                   "via": "cumprido"})
                            flash(
                                "Cumprido: tarefa concluída e saiu das "
                                "pendências.",
                                "success",
                            )
                            with db.connect() as _c:
                                recado = EXPT.recado_da_tarefa_concluida(
                                    _c, task_id)
                            if recado and not recado["ja_encerrado"]:
                                flash(
                                    f"Esta tarefa é do expediente "
                                    f"{recado['protocolo']} - "
                                    f"{recado['assunto']}. "
                                    f"{recado['recado']}"
                                    + ("" if recado["abertas"] else
                                       " Encerre-o na ficha dele."),
                                    "warning",
                                )
                    return redirect(url_for("task_detail", task_id=task_id))
        s = settings_dict()
        sectors = json_list(s.get("sectors", "[]"), [])
        users = db.list_users(active_only=True)
        row = db.get_task(task_id)
        history = db.task_history(task_id)
        attachments = db.get_attachments("TASK", task_id)
        # OS DOCUMENTOS DO EXPEDIENTE À VISTA DE QUEM CUMPRE (12/10/2026): a
        # tarefa da averbação de divórcio de uma escrevente (#318) nasceu do malote, e o
        # mandado estava guardado no expediente — a tarefa não o mostrava e não
        # dizia onde procurar.
        # A PASTA DO PROCESSO (fase 1, mesmo dia): não só o expediente, mas o
        # assento, a matrícula, a prenotação, o protocolo, o rascunho — e os
        # documentos de todos eles numa lista só (`processo_pasta.py`).
        import processo_pasta as PASTA
        with db.connect() as _c:
            pasta_vinculos = PASTA.vinculos(_c, task_id)
            pasta_docs = PASTA.documentos(_c, task_id)
            # Os retirados com motivo (relato #135) vêm à parte, e não somem.
            pasta_retirados = PASTA.documentos_retirados(_c, task_id)
            import processo_especies as ESP
            tipo = ESP.tipo_do_processo(_c, dict(row))
        for v in pasta_vinculos:
            # Tela que mudou de endereço não derruba a ficha: a peça aparece sem link.
            try:
                v["url"] = url_for(v["endpoint"], **{v["arg"]: v["item_id"]}) if v["endpoint"] else None
            except Exception:                                   # noqa: BLE001
                v["url"] = None
        return render_template("task_detail.html", row=row, history=history, attachments=attachments, users=users,
                               sectors=sectors, pasta_vinculos=pasta_vinculos, pasta_docs=pasta_docs,
                               pasta_retirados=pasta_retirados,
                               pasta_tipos=PASTA.TIPOS, tipo=tipo,
                               suspensao=TS.situacao(row), MODOS_DE_SUSPENDER=TS.MODOS,
                               amanha=(date.today() + timedelta(days=1)).isoformat())

    @app.route("/tarefas/<int:task_id>/evidence", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def task_evidence(task_id):
        row = db.get_task(task_id)
        if not row: abort(404)
        files = [f for f in request.files.getlist("file") if f and f.filename]
        if not files:
            flash("Selecione um arquivo.", "danger")
        else:
            target = archive_root() / "Evidencias" / safe_component(row["sector"] or "Geral") / f"Tarefa-{task_id:05d}"
            for fs in files:
                info = save_upload(fs, target)
                att = db.add_attachment("TASK", task_id, info, int(current_user()["id"]), request.form.get("description"))
                db.add_task_note(task_id, int(current_user()["id"]), f"Evidencia anexada: {info['original_name']} (SHA-256 {info['sha256']})")
                audit("TASK_EVIDENCE_ADDED", "TASK", task_id, {"attachment_id": att, "sha256": info["sha256"]})
            if len(files) == 1:
                flash("Evidencia anexada e registrada no historico.", "success")
            else:
                flash(f"{len(files)} evidencias anexadas e registradas no historico.", "success")
        return redirect(url_for("task_detail", task_id=task_id))

    @app.route("/tarefas/<int:task_id>/dossie")
    @login_required
    def task_dossier(task_id):
        row = db.get_task(task_id)
        if not row: abort(404)
        history = db.task_history(task_id)
        attachments = db.get_attachments("TASK", task_id)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            html = render_template("dossier.html", row=row, history=history, attachments=attachments)
            zf.writestr("dossie.html", html)
            zf.writestr("dados.json", json.dumps({k: row[k] for k in row.keys()}, ensure_ascii=False, default=str, indent=2))
            for a in attachments:
                p = Path(a["stored_path"])
                if p.exists():
                    zf.write(p, Path("evidencias") / a["stored_name"])
        buffer.seek(0)
        audit("TASK_DOSSIER_EXPORTED", "TASK", task_id)
        return send_file(buffer, as_attachment=True, download_name=f"Dossie_Tarefa_{task_id:05d}.zip", mimetype="application/zip")

    @app.route("/inspecoes")
    @login_required
    def inspections():
        return render_template("inspections.html", rows=db.list_inspections())

    @app.route("/inspecoes/<int:inspection_id>", methods=["GET", "POST"])
    @login_required
    @roles_required(*PRATICA, metodos=("POST",))
    def inspection_detail(inspection_id):
        row = db.get_inspection(inspection_id)
        if not row: abort(404)
        if request.method == "POST":
            start_date = parse_date(request.form.get("start_date"))
            if not start_date:
                flash("Informe a data-base da ciência/intimação.", "danger")
            else:
                db.set_inspection_start_date(inspection_id, start_date, int(current_user()["id"]))
                audit("INSPECTION_START_DATE_SET", "INSPECTION", inspection_id, {"start_date": start_date})
                flash("Prazos calculados a partir da data-base informada.", "success")
                return redirect(url_for("inspection_detail", inspection_id=inspection_id))
        tasks_rows = [t for t in db.list_tasks(limit=2000) if t["inspection_id"] == inspection_id]
        sectors = sorted({t["sector"] for t in tasks_rows if t["sector"]})
        users = db.list_users(active_only=True)
        return render_template("inspection_detail.html", row=row, tasks=tasks_rows, sectors=sectors, users=users)

    @app.route("/inspecoes/<int:inspection_id>/atribuir", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER")
    def inspection_assign(inspection_id):
        sector = request.form.get("sector", "").strip()
        if not sector:
            flash("Selecione o setor.", "danger")
        else:
            count = db.bulk_assign_inspection_tasks(inspection_id, sector, parse_int(request.form.get("assigned_user_id")), parse_int(request.form.get("backup_user_id")), int(current_user()["id"]))
            audit("INSPECTION_BULK_ASSIGN", "INSPECTION", inspection_id, {"sector":sector,"count":count})
            flash(f"{count} tarefas do setor {sector} foram atualizadas.", "success")
        return redirect(url_for("inspection_detail", inspection_id=inspection_id))

    @app.route("/recorrencias", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER")
    def recurrences():
        s = settings_dict(); sectors = json_list(s.get("sectors", "[]"), [])
        users = db.list_users(active_only=True)
        if request.method == "POST":
            next_due = parse_date(request.form.get("next_due_date"))
            if not request.form.get("title", "").strip() or not next_due:
                flash("Informe título e próximo vencimento.", "danger")
            else:
                rid = db.create_recurrence({
                    "title": request.form.get("title"), "system_name": request.form.get("system_name"), "sector": request.form.get("sector"),
                    "frequency": request.form.get("frequency"), "due_day": parse_int(request.form.get("due_day")), "due_month": parse_int(request.form.get("due_month")),
                    "lead_days": parse_int(request.form.get("lead_days")) or 5, "assigned_user_id": parse_int(request.form.get("assigned_user_id")),
                    "backup_user_id": parse_int(request.form.get("backup_user_id")), "next_due_date": next_due, "evidence_required": 1 if request.form.get("evidence_required") else 0,
                    "notes": request.form.get("notes"),
                }, int(current_user()["id"]))
                audit("RECURRENCE_CREATED", "RECURRENCE", rid)
                flash("Obrigação recorrente criada.", "success")
                return redirect(url_for("recurrences"))
        return render_template("recurrences.html", rows=db.list_recurrences(), users=users, sectors=sectors, frequencies=FREQUENCIES)

    @app.route("/recorrencias/<int:recurrence_id>", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER")
    def recurrence_detail(recurrence_id):
        row = db.get_recurrence(recurrence_id)
        if not row: abort(404)
        users = db.list_users(active_only=True)
        sectors = json_list(db.get_setting("sectors", "[]"), [])
        if request.method == "POST":
            db.update_recurrence(recurrence_id, {
                "title": request.form.get("title"), "system_name": request.form.get("system_name"), "sector": request.form.get("sector"),
                "frequency": request.form.get("frequency"), "due_day": parse_int(request.form.get("due_day")), "due_month": parse_int(request.form.get("due_month")),
                "lead_days": parse_int(request.form.get("lead_days")) or 5, "assigned_user_id": parse_int(request.form.get("assigned_user_id")),
                "backup_user_id": parse_int(request.form.get("backup_user_id")), "active": 1 if request.form.get("active") else 0,
                "next_due_date": parse_date(request.form.get("next_due_date")), "evidence_required": 1 if request.form.get("evidence_required") else 0,
                "notes": request.form.get("notes"),
            })
            audit("RECURRENCE_UPDATED", "RECURRENCE", recurrence_id)
            flash("Obrigação recorrente atualizada.", "success")
            return redirect(url_for("recurrence_detail", recurrence_id=recurrence_id))
        return render_template("recurrence_detail.html", row=row, users=users, sectors=sectors, frequencies=FREQUENCIES)

    @app.route("/checklists", methods=["GET", "POST"])
    @login_required
    @roles_required(*PRATICA, metodos=("POST",))
    def checklists():
        user = current_user()
        if request.method == "POST":
            if user["role"] not in {"ADMIN", "MANAGER"}:
                abort(403)
            try:
                tid = db.create_checklist_template(
                    request.form.get("name", ""),
                    request.form.get("sector") or None,
                    request.form.get("items", "").splitlines(),
                )
                audit("CHECKLIST_TEMPLATE_CREATED", "CHECKLIST_TEMPLATE", tid)
                flash("Modelo de checklist criado.", "success")
            except ValueError as exc:
                flash(str(exc), "danger")
            return redirect(url_for("checklists"))
        sectors = json_list(db.get_setting("sectors", "[]"), [])
        return render_template("checklists.html", rows=db.list_checklist_templates(), sectors=sectors)

    @app.route("/checklists/<int:template_id>/start", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def checklist_start(template_id):
        run_id = db.start_checklist(template_id, request.form.get("reference", ""), int(current_user()["id"]))
        audit("CHECKLIST_STARTED", "CHECKLIST", run_id, {"template_id": template_id})
        return redirect(url_for("checklist_run", run_id=run_id))

    @app.route("/checklists/run/<int:run_id>", methods=["GET", "POST"])
    @login_required
    @roles_required(*PRATICA, metodos=("POST",))
    def checklist_run(run_id):
        run, items = db.get_checklist_run(run_id)
        if not run: abort(404)
        if request.method == "POST":
            # LD13: «abc» numa caixa era 500; a que não é número não se marcou.
            checked = {n for n in map(SEGWEB.numero_digitado, request.form.getlist("checked"))
                       if n is not None}
            notes = {int(i["id"]): request.form.get(f"note_{i['id']}", "") for i in items}
            try:
                db.save_checklist_run(run_id, checked, notes, request.form.get("action") == "finish")
                audit("CHECKLIST_UPDATED", "CHECKLIST", run_id, {"finish": request.form.get("action") == "finish"})
                flash("Checklist salvo.", "success")
                if request.form.get("action") == "finish":
                    return redirect(url_for("checklists"))
            except ValueError as exc:
                flash(str(exc), "danger")
        run, items = db.get_checklist_run(run_id)
        return render_template("checklist_run.html", run=run, items=items)

    @app.route("/ti", methods=["GET", "POST"])
    @login_required
    @roles_required(*PRATICA, metodos=("POST",))
    def assets():
        users = db.list_users(active_only=True)
        if request.method == "POST":
            aid = db.create_asset({
                "kind": request.form.get("kind"), "name": request.form.get("name"), "identifier": request.form.get("identifier"),
                "location": request.form.get("location"), "responsible_user_id": parse_int(request.form.get("responsible_user_id")),
                "status": request.form.get("status"), "expiry_date": parse_date(request.form.get("expiry_date")), "last_check_date": parse_date(request.form.get("last_check_date")),
                "notes": request.form.get("notes"),
            }, int(current_user()["id"]))
            audit("ASSET_CREATED", "ASSET", aid)
            flash("Item de TI/infraestrutura cadastrado.", "success")
            return redirect(url_for("assets"))
        return render_template("assets.html", rows=db.list_assets(), users=users)

    @app.route("/ti/<int:asset_id>", methods=["GET", "POST"])
    @login_required
    @roles_required(*PRATICA, metodos=("POST",))
    def asset_detail(asset_id):
        row = db.get_asset(asset_id)
        if not row: abort(404)
        users = db.list_users(active_only=True)
        if request.method == "POST":
            db.update_asset(asset_id, {
                "kind": request.form.get("kind"), "name": request.form.get("name"), "identifier": request.form.get("identifier"),
                "location": request.form.get("location"), "responsible_user_id": parse_int(request.form.get("responsible_user_id")),
                "status": request.form.get("status"), "expiry_date": parse_date(request.form.get("expiry_date")), "last_check_date": parse_date(request.form.get("last_check_date")),
                "notes": request.form.get("notes"),
            })
            audit("ASSET_UPDATED", "ASSET", asset_id)
            flash("Item atualizado.", "success")
            return redirect(url_for("asset_detail", asset_id=asset_id))
        return render_template("asset_detail.html", row=row, users=users)

    @app.route("/lgpd", methods=["GET", "POST"])
    @login_required
    @roles_required(*PRATICA, metodos=("POST",))
    def lgpd():
        users = db.list_users(active_only=True)
        if request.method == "POST":
            lid = db.create_lgpd_item({
                "item_type": request.form.get("item_type"), "title": request.form.get("title"), "owner_user_id": parse_int(request.form.get("owner_user_id")),
                "status": request.form.get("status"), "review_date": parse_date(request.form.get("review_date")), "notes": request.form.get("notes"),
            }, int(current_user()["id"]))
            audit("LGPD_ITEM_CREATED", "LGPD", lid)
            flash("Item de governança/LGPD cadastrado.", "success")
            return redirect(url_for("lgpd"))
        return render_template("lgpd.html", rows=db.list_lgpd_items(), users=users)

    @app.route("/lgpd/<int:item_id>", methods=["GET", "POST"])
    @login_required
    @roles_required(*PRATICA, metodos=("POST",))
    def lgpd_detail(item_id):
        row = db.get_lgpd_item(item_id)
        if not row: abort(404)
        users = db.list_users(active_only=True)
        if request.method == "POST":
            db.update_lgpd_item(item_id, {
                "item_type": request.form.get("item_type"), "title": request.form.get("title"), "owner_user_id": parse_int(request.form.get("owner_user_id")),
                "status": request.form.get("status"), "review_date": parse_date(request.form.get("review_date")), "notes": request.form.get("notes"),
            })
            audit("LGPD_ITEM_UPDATED", "LGPD", item_id)
            flash("Item de LGPD/governança atualizado.", "success")
            return redirect(url_for("lgpd_detail", item_id=item_id))
        return render_template("lgpd_detail.html", row=row, users=users)

    @app.route("/atendimento", methods=["GET", "POST"])
    @login_required
    @roles_required(*PRATICA, metodos=("POST",))
    def service_queue():
        if request.method == "POST" and request.form.get("action") == "new":
            tid = db.create_ticket(bool(request.form.get("priority")), request.form.get("service_type"))
            audit("SERVICE_TICKET_CREATED", "TICKET", tid)
            return redirect(url_for("service_queue"))
        return render_template("service_queue.html", rows=db.list_tickets_today())

    @app.route("/atendimento/<int:ticket_id>/<action>", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def ticket_action(ticket_id, action):
        if action not in {"call", "start", "finish"}: abort(400)
        db.update_ticket(ticket_id, action, int(current_user()["id"]))
        audit("SERVICE_TICKET_ACTION", "TICKET", ticket_id, {"action": action})
        return redirect(url_for("service_queue"))

    @app.route("/relatorios/selos")
    @roles_required("ADMIN", "MANAGER", "AUDITOR")
    def relatorio_selos():
        """O endereço antigo do razão dos selos — **agora ele aponta para lá**.

        Havia **duas** telas chamadas «Selos emitidos» no menu, com o mesmo
        rótulo e réguas diferentes para a mesma palavra: elas discordavam em
        **7.762 selos** sobre o que é «não usado», e a lista de lá perdia o
        último dia de todo período. **Duas réguas para a mesma pergunta**, e
        quem lesse uma não saberia o que a outra diria.

        Sobrou **uma**, `/selos`, com o que a antiga tinha de melhor dentro. Este
        endereço continua respondendo — quem o tem nos favoritos não encontra
        uma porta fechada —, e **traduz os nomes dos filtros**: os de lá eram
        `de`, `ate` e `usuario`, e os de cá são `inicio`, `fim` e `quem`.
        Redirecionar sem traduzir deixaria quem voltasse pelo favorito na tela
        sem filtro nenhum, achando que a busca quebrou.
        """
        novos = {
            "inicio": request.args.get("de") or request.args.get("inicio"),
            "fim": request.args.get("ate") or request.args.get("fim"),
            "quem": request.args.get("usuario") or request.args.get("quem"),
            "atribuicao": request.args.get("atribuicao"),
            "caminho": request.args.get("caminho"),
            "tipo": request.args.get("tipo"),
            "numero": request.args.get("numero"),
            "situacao": request.args.get("situacao"),
            "agrupar": request.args.get("agrupar"),
        }
        limpos = {k: v for k, v in novos.items() if (v or "").strip()}
        return redirect(url_for("selos_emitidos_lista", **limpos))

    @app.route("/relatorios")
    @login_required
    def reports():
        alert_days = parse_int(db.get_setting("alert_days", "5")) or 5
        stats = db.dashboard_stats(alert_days)
        tasks_rows = db.list_tasks("ABERTAS", limit=200)
        exp_rows = db.list_expedientes(limit=200, only_open=True)
        service_metrics = db.service_metrics_today()
        return render_template("reports.html", stats=stats, tasks=tasks_rows, expedientes=exp_rows, service_metrics=service_metrics)

    def csv_response(filename: str, headers: list[str], rows: list[list[object]]):
        # A PLANILHA NÃO LEVA FÓRMULA (revisão de segurança de 26/10/2026,
        # achado transversal 2): todo CSV da casa sai por `csv_seguro`, que põe
        # cada campo entre aspas e neutraliza o texto que começa com = + - @.
        import csv_seguro as CSVS
        return CSVS.resposta(filename, headers, rows)

    @app.route("/relatorios/tarefas.csv")
    @login_required
    def tasks_csv():
        rows = db.list_tasks(limit=5000)
        return csv_response("tarefas.csv", ["ID","Título","Setor","Sistema","Prioridade","Status","Início","Vencimento","Responsável","Substituto","Evidências"], [[r["id"],r["title"],r["sector"],r["system_name"],r["priority"],r["status"],r["start_date"],r["due_date"],r["assigned_name"],r["backup_name"],r["evidence_count"]] for r in rows])

    @app.route("/relatorios/expedientes.csv")
    @login_required
    def expedientes_csv():
        rows = db.list_expedientes(limit=5000)
        return csv_response("expedientes.csv", ["Protocolo","Entrada","Referência","Remetente","Assunto","Classificação","Setor","Recebido","Prazo","Prioridade","Responsável","Etapa"], [[r["internal_protocol"],r["source"],r["external_reference"],r["sender"],r["subject"],r["category"],r["sector"],r["received_at"],r["deadline_date"],r["priority"],r["assigned_name"],r["stage"]] for r in rows])

    @app.route("/usuarios", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN")
    def users():
        if request.method == "POST":
            action = request.form.get("action")
            if action == "create":
                password = request.form.get("password", "")
                ok, msg = db.validate_password(password)
                if not ok:
                    flash(msg, "danger")
                else:
                    try:
                        # O ROBO TEM RESPONSAVEL (ordem do oficial, 26/10/2026):
                        # a pessoa que responde por ele se escolhe na criacao, e
                        # se confere ANTES de criar — conta pela metade nao fica.
                        resp_id = parse_int(request.form.get("robo_responsavel_id"))
                        if request.form.get("eh_robo") == "1" and resp_id:
                            with db.connect() as con:
                                IDR.validar_responsavel_de_robo(con, resp_id)
                        uid = db.create_user(request.form.get("username", ""), request.form.get("full_name", ""), password, request.form.get("role", "USER"), int(current_user()["id"]), eh_robo=1 if request.form.get("eh_robo") == "1" else 0)
                        audit("USER_CREATED", "USER", uid)
                        criado = db.get_user(uid)
                        if criado and int(criado["eh_robo"] or 0) and resp_id:
                            with db.transaction() as con:
                                IDR.definir_responsavel_do_robo(con, uid, resp_id)
                            audit("USER_ROBO_RESPONSAVEL_ALTERADO", "USER", uid,
                                  {"robo_responsavel_id": resp_id})
                        if criado and int(criado["eh_robo"] or 0) and not resp_id:
                            flash("Usuário criado. É conta de robô SEM responsável: o "
                                  "login funciona, e toda ação dele fica com o aviso "
                                  "«robô sem responsável» até alguém ser escolhido "
                                  "na coluna Robô.", "warning")
                        else:
                            flash("Usuário criado.", "success")
                    except ValueError as exc:
                        flash(str(exc), "danger")
            elif action == "editar":
                # RELATO DO OFICIAL, 08/09/2026: precisava corrigir nome e
                # usuário de um cadastro já criado, e a tela só sabia CRIAR.
                uid = parse_int(request.form.get("user_id"))
                target = db.get_user(uid) if uid else None
                if not target:
                    flash("Usuário inválido.", "danger")
                    return redirect(url_for("users"))
                novo_role = (request.form.get("role") or "").strip().upper()
                # O ADMIN NUNCA SE TRANCA DO LADO DE FORA — a mesma regra do
                # `toggle` de baixo, aqui contra se rebaixar a si mesmo.
                if (int(target["id"]) == int(current_user()["id"])
                        and novo_role and novo_role != "ADMIN"):
                    flash("Não é possível rebaixar o próprio perfil durante "
                          "a sessão.", "danger")
                    return redirect(url_for("users"))
                try:
                    db.update_user(
                        uid, request.form.get("username", ""),
                        request.form.get("full_name", ""),
                        novo_role or target["role"],
                        eh_robo=1 if request.form.get("eh_robo") == "1" else 0)
                    audit("USER_EDITED", "USER", uid, {
                        "username": request.form.get("username", "").strip(),
                        "full_name": request.form.get("full_name", "").strip(),
                        "role": novo_role or target["role"]})
                    flash("Usuário atualizado.", "success")
                except ValueError as exc:
                    flash(str(exc), "danger")
            elif action == "eh_robo":
                uid = parse_int(request.form.get("user_id"))
                if uid:
                    marca = 1 if request.form.get("eh_robo") == "1" else 0
                    alvo = db.get_user(uid)
                    if marca and alvo and str(alvo["role"]).upper() not in ("USER", "AUDITOR"):
                        # a mesma regra de `create_user` (22/10/2026, A6)
                        flash("Robô só pode ter o perfil USER ou AUDITOR. Troque o "
                              "perfil antes de marcar como robô.", "danger")
                        return redirect(url_for("users"))
                    # O RESPONSAVEL VAI JUNTO COM A MARCA (26/10/2026): robo
                    # diz a mando de quem age. Desmarcar limpa o responsavel —
                    # a pessoa responde por si.
                    resp_id = parse_int(request.form.get("robo_responsavel_id")) if marca else None
                    try:
                        with db.transaction() as con:
                            banco(con).escrever("UPDATE users SET eh_robo=%s WHERE id=%s",
                                                (marca, uid))
                            IDR.definir_responsavel_do_robo(con, uid, resp_id)
                    except ValueError as exc:
                        flash(str(exc), "danger")
                        return redirect(url_for("users"))
                    audit("USER_EH_ROBO_ALTERADO", "USER", uid,
                          {"eh_robo": marca, "robo_responsavel_id": resp_id})
                    if marca and not resp_id:
                        flash("Marca de robô gravada, SEM responsável: toda ação dele "
                              "fica com o aviso «robô sem responsável».", "warning")
                    else:
                        flash("Marca de robô atualizada.", "success")
            elif action == "responsavel_rotinas":
                # QUEM RESPONDE PELAS ROTINAS AUTOMATICAS (26/10/2026): backup,
                # CNIB, malote, envio a CENSEC, scripts. So ADMIN ou MANAGER
                # (revisao de seguranca, 26/10). Vazio = o primeiro ADMIN ativo
                # que nao e robo.
                resp_id = parse_int(request.form.get("responsavel_rotinas"))
                try:
                    with db.connect() as con:
                        IDR.validar_responsavel_das_rotinas(con, resp_id)
                except ValueError as exc:
                    flash(str(exc), "danger")
                    return redirect(url_for("users"))
                db.set_settings({IDR.CHAVE_RESPONSAVEL: str(resp_id) if resp_id else ""})
                audit("RESPONSAVEL_ROTINAS_ALTERADO", "SETTINGS", None,
                      {"user_id": resp_id})
                flash("Responsável pelas rotinas automáticas gravado.", "success")
            elif action == "funcao":
                # Em que qualidade a pessoa assina. Vai impressa embaixo da
                # assinatura no orcamento, no protocolo de recepcao e no
                # comprovante de prenotacao: quem assina por delegacao tem de
                # dizer em que qualidade o faz (Lei 8.935/94, arts. 20 e 21).
                uid = parse_int(request.form.get("user_id"))
                funcao = (request.form.get("funcao") or "").strip() or None
                if uid:
                    with db.transaction() as con:
                        banco(con).escrever("UPDATE users SET funcao=%s WHERE id=%s", (funcao, uid))
                    audit("USER_FUNCAO_ALTERADA", "USER", uid, {"funcao": funcao})
                    flash("Função atualizada.", "success")
            elif action == "toggle":
                uid = parse_int(request.form.get("user_id"))
                target = db.get_user(uid) if uid else None
                if target and int(target["id"]) == int(current_user()["id"]):
                    flash("Não é possível desativar o próprio usuário durante a sessão.", "danger")
                elif target:
                    db.set_user_active(uid, not bool(target["active"]))
                    audit("USER_STATUS_CHANGED", "USER", uid, {"active": not bool(target["active"])})
                    flash("Status alterado.", "success")
            elif action == "reset":
                uid = parse_int(request.form.get("user_id")); password = request.form.get("new_password", "")
                ok, msg = db.validate_password(password)
                if uid and ok:
                    db.reset_password(uid, password); audit("PASSWORD_RESET", "USER", uid)
                    # A senha nova derruba as sessões abertas com a velha (M3) —
                    # menos a desta tela, quando o ADMIN redefine a própria.
                    if int(uid) == int(current_user()["id"]):
                        session["cred"] = carimbo_da_senha(uid)
                    flash("Senha redefinida. Quem estava dentro com a senha "
                          "antiga terá de entrar de novo.", "success")
                else:
                    flash(msg if not ok else "Usuário inválido.", "danger")
            elif action == "destravar":
                # A ESPERA DO LOGIN (A4) SE DESFAZ AQUI, para todas as máquinas:
                # é o caminho de quem errou a senha e já falou com o ADMIN.
                uid = parse_int(request.form.get("user_id"))
                target = db.get_user(uid) if uid else None
                if target:
                    eu = current_user()
                    db.log(int(eu["id"]), eu["username"], LESP.DESTRAVADO, "USER",
                           int(target["id"]),
                           LESP.detalhes(LESP.chave(secret_key, target["username"]),
                                         usuario=target["username"]),
                           request.remote_addr)
                    flash(f"Tentativas de login zeradas para {target['username']}.",
                          "success")
            elif action == "cargos":
                # OS CARGOS ERAM FIXOS NO CÓDIGO — pedido do oficial em
                # 08/09/2026. `caixa_schema.FUNCOES` continua sendo o de
                # fábrica; a partir daqui quem manda é o que estiver
                # gravado, um por linha, como já se faz com categorias,
                # fontes e setores em Configurações.
                novos = [x.strip() for x in
                        request.form.get("funcoes_cargos", "").splitlines()
                        if x.strip()]
                if not novos:
                    flash("Informe ao menos um cargo — a lista não pode "
                          "ficar vazia.", "danger")
                else:
                    db.set_settings({"funcoes_cargos": json.dumps(
                        novos, ensure_ascii=False)})
                    audit("CARGOS_ALTERADOS", "SETTINGS", None, {"cargos": novos})
                    flash("Cargos atualizados.", "success")
            return redirect(url_for("users"))
        from caixa_schema import FUNCOES
        linhas = db.list_users()
        with db.connect() as con:
            em_espera = LESP.em_espera_na_casa(con, linhas, secret_key)
            # A IDENTIDADE DOS ROBOS (26/10/2026): quem pode responder, quem
            # responde pelas rotinas, e o aviso do que grava sem dizer quem e.
            pessoas = IDR.pessoas_que_podem_responder(con, por="robo")
            pessoas_rotinas = IDR.pessoas_que_podem_responder(con, por="rotinas")
            resp_rotinas = IDR.responsavel_das_rotinas(con)
            identidade = IDR.conferencia(con)
        return render_template(
            "users.html", rows=linhas, roles=ROLES, em_espera=em_espera,
            funcoes=json_list(db.get_setting("funcoes_cargos", ""), list(FUNCOES)),
            pessoas=pessoas, pessoas_rotinas=pessoas_rotinas,
            resp_rotinas=resp_rotinas, identidade=identidade)

    @app.route("/saude")
    def health():
        return {
            "product": "CartorioGestao",
            "app": APP_NAME,
            "version": VERSION,
            "unit": db.get_setting("unit_name", "Serventia Extrajudicial"),
            "hostname": socket.gethostname(),
            "ok": True,
        }

    @app.route("/rede")
    @login_required
    @roles_required("ADMIN", "MANAGER")
    def network_status():
        port = parse_int(db.get_setting("network_port", "8765")) or 8765
        discovery_port = parse_int(db.get_setting("discovery_port", "8766")) or 8766
        urls = [f"http://{ip}:{port}" for ip in lan_ipv4_addresses()]
        return render_template(
            "network.html", urls=urls, hostname=socket.gethostname(), port=port,
            discovery_port=discovery_port, discovery_enabled=db.get_setting("discovery_enabled", "1") == "1",
            install_dir=installed_app_dir(), data_dir=data_dir,
        )

    @app.route("/rede/cliente.zip")
    @login_required
    @roles_required("ADMIN", "MANAGER")
    def client_installer_zip():
        client_dir = installed_app_dir() / "installer" / "client"
        required = ["INSTALAR_CLIENTE.cmd", "instalar_cliente.ps1", "localizar_servidor.ps1", "diagnostico_cliente.ps1"]
        if not all((client_dir / name).exists() for name in required):
            abort(404)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in required:
                zf.write(client_dir / name, name)
            zf.writestr("LEIA-ME.txt", "Extraia todos os arquivos e execute INSTALAR_CLIENTE.cmd. Nao e necessario instalar Python no computador cliente.\n")
        buffer.seek(0)
        audit("CLIENT_INSTALLER_DOWNLOADED", "SYSTEM", None)
        return send_file(buffer, as_attachment=True, download_name="CartorioGestao_Acesso_Cliente.zip", mimetype="application/zip")

    @app.route("/atualizacoes", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN")
    def updates():
        updates_root = data_dir / "updates"
        incoming = updates_root / "incoming"
        staged = updates_root / "staged"
        incoming.mkdir(parents=True, exist_ok=True)
        staged.mkdir(parents=True, exist_ok=True)
        result_file = updates_root / "last_result.json"
        last_result = None
        if result_file.exists():
            try:
                last_result = json.loads(result_file.read_text(encoding="utf-8"))
            except Exception:
                last_result = {"status": "UNKNOWN", "message": "Resultado anterior ilegivel."}
        def preparacoes() -> list[dict]:
            itens: list[dict] = []
            for pasta in staged.iterdir():
                if not pasta.is_dir():
                    continue
                try:
                    meta = load_staged(pasta)
                    if meta["version"] != pasta.name:
                        raise UpdateError("Versao e pasta de preparacao nao correspondem.")
                    impacto = (meta.get("inspection") or {}).get("impact") or []
                    meta["impact_counts"] = {
                        nome: sum(1 for item in impacto if item.get("status") == nome)
                        for nome in ("NOVO", "ALTERADO", "IGUAL", "EXCLUIDO")
                    }
                    itens.append(meta)
                except (UpdateError, OSError, ValueError, json.JSONDecodeError) as exc:
                    itens.append({
                        "version": pasta.name, "state": "INVALID",
                        "load_error": str(exc), "stage_dir": str(pasta),
                    })
            return sorted(
                itens, key=lambda item: str(item.get("staged_at") or ""),
                reverse=True,
            )

        if request.method == "POST":
            action = request.form.get("action", "prepare")
            # O RETRATO DA INSTALACAO (14/10/2026): conferir o que mudou fora de
            # uma atualizacao, e o oficial assumir o estado instalado como base.
            if action in ("conferir_instalacao", "aceitar_retrato"):
                import retrato_da_instalacao as RET
                try:
                    if action == "conferir_instalacao":
                        r = RET.conferir(updates_root, installed_app_dir(), VERSION)
                        flash("Instalacao conferida: nada mudou fora de uma atualizacao."
                              if r["limpo"] else
                              f"Instalacao conferida: {len(r['alterados'])} alterado(s), "
                              f"{len(r['novos'])} novo(s) e {len(r['sumidos'])} "
                              "sumido(s) fora de uma atualizacao — veja a lista.",
                              "success" if r["limpo"] else "warning")
                    else:
                        RET.aceitar(updates_root, installed_app_dir(), VERSION,
                                    por=usuario_nome(),
                                    motivo=request.form.get("motivo", ""))
                        audit("INSTALACAO_RETRATO_ACEITO", "SYSTEM", None, {
                            "versao": VERSION, "motivo": request.form.get("motivo", "")})
                        flash("O estado instalado virou a base da conferencia.", "success")
                except (ValueError, OSError) as exc:
                    flash(str(exc), "danger")
                return redirect(url_for("updates"))
            if action == "prepare":
                upload = request.files.get("update_file")
                if not upload or not upload.filename:
                    flash("Selecione o arquivo de atualizacao (.cgu).", "danger")
                    return redirect(url_for("updates"))
                filename = safe_component(Path(upload.filename).name)
                if not filename.lower().endswith(".cgu"):
                    flash("Formato invalido. Use somente o pacote .cgu fornecido para esta versao.", "danger")
                    return redirect(url_for("updates"))
                package = incoming / (
                    f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{filename}"
                )
                upload.save(package)
                expected = request.form.get("expected_sha256", "").strip()
                try:
                    info = validate_and_stage(
                        package, staged, VERSION, expected,
                        require_expected_hash=True,
                    )
                    inspection = inspect_staged(
                        Path(info["stage_dir"]), installed_app_dir()
                    )
                    detalhes = {
                        "from": VERSION,
                        "to": info["version"],
                        "package_sha256": info["package_sha256"],
                        "static_inspection_ok": inspection["ok"],
                        "executed_received_code": inspection["executed_code"],
                        "changed_files": sum(
                            1 for item in inspection["impact"]
                            if item.get("status") in {"NOVO", "ALTERADO", "EXCLUIDO"}
                        ),
                        "warnings": inspection["warnings"],
                        "problems": inspection["problems"],
                    }
                    if inspection["ok"]:
                        audit("UPDATE_PREPARED", "SYSTEM", None, detalhes)
                        flash(
                            f"Atualizacao {info['version']} preparada e inspecionada. "
                            "Ela ainda nao foi aplicada: revise o impacto e faca a aprovacao final.",
                            "success",
                        )
                    else:
                        audit("UPDATE_PREPARATION_REJECTED", "SYSTEM", None, detalhes)
                        flash(
                            f"A atualizacao {info['version']} foi rejeitada pela inspecao. "
                            "Consulte os problemas abaixo.",
                            "danger",
                        )
                except (UpdateError, zipfile.BadZipFile, OSError, ValueError) as exc:
                    audit("UPDATE_REJECTED", "SYSTEM", None, {
                        "error": str(exc), "file": filename,
                    })
                    flash(str(exc), "danger")
                return redirect(url_for("updates"))

            if action == "approve":
                versao_solicitada = request.form.get("stage_version", "").strip()
                meta = next(
                    (item for item in preparacoes()
                     if item.get("version") == versao_solicitada
                     and item.get("state") == "READY_FOR_APPROVAL"),
                    None,
                )
                if not meta:
                    flash("A preparacao escolhida nao esta disponivel para aprovacao.", "danger")
                    return redirect(url_for("updates"))
                usuario = current_user()
                autenticado = db.authenticate(
                    str(usuario["username"]), request.form.get("admin_password", "")
                )
                if not autenticado or int(autenticado["id"]) != int(usuario["id"]):
                    audit("UPDATE_APPROVAL_DENIED", "SYSTEM", None, {
                        "to": versao_solicitada, "reason": "reauthentication_failed",
                    })
                    flash("Senha do administrador incorreta. A atualizacao nao foi aplicada.", "danger")
                    return redirect(url_for("updates"))
                frase_esperada = f"APLICAR {versao_solicitada}"
                if request.form.get("confirmation", "").strip() != frase_esperada:
                    audit("UPDATE_APPROVAL_DENIED", "SYSTEM", None, {
                        "to": versao_solicitada, "reason": "confirmation_mismatch",
                    })
                    flash(f"Digite exatamente: {frase_esperada}", "danger")
                    return redirect(url_for("updates"))
                if request.form.get("approval_sha256", "").strip().lower() != meta.get("package_sha256"):
                    audit("UPDATE_APPROVAL_DENIED", "SYSTEM", None, {
                        "to": versao_solicitada, "reason": "hash_mismatch",
                    })
                    flash("O SHA-256 da aprovacao nao corresponde ao pacote preparado.", "danger")
                    return redirect(url_for("updates"))
                if request.form.get("review_ack") != "yes":
                    audit("UPDATE_APPROVAL_DENIED", "SYSTEM", None, {
                        "to": versao_solicitada, "reason": "review_not_acknowledged",
                    })
                    flash("Confirme que revisou o impacto e o plano de rollback.", "danger")
                    return redirect(url_for("updates"))
                # E A PERGUNTA QUE DECIDE SE O BALCAO CAI: «esta instalacao consegue
                # aplicar sozinha, e por que nao?». Era um teste de duas linhas — estar
                # no Windows e existir o install.json —, e ele respondia «sim» para uma
                # instancia que rodava de outra pasta e sob uma conta sem permissao
                # nessa pasta. Ver `update_manager.pode_aplicar_sozinho`.
                pode_aplicar, por_que_nao = pode_aplicar_sozinho(data_dir)
                if not pode_aplicar:
                    audit("UPDATE_APPROVAL_DENIED", "SYSTEM", None, {
                        "to": versao_solicitada, "reason": "automatic_apply_unavailable",
                        "detail": por_que_nao,
                    })
                    flash(
                        por_que_nao + " A preparacao permaneceu intacta e nao foi aprovada.",
                        "warning",
                    )
                    return redirect(url_for("updates"))
                try:
                    backup_target = backup_dir() / (
                        f"backup_pre_atualizacao_{VERSION}_para_{versao_solicitada}_"
                        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                    )
                    full_backup(backup_target)
                    aprovado = mark_approved(
                        Path(meta["stage_dir"]),
                        approved_by=str(usuario["username"]),
                        approved_at=datetime.now().isoformat(timespec="seconds"),
                        backup=str(backup_target),
                    )
                    audit("UPDATE_APPROVED", "SYSTEM", None, {
                        "from": VERSION, "to": versao_solicitada,
                        "package_sha256": aprovado["package_sha256"],
                        # reconferida contra o pacote na aprovacao (22/10/2026)
                        "assinatura": aprovado.get("assinatura"),
                        "backup": str(backup_target),
                    })
                    stage_path = Path(meta["stage_dir"])
                    porta = parse_int(db.get_setting("network_port", "8765")) or 8765
                    threading.Timer(
                        1.5,
                        lambda: launch_windows_updater(
                            stage_path, data_dir, os.getpid(), porta
                        ),
                    ).start()
                    flash(
                        f"Atualizacao {versao_solicitada} aprovada. O servidor sera "
                        "reiniciado; se a nova versao falhar, o rollback sera automatico.",
                        "success",
                    )
                except (UpdateError, OSError, ValueError) as exc:
                    audit("UPDATE_APPROVAL_FAILED", "SYSTEM", None, {
                        "to": versao_solicitada, "error": str(exc),
                    })
                    flash(str(exc), "danger")
                return redirect(url_for("updates"))

            abort(400)
        recent_packages = sorted(incoming.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True)[:10]
        # A TELA MOSTRA O MESMO VEREDITO DA ROTA, e pela mesma funcao: se a tela dissesse
        # «disponivel» e a rota recusasse, o oficial clicaria num botao que nao existe
        # para ele — e a frase de recusa chegaria depois de ele ter decidido.
        pode_aplicar, por_que_nao = pode_aplicar_sozinho(data_dir)
        return render_template(
            "updates.html", last_result=last_result,
            recent_packages=recent_packages, current_version=VERSION,
            staged_updates=preparacoes(),
            automatic_apply_available=pode_aplicar,
            automatic_apply_reason=por_que_nao,
            conferencia_instalacao=_ultima_conferencia_da_instalacao(updates_root),
        )

    def _ultima_conferencia_da_instalacao(updates_root):
        import retrato_da_instalacao as RET
        return RET.ultima_conferencia(updates_root)

    @app.route("/auditoria")
    @login_required
    @roles_required("ADMIN", "AUDITOR")
    def audit_logs():
        return render_template("audit.html", rows=db.list_logs(2000),
                               agente_servidor=IDR.AGENTE_SERVIDOR)

    @app.route("/configuracoes", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN")
    def settings():
        if request.method == "POST":
            values = {
                "unit_name": request.form.get("unit_name", "").strip() or "Serventia Extrajudicial",
                # O NOME DO REGISTRADOR (RI) NÃO TINHA TELA — achado em
                # 07/09/2026: `ri_registrador` ficou gravado como «MARIO
                # EXEMPLO DOS SANTOS» desde a instalação, e nenhuma tela
                # deixava corrigir. Vazio não se salva por cima do que já
                # está lá — apagaria o nome do registrador sem querer.
                **({"ri_registrador": request.form.get("ri_registrador", "").strip()}
                   if request.form.get("ri_registrador", "").strip() else {}),
                **({"ri_substituta": request.form.get("ri_substituta", "").strip()}
                   if request.form.get("ri_substituta", "").strip() else {}),
                **({"ri_cidade": request.form.get("ri_cidade", "").strip()}
                   if request.form.get("ri_cidade", "").strip() else {}),
                **({"ri_uf": request.form.get("ri_uf", "").strip().upper()}
                   if request.form.get("ri_uf", "").strip() else {}),
                "alert_days": str(max(1, parse_int(request.form.get("alert_days")) or 5)),
                "session_timeout_minutes": str(max(10, parse_int(request.form.get("session_timeout_minutes")) or 60)),
                # Campo que não veio não se grava por cima (o formulário antigo
                # aberto numa aba não zera o prazo absoluto).
                **({"session_absolute_hours": str(max(1, min(24 * 7, parse_int(
                    request.form.get("session_absolute_hours")) or 12)))}
                   if "session_absolute_hours" in request.form else {}),
                "require_backup_assignee": "1" if request.form.get("require_backup_assignee") else "0",
                "auto_backup": "1" if request.form.get("auto_backup") else "0",
                # `cra_auto_enviar_homolog` SAIU DAQUI EM 14/10/2026 — a caixa
                # saiu da tela com a ordem «agora é tudo produção», e gravar
                # o «0» de um campo que não vem mais seria mexer num valor que
                # ninguém pediu para mexer. Ele fica como estava, sem uso.
                # `cra_auto_enviar_producao` SAIU DAQUI EM 15/10/2026: a caixa
                # mora FORA deste formulário (na seção das Centrais), e por
                # isso nunca chegava — e cada «salvar» gravava «0» por cima,
                # desligando o envio que o oficial tentava ligar. Ela tem rota
                # própria agora: `configuracoes_cra_envio`.
                "backup_retention": str(max(3, parse_int(request.form.get("backup_retention")) or 30)),
                "archive_root": request.form.get("archive_root", "").strip(),
                # Uma por linha, sem linha vazia (LX12): ver `pastas_da_casa`.
                "pastas_de_importacao": "\n".join(
                    x.strip() for x in request.form.get("pastas_de_importacao", "").splitlines()
                    if x.strip()),
                "backup_dir": request.form.get("backup_dir", "").strip(),
                "malote_pasta": request.form.get("malote_pasta", "").strip(),
                "gratuidade_pasta": request.form.get("gratuidade_pasta", "").strip(),
                "network_host": request.form.get("network_host", "0.0.0.0").strip() or "0.0.0.0",
                "network_port": str(max(1024, min(65535, parse_int(request.form.get("network_port")) or 8765))),
                "discovery_enabled": "1" if request.form.get("discovery_enabled") else "0",
                "discovery_port": str(max(1024, min(65535, parse_int(request.form.get("discovery_port")) or 8766))),
                "password_min_length": str(max(4, min(64, parse_int(request.form.get("password_min_length")) or 6))),
                "password_require_upper": "1" if request.form.get("password_require_upper") else "0",
                "password_require_lower": "1" if request.form.get("password_require_lower") else "0",
                "password_require_digit": "1" if request.form.get("password_require_digit") else "0",
                # O INTERRUPTOR DO PROTESTO — ordem do oficial em
                # 01/09/2026. Caixa desmarcada desliga: e o lado seguro,
                # porque formulario que chega sem o campo nao pode LIGAR
                # um modulo que o oficial desligou.
                # O QUE O BOTAO DE IMPRIMIR ENTREGA — pedido do oficial em
                # 01/09/2026. Configuracao, e nao constante: a conversao para
                # PDF mediu de 1 s a 51 s nesta maquina, e se ela estiver
                # lenta no balcao quem volta para o `.odt` e ele.
                "impressao_formato_padrao": (
                    request.form.get("impressao_formato_padrao", "").strip().lower()
                    if request.form.get("impressao_formato_padrao", "").strip().lower()
                    in IMPPDF.FORMATOS else IMPPDF.FORMATO_PADRAO),
                # O ALCANCE DO PROTESTO — ordem do oficial em 01/09/2026:
                # aberto para o oficial, com um botao para liberar a todos.
                # Valor desconhecido nao entra: cai no de fabrica.
                "modulo_protesto_alcance": (
                    request.form.get("modulo_protesto_alcance", "").strip().upper()
                    if request.form.get("modulo_protesto_alcance", "").strip().upper()
                    in MODLIG.ALCANCES else MODLIG.ALCANCE_DE_FABRICA["PROTESTO"]),
                # OS DOIS INTERRUPTORES DAS ROTINAS QUE ESCREVEM SEM CLIQUE
                # (revisão de 22/10/2026, A13 e M19), na forma do envio do ONR:
                # caixa marcada = LIGADO; desmarcada desliga, que é o lado seguro.
                "censec_envio_automatico": "LIGADO" if request.form.get("censec_envio_automatico") else "DESLIGADO",
                "rtdpj_corrigir_automatico": "LIGADO" if request.form.get("rtdpj_corrigir_automatico") else "DESLIGADO",
                "categories": json.dumps([x.strip() for x in request.form.get("categories", "").splitlines() if x.strip()], ensure_ascii=False),
                "sources": json.dumps([x.strip() for x in request.form.get("sources", "").splitlines() if x.strip()], ensure_ascii=False),
                "sectors": json.dumps([x.strip() for x in request.form.get("sectors", "").splitlines() if x.strip()], ensure_ascii=False),
            }
            # CAMINHO DE REDE NÃO ENTRA NAS CONFIGURAÇÕES (revisão de segurança
            # de 22/10/2026, M3): `archive_root`, `backup_dir` e as pastas de
            # importação em `\\maquina\...` fariam o serviço, que roda como
            # SYSTEM, entregar a credencial da máquina à rede a cada leitura. A
            # régua é a de `pastas_da_casa._rede`, a mesma das importações.
            import pastas_da_casa as PDC
            de_rede = [c.strip() for c in (values["archive_root"], values["backup_dir"],
                                            values["malote_pasta"], values["gratuidade_pasta"],
                                            *values["pastas_de_importacao"].splitlines())
                       if c and c.strip() and PDC._rede(c.strip())]
            if de_rede:
                flash(f"Caminho de rede não é aceito nas configurações ({de_rede[0]}): "
                      "use uma pasta local do servidor. Nada foi salvo.", "danger")
                return redirect(url_for("settings"))
            db.set_settings(values)
            audit("SETTINGS_CHANGED", "SETTINGS", None, values)
            flash("Configurações salvas. Alterações de host/porta entram em vigor após reiniciar o servidor.", "success")
            return redirect(url_for("settings"))
        s = settings_dict()
        # O QUE ESTA INFORMADO, SEM O SEGREDO — `situacao` nunca devolve senha.
        return render_template("settings.html", s=s,
                               backup_cifra=BKP.situacao_da_cifra(data_dir),
                               centrais=CENTCRED.situacao(), categories="\n".join(json_list(s.get("categories","[]"), [])), sources="\n".join(json_list(s.get("sources","[]"), [])), sectors="\n".join(json_list(s.get("sectors","[]"), [])), data_dir=data_dir)

    @app.route("/configuracoes/cra-envio", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def configuracoes_cra_envio():
        """Liga ou desliga o envio automático à CRA. ESCREVE só esta chave.

        Relato do oficial, 15/10/2026: «não consegui salvar o check de mandar
        automaticamente para a CRA». A caixa estava fora do formulário da tela;
        agora tem formulário e botão próprios, e só mexe nela.
        """
        valor = "1" if request.form.get("cra_auto_enviar_producao") else "0"
        db.set_settings({"cra_auto_enviar_producao": valor})
        audit("SETTINGS_CHANGED", "SETTINGS", None,
              {"cra_auto_enviar_producao": valor})
        flash("Envio automático à CRA " + ("LIGADO: a confirmação e o andamento "
              "sobem sozinhos logo depois de receber a remessa." if valor == "1"
              else "desligado: confirmação e andamento sobem pelo botão "
              "«Enviar à CRA»."), "success")
        return redirect(url_for("settings"))

    @app.route("/configuracoes/central", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def configuracoes_central():
        """Guarda a credencial de uma Central. ESCREVE EM DISCO, nao no banco.

        **ROTA PROPRIA, E NAO UM CAMPO DO FORMULARIO DE CONFIGURACOES.** Aquele
        chama `db.set_settings`, que grava no banco — e o banco viaja no
        backup, que ja saiu da serventia. Aqui a senha vai para
        `%PROGRAMDATA%`, ao lado da do selador.

        **E SO O ADMIN**, como a chave da API do Claude: quem configura o que
        fala com a Central nao pode ser quem a lista alcanca.
        """
        central = (request.form.get("central") or "").strip().upper()
        ambiente = (request.form.get("ambiente") or "").strip().upper()
        acao = (request.form.get("acao") or "gravar").strip().lower()
        try:
            # AS TRÊS DO PROTESTO SÓ TÊM PRODUÇÃO NA TELA (14/10/2026): um
            # formulário antigo, ou o endereço digitado à mão, não grava nem
            # retira a gaveta de homologação — ela fica como está.
            if central in CENTCRED.CENTRAIS_SO_EM_PRODUCAO and ambiente:
                CENTCRED.ambiente_de_uso(central, ambiente)
            if acao == "apagar":
                tirou = CENTCRED.apagar(central, ambiente)
                flash("Credencial retirada." if tirou
                      else "Não havia credencial gravada para esse ambiente.",
                      "success" if tirou else "warning")
            elif CENTCRED.FORMA_DA_CENTRAL.get(central) == CENTCRED.TOKEN:
                # A TERCEIRA CENTRAL GUARDA UM TOKEN, e nao um par — o contrato
                # da ONRTDPJ declara `apiKey` no cabecalho `Authorization`, e o
                # token e gerado pelo proprio cartorio la dentro. Um campo de
                # usuario aqui faria alguem preenche-lo com o CNS so para a
                # tela deixar salvar.
                CENTCRED.gravar_token(central, ambiente=ambiente,
                                      token=request.form.get("token") or "")
                flash(f"Token da {CENTCRED.NOME_DA_CENTRAL[central]} guardado "
                      f"fora do banco.", "success")
            else:
                CENTCRED.gravar(central, ambiente=ambiente,
                                usuario=request.form.get("usuario") or "",
                                senha=request.form.get("senha") or "")
                # **TROCAR A CREDENCIAL TEM DE JOGAR FORA O TOKEN GUARDADO.**
                # O ONR troca o par por um token com validade, e o sistema o
                # guarda na memoria ate perto de vencer; sem esta linha, quem
                # corrigisse o `client_secret` continuaria falando com o ONR
                # pelo token velho ate ele expirar — e concluiria que a
                # correcao nao pegou.
                if central == CENTCRED.ONR:
                    import onr_api
                    onr_api.esquecer_o_token(ambiente)
                # **O CNIB CAI NA MESMA ARMADILHA, e caiu sozinho ate
                # 19/09/2026**: ele tambem troca o par por um token de uma
                # hora, guardado na memoria do processo. Sem esta linha, quem
                # corrigisse o `client_secret` continuaria falando pelo token
                # velho — e concluiria que a correcao nao pegou. O modulo ja
                # trazia o `esquecer_o_token` pronto; faltava chamar.
                if central == CENTCRED.CNIB:
                    import cnib_api
                    cnib_api.esquecer_o_token(ambiente)
                flash(f"Credencial da {CENTCRED.NOME_DA_CENTRAL[central]} "
                      f"({ambiente.lower()}) guardada fora do banco.", "success")
        except CENTCRED.CredencialError as erro:
            flash(str(erro), "danger")
        except KeyError:
            flash("Central desconhecida.", "danger")
        # **A SENHA NAO ENTRA NA AUDITORIA.** O que se registra e QUE se mexeu,
        # e nunca o que se digitou — a auditoria mora no banco.
        audit("CENTRAL_CREDENCIAL", "CENTRAIS", None,
              {"central": central, "ambiente": ambiente, "acao": acao})
        return redirect(url_for("settings"))

    @app.route("/configuracoes/backup-protecao", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def configuracoes_backup_protecao():
        """A cifra do pacote e o acervo no completo (LX14; A7 do LS03). ESCREVE.

        ROTA PRÓPRIA, como a das Centrais: a senha da cifra vai ao cofre
        (`backup.cred`), e não a `settings`, que viaja no backup — a senha iria
        dentro do pacote que ela fecha. Só o «acervo fora do completo», que
        não é segredo, vai a `settings`.

        A SENHA NÃO ENTRA NA AUDITORIA nem na mensagem: registra-se QUE a cifra
        foi ligada ou desligada.
        """
        acao = (request.form.get("acao") or "").strip().lower()
        if acao == "senha":
            senha = request.form.get("senha") or ""
            if senha != (request.form.get("confirmacao") or ""):
                flash("A senha e a confirmação não são iguais; nada mudou.", "danger")
            else:
                try:
                    BKP.guardar_senha_da_cifra(data_dir, senha)
                except BKP.BackupInvalido as erro:
                    flash(f"Não liguei a cifra: {erro}.", "danger")
                else:
                    audit("BACKUP_CIFRA", "BACKUP", None, {"cifra": "ligada"})
                    flash("Cifra do backup LIGADA: os próximos pacotes saem "
                          "cifrados. Anote a senha FORA do servidor — sem ela, "
                          "um pacote cifrado não abre, nem para quem fez o "
                          "sistema.", "success")
        elif acao == "desligar":
            BKP.apagar_senha_da_cifra(data_dir)
            audit("BACKUP_CIFRA", "BACKUP", None, {"cifra": "desligada"})
            flash("Cifra do backup desligada: os próximos pacotes saem sem "
                  "cifra. Os que já saíram cifrados continuam pedindo a senha "
                  "de quando foram feitos.", "warning")
        elif acao == "acervo":
            valor = "1" if request.form.get("backup_completo_sem_acervo") else "0"
            db.set_settings({"backup_completo_sem_acervo": valor})
            audit("SETTINGS_CHANGED", "SETTINGS", None,
                  {"backup_completo_sem_acervo": valor})
            flash("O backup completo " + ("deixa de levar o acervo do E-Ofício "
                  "— guarde uma cópia dele à parte." if valor == "1"
                  else "volta a levar o acervo do E-Ofício."), "success")
        else:
            abort(400)
        return redirect(url_for("settings"))

    @app.route("/backup", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def backup():
        target = backup_dir() / f"backup_manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        full_backup(target)
        audit("MANUAL_BACKUP", "BACKUP", None, {"path": str(target)})
        return send_file(target, as_attachment=True, download_name=target.name)

    @app.route("/integridade")
    @login_required
    @roles_required("ADMIN", "AUDITOR")
    def integrity():
        with db.connect() as con:
            rows = banco(con).ler("SELECT * FROM attachments ORDER BY id DESC")
        results = []
        for r in rows:
            p = Path(r["stored_path"])
            actual = hash_file(p) if p.exists() else None
            results.append((r, actual, actual == r["sha256"] if actual else False))
        audit("INTEGRITY_CHECK", "SYSTEM", None, {"files": len(results), "ok": sum(1 for _,_,ok in results if ok)})
        return render_template("integrity.html", results=results)

    def _sigilo_do_coaf(row) -> None:
        """O recibo da comunicação ao COAF só abre para o ADMIN (08/10/2026).

        CNN, art. 154, e TJMA, art. 954, parágrafo único: sigilo das
        comunicações, inclusive dentro da casa. As duas rotas abaixo servem
        qualquer anexo a quem tem login — sem esta guarda, o número do anexo
        trocado na barra mostraria a comunicação ao balcão. 404, e não 403:
        quem não pode ver também não fica sabendo que o arquivo existe.
        """
        if row["entity_type"] == "PLD_CASO" and usuario_papel() != "ADMIN":
            abort(404)

    # DE QUE TELA É CADA ANEXO (LX12, 19/10/2026; LS02 «/arquivo/<id> serve
    # qualquer anexo a qualquer logado»). O anexo abre para quem abre a tela
    # que o oferece — a mesma guarda de papel e o mesmo alcance de módulo
    # (Protesto só do oficial, por exemplo). Sem isto, o número trocado na
    # barra trazia o anexo do módulo que o menu e a rota escondem.
    #
    # A REGRA SE LÊ DA TELA, e não se copia: os papéis vêm do `roles_required`
    # dela (`papeis_exigidos`) e o módulo de `modulos.modulo_da_tela` — no dia
    # em que a tela mudar, o anexo muda junto. Mais de uma tela = basta uma.
    # Tipo que não está aqui só abre para o ADMIN: anexo de tela nova não sai
    # aberto a todos por esquecimento (o teste `test_todo_tipo_de_anexo_...`
    # cobra a lista contra quem grava anexo).
    TELA_DO_ANEXO: dict[str, tuple[str, ...]] = {
        "EXPEDIENTE": ("expediente_detail",),
        "TASK": ("task_detail",),
        "NT_ATO": ("notas_ato",),
        "NT_COMUNICACAO_ORIGEM": ("notas_ato",),
        "PROTOCOLO": ("caixa_protocolo",),
        "RI_PROTOCOLO": ("ri_protocolo_ver",),
        "RG_ATO": ("rcpj_rtd_registro",),
        "RG_REGISTRO": ("rcpj_rtd_registro",),
        "RG_TITULO": ("rcpj_rtd_titulo",),
        "rc_termo": ("rcpn_assento",),
        "rc_assento": ("rcpn_assento",),
        "RC_LEITURA": ("rcpn_leitura_ficha",),
        "HC_HABILITACAO": ("rcpn_habilitacao",),
        "USUCAPIAO_PECA": ("usucapiao_processo",),
        "RT_PECA": ("ri_retificacao",),
        "PT_AVISO": ("protesto_avisos",),
        "PT_TITULO": ("protesto_imagem",),
        "SELO_GRATUIDADE": ("gratuidade_comprovantes", "selo_gratuidades_portal"),
        "SELO_GRATUIDADE_CERTIDAO": ("selo_gratuidades_portal",),
        "ONR_CERTIDAO": ("onr_certidao_ficha",),
        "PLD_CASO": ("pld_caso",),
    }
    app.extensions["tela_do_anexo"] = TELA_DO_ANEXO

    def _abre_pela_tela(endpoint: str, papel, funcao=None) -> bool:
        view = app.view_functions.get(endpoint)
        if view is None:
            return False
        papeis = getattr(view, "papeis_exigidos", None)
        if papeis is not None and papel not in papeis:
            return False
        # A FUNÇÃO TAMBÉM CONTA AQUI (LH06, 21/10/2026): a auxiliar que o
        # `before_request` tira do Protesto não pode baixar pelo endereço do
        # anexo o comprovante do aviso nem a imagem do título — seria a porta
        # dos fundos da mesma tela.
        return MODLIG.pode_entrar(db.get_setting, MOD.modulo_da_tela(endpoint),
                                  papel, funcao)

    def _conferir_o_dono(row) -> None:
        """404 se quem pede não abre a tela que oferece este anexo. Ver
        `TELA_DO_ANEXO`. 404, e não 403, pela razão do `_sigilo_do_coaf`."""
        _sigilo_do_coaf(row)
        papel = usuario_papel()
        telas = TELA_DO_ANEXO.get(row["entity_type"])
        if telas is None:
            if papel != "ADMIN":
                abort(404)
            return
        funcao = funcao_de_quem_esta_logado()
        if not any(_abre_pela_tela(t, papel, funcao) for t in telas):
            abort(404)

    @app.route("/arquivo/<int:attachment_id>")
    @login_required
    def attachment_download(attachment_id):
        row = db.get_attachment(attachment_id)
        if not row: abort(404)
        _conferir_o_dono(row)
        path = Path(row["stored_path"])
        if not path.exists(): abort(404)
        audit("ATTACHMENT_DOWNLOADED", row["entity_type"], row["entity_id"], {"attachment_id": attachment_id})
        return send_file(path, as_attachment=True, download_name=row["original_name"])

    @app.route("/arquivo/<int:attachment_id>/ver")
    @login_required
    def attachment_view(attachment_id):
        """O MESMO arquivo, aberto NA TELA em vez de baixado.

        «esteja disponível para analisar no visualizador de pdf direto no
        sistema, disponível para baixar» — o oficial, 03/09/2026. **São as duas
        coisas, e por isso são duas rotas**: `/arquivo/<id>` baixa e
        `/arquivo/<id>/ver` mostra. Um parâmetro na mesma rota faria o link de
        baixar e o de ver serem o mesmo endereço com uma letra de diferença, e
        quem copiasse um levaria o outro.

        **E ISTO CONSERTA UM DEFEITO ANTIGO, DE OUTRO MÓDULO.** O relato #25
        pedia visualizar os documentos da prenotação do RI; `ri_documentos.
        e_imagem` foi escrita para decidir isso e a tela do RI já põe
        `target="_blank"` no link — **e a única rota que servia arquivo baixava
        sempre**. A metade que decide estava pronta e a que serve nunca soube
        dela.

        **O QUE ABRE NA TELA É LISTA CURTA, E A RAZÃO É DE SEGURANÇA**: arquivo
        servido em linha roda na origem do sistema, e um `.html` ou um `.svg`
        de terceiro traria o script dele para dentro da sessão de quem está no
        balcão. Quem decide é `arquivo_visivel`; o que não estiver na lista
        **volta para a rota de baixar**, e não dá erro — o arquivo continua
        chegando a quem clicou.
        """
        row = db.get_attachment(attachment_id)
        if not row: abort(404)
        _conferir_o_dono(row)
        path = Path(row["stored_path"])
        if not path.exists(): abort(404)
        if not ARQVIS.abre_na_tela(row["original_name"]):
            # Nao e recusa: e o mesmo arquivo pelo caminho que funciona para
            # ele. Uma tela em branco seria pior que o botao de baixar.
            return redirect(url_for("attachment_download",
                                    attachment_id=attachment_id))
        audit("ATTACHMENT_VIEWED", row["entity_type"], row["entity_id"], {"attachment_id": attachment_id})
        resposta = send_file(path, as_attachment=False,
                             download_name=row["original_name"],
                             mimetype=ARQVIS.tipo_do_arquivo(row["original_name"]))
        for chave, valor in ARQVIS.cabecalhos_para_mostrar().items():
            resposta.headers[chave] = valor
        return resposta

    ri_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    # AS NOTAS DE REVISAO vem DEPOIS das telas do RI, porque a tela delas
    # aponta para `ri_ficha` e `ri_matriculas`, que nascem ali.
    import ri_revisao_web
    ri_revisao_web.registrar_rotas(app, db, login_required, roles_required,
                                   audit, fmt_date)

    # O ATUALIZADOR DO CNIB tambem vem depois do RI, pela mesma razao: a tela
    # dele aponta para `ri_cnib_pendentes`. Ele registra em `app.extensions` a
    # rotina diaria, que o `before_request` chama — e que so sai para a rede
    # quando ha credencial, CPF e nao houve leitura hoje.
    import cnib_web
    cnib_web.registrar_rotas(app, db, login_required, roles_required,
                             audit, fmt_date)

    import caixa_web
    caixa_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    # A NFS-e DOS EMOLUMENTOS (LG01) — a fila do caixa, o recibo diante da nota
    # e a configuração do Gestor. Pelo emissor nacional; desligada por padrão.
    import nfse_web
    nfse_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    # AS DESPESAS (24/10/2026) — cadastrar, o oficial autoriza, o Banco Inter
    # paga, o extrato confere e o Livro Diário recebe. Pagamento desligado por padrão.
    import despesas_web
    despesas_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    import notas_web
    notas_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    # O AGENTE DE MINUTAS DO RI E DAS NOTAS (23/10/2026) — o quadro na ficha da
    # matrícula e no ato em lavratura; prepara a minuta, não lavra.
    import minuta_ia_web
    minuta_ia_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    # O CADASTRO NO CCN (13/10/2026) — o lote e a ponte com a extensão.
    import ccn_web
    ccn_web.registrar_rotas(app, db, login_required, roles_required, audit)

    import selador_web
    selador_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    import atribuicoes_web
    atribuicoes_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    # O SELO DO ATO DO LIVRO 3 vem DEPOIS das telas do Registro Auxiliar,
    # porque a rota dele volta para `livro3_registro`, que nasce ali — e ele
    # deixa em `app.extensions` a funcao que a rota de averbar chama para
    # selar sozinha, na forma que o Livro 2 ja usa.
    import ra_selo_web
    ra_selo_web.registrar_rotas(app, db, login_required, roles_required,
                                audit, fmt_date)

    # A MINUTA DO LIVRO 3 — item 1 da fila de 20/09/2026. Vem depois das telas
    # do Registro Auxiliar pelo mesmo motivo: as rotas dela voltam para
    # `livro3_registro`.
    import ra_minuta_web
    ra_minuta_web.registrar_rotas(app, db, login_required, roles_required,
                                  audit, fmt_date)

    # AS PARTES DO REGISTRO DO LIVRO 3 — 21/09/2026. A tabela existia desde
    # que o livro nasceu e NENHUMA TELA escrevia nela; sem elas o selo nao
    # sai, e o aparelho recusa com «Os nomes das partes devem ser informados».
    import ra_parte_web
    ra_parte_web.registrar_rotas(app, db, login_required, roles_required,
                                 audit, fmt_date)

    # AS NOTAS DE REVISAO e AS CORRECOES do Livro 3 — itens 2, 4, 5 e 7 da
    # fila, por ordem dele em 21/09/2026: «termine o desenvolvimento do livro
    # 3, falta varias coisas que temos no livro 2».
    import ra_revisao_web
    ra_revisao_web.registrar_rotas(app, db, login_required, roles_required,
                                   audit, fmt_date)
    import ra_correcoes_web
    ra_correcoes_web.registrar_rotas(app, db, login_required, roles_required,
                                     audit, fmt_date)

    # A DIGITALIZACAO E A CONFERENCIA do Livro 3 — ordem dele em 21/09/2026:
    # «digitalizacao de imagens deve ter igual ao livro 2».
    import ra_digitalizacao_web
    ra_digitalizacao_web.registrar_rotas(app, db, login_required,
                                         roles_required, audit, fmt_date)

    # A COPIA EM TIFF PARA O ONR NA HORA DO ENVIO — 10/10/2026: «nao existe
    # outra forma que o sistema processe e crie a copia em tiff?». A situacao
    # na ficha da matricula e o botao «converter agora».
    import ri_onr_imagem_web
    ri_onr_imagem_web.registrar_rotas(app, db, login_required, roles_required,
                                      audit, fmt_date)

    import livro3_modelos_web
    livro3_modelos_web.registrar_rotas(app, db, login_required,
                                       roles_required, audit, fmt_date)
    # AS TELAS DO TITULO DO RCPJ/RTD vem DEPOIS das das atribuicoes, porque a
    # ficha do titulo aponta para `rcpj_rtd_registro`, que nasce ali.
    import rg_web
    rg_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)
    # OS ATOS DO LG04 (19/10/2026): a notificação extrajudicial e a autenticação
    # de livros do RCPJ/RTD voltam para `rcpj_rtd_registro`, que nasce acima;
    # a pública forma e a comunicação ao DETRAN são do balcão das Notas.
    import nt_publica_forma
    import nt_veiculo_detran
    import rg_livro_contabil
    import rg_notificacao
    for _modulo_lg04 in (rg_notificacao, rg_livro_contabil, nt_publica_forma,
                         nt_veiculo_detran):
        _modulo_lg04.registrar_rotas(app, db, login_required, roles_required,
                                     audit)
    # AS TELAS DA CENPROT vem DEPOIS das do Protesto, porque a fila delas
    # aponta para `pt_titulos` e os links levam a `protesto_titulo`.
    cenprot_web.registrar_rotas(app, db, login_required, roles_required, audit)
    resolve_web.registrar_rotas(app, db, login_required, roles_required, audit)
    # O AR DIGITAL, O BOLETO E O PAINEL DO DEVEDOR (LG06) vem ao lado da
    # Resolve: sao os outros caminhos da intimacao e do pagamento, e as telas
    # deles apontam para `protesto_titulo` e `protesto_avisos`.
    protesto_cobranca_web.registrar_rotas(app, db, login_required,
                                          roles_required, audit)
    # A TELA DA CRA vem ao lado da da CENPROT: sao as duas Centrais, e a
    # credencial das duas mora no mesmo lugar, fora do banco.
    cra21_web.registrar_rotas(app, db, login_required, roles_required, audit)
    # O REPASSE AO APRESENTANTE E A CERTIDÃO EM RELAÇÃO (LG05) vêm depois das
    # do Protesto: as telas apontam para `protesto_titulo`, que nasce ali.
    import protesto_repasse_web
    protesto_repasse_web.registrar_rotas(app, db, login_required,
                                         roles_required, audit)
    # O PAINEL DAS CENTRAIS — fila generica, ultimas falhas e o cofre (so
    # «informada/nao informada»). Marco (a) da base comum, 05/10/2026. Vem
    # depois da CRA e da CENPROT porque e o painel comum delas; so le, e o
    # unico botao (Reprocessar) e local: devolve a fila, nao envia nada.
    import centrais_web
    centrais_web.registrar_rotas(app, db, login_required, roles_required, audit)
    # FILA DO WHATSAPP: mesmo login, mesmo Flask. Webhook sem CSRF.
    wa_web.registrar_rotas(app, db, login_required, roles_required, audit)
    # ROBOS: CRUD + config API + testar rascunho (humano no loop).
    robo_web.registrar_rotas(app, db, login_required, roles_required, audit)

    # As telas do NUCLEO — livros, termos, inutilizacoes e encerramentos.
    # Modulo proprio porque o livro serve as SEIS atribuicoes, e nao so as
    # quatro novas.
    import nucleo_web
    nucleo_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    import retificacao_web
    retificacao_web.registrar_rotas(app, db, login_required,
                                    roles_required, audit, fmt_date)

    import usucapiao_web
    usucapiao_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    # A LISTA DE ATENCAO PARA FRAUDES serve as SEIS atribuicoes — as
    # comunicacoes chegam pelo malote e o nome pode aparecer em qualquer uma.
    # Por isso modulo proprio, como o nucleo, e nao dentro de uma delas.
    import fraude_web
    fraude_web.registrar_rotas(app, db, login_required, roles_required, audit)

    # O PAPEL DE SEGURANCA e do Registro Civil, e as rotas dele se chamam
    # `rcpn_papel_*` para cairem no grupo certo do menu — o modulo sai do
    # prefixo, e nao de uma lista.
    import modelos_web
    modelos_web.registrar_rotas(app, db, login_required, roles_required,
                                audit, fmt_date)

    import papel_web
    papel_web.registrar_rotas(app, db, login_required, roles_required, audit)

    # A HABILITACAO DE CASAMENTO — o processo que antecede o assento do Livro B.
    # As rotas se chamam `rcpn_habilitac*` pelo mesmo motivo do papel: o modulo
    # do menu sai do PREFIXO da rota, e nao de uma lista escrita a mao.
    import habilitacao_web
    habilitacao_web.registrar_rotas(app, db, login_required, roles_required,
                                    audit, fmt_date)

    # HOTFIX-2026-10-09-04 - modelos de averbacao RCPN com formulario
    # proprio (so montam texto; o lancamento e o selo seguem na tela padrao).
    import rc_averbacao_modelos_web
    rc_averbacao_modelos_web.registrar_rotas(app, db, login_required,
                                             roles_required, audit, fmt_date)

    # O e-PROCLAMAS VEM LOGO DEPOIS DA HABILITACAO, e a ordem nao e por acaso:
    # a fila dele sai de `hc_habilitacoes` com edital publicado.
    import proclamas_web
    proclamas_web.registrar_rotas(app, db, login_required, roles_required,
                                  audit, fmt_date)

    # O ONR — o indicador real, o edital do usucapiao e a fila. Depois de
    # `ri_web` e de `usucapiao_web`, que sao as telas para onde estas apontam.
    import ri_onr_web
    ri_onr_web.registrar_rotas(app, db, login_required, roles_required, audit,
                               fmt_date)

    # A BASE DO MAPA DO ONR — o CSV que o QGIS junta ao polígono (LF02).
    import ri_mapa_onr
    ri_mapa_onr.registrar_rotas(app, db, login_required, roles_required, audit)

    # A APOSTILA DE HAIA (LG03) — pedido, documento, emissão no CNJ, selo,
    # cobrança e controle. Chega DESLIGADA (`modulos_ligados`, NINGUEM).
    import apostila_web
    apostila_web.registrar_rotas(app, db, login_required, roles_required, audit)

    # OS LIVROS OBRIGATÓRIOS (LG08) — o catálogo do Código de Normas do MA e
    # os três livros administrativos de toda serventia (art. 188): Visitas e
    # Correições, Diário Auxiliar e Controle de Depósito Prévio.
    import livros_administrativos_web
    livros_administrativos_web.registrar_rotas(app, db, login_required, roles_required, audit)

    # AS CERTIDÕES PEDIDAS PELO ONR (Ofício Eletrônico, Certidoes.asmx) —
    # buscar, guardar o arquivo assinado, enviar, finalizar ou devolver.
    # Ordem do oficial em 11/10/2026: «faça a da onr certidões».
    import onr_certidoes_web
    onr_certidoes_web.registrar_rotas(app, db, login_required, roles_required, audit,
                                      fmt_date)
    # A APROVAÇÃO DO QUE O ROBÔ PREPAROU (25/10/2026): o clique «Aprovar» é a
    # emissão, pela rota da casa (`onr_certidoes_auto_web`).
    import onr_certidoes_auto_web
    onr_certidoes_auto_web.registrar_rotas(app, db, login_required, roles_required, audit)

    # A CONFERENCIA DO ENDERECO QUE VAI AO ONR — o que o teor da ficha diz,
    # ao lado do que a ficha tem, com a frase de onde cada campo saiu.
    # **Vem logo depois de `ri_onr_web`** porque e o passo anterior dele:
    # aqui se confere e grava na ficha, la se publica o indicador. Separados
    # de proposito — conferir e do balcao, publicar e do oficial.
    import onr_endereco_web
    onr_endereco_web.registrar_rotas(app, db, login_required, roles_required,
                                     audit, fmt_date)

    # A CENTRAL DE CERTIDOES DO ON-RCPN — a fila dos sete modulos e a
    # certidao eletronica. Depois de `atribuicoes_web`, que e quem tem a
    # ficha do assento para onde estas telas apontam.
    import rc_pedidos_web
    rc_pedidos_web.registrar_rotas(app, db, login_required,
                                   roles_required, audit, fmt_date)

    # AS TELAS DOS MODELOS DO ESCREVENTE — o modulo Modelos do
    # E-Oficio. As rotas se chamam `rcpn_*` porque e o nome da rota que
    # poe a tela no grupo do menu, e este assunto e do Registro Civil.
    import rc_modelos_livres_web
    rc_modelos_livres_web.registrar_rotas(app, db, login_required,
                                          roles_required, audit, fmt_date)

    # OS SEIS SUBMODULOS DE MODELOS — um por atribuicao, com as partes
    # editaveis. Vem DEPOIS de `modelos_web`, que e a tela geral: as duas
    # gravam no mesmo lugar, e a geral e quem responde quando nao se sabe de
    # qual atribuicao e o papel.
    import modelos_elementos_web
    modelos_elementos_web.registrar_rotas(app, db, login_required,
                                          roles_required, audit, fmt_date)

    # MOTOR DE FIDELIDADE — APIs /modelos/api/* (Robô Modelos — Fidelidade).
    # try/except: falha no motor não impede o app de subir.
    try:
        import modelos_motor_web
        modelos_motor_web.registrar_rotas(app, db, login_required,
                                          roles_required, audit)
    except Exception as erro_motor_modelos:
        import logging
        logging.getLogger(__name__).exception(
            'Falha ao registrar modelos_motor_web: %s', erro_motor_modelos)

    # EDITOR UNIFICADO DE MODELOS (Marco 1) - RCPN termos + moldes.
    # Rotas /modelos/api/* sao do Robo Fidelidade - registradas acima.
    try:
        import modelos_editor_web
        modelos_editor_web.registrar_rotas(app, db, login_required,
                                           roles_required, audit, fmt_date)
    except Exception as erro_editor_modelos:
        import logging
        logging.getLogger(__name__).exception(
            'Falha ao registrar modelos_editor_web: %s', erro_editor_modelos)


    import ajuda_problemas
    import ajuda_web
    ajuda_web.registrar_rotas(app, db, login_required, roles_required, audit,
                              fmt_date)

    import dev_projetos_web
    from nu_avisos_gestao import banco_e_sandbox

    dev_projetos_web.register_dev_projetos_routes(
        app,
        login_required=login_required,
        roles_required=roles_required,
        get_db=db.connect,
        render_template=render_template,
        redirect=redirect,
        url_for=url_for,
        request=request,
        flash=flash,
        abort=abort,
        is_sandbox=banco_e_sandbox,
        current_user_login=lambda: (
            getattr(g.user, "login", None) if g.get("user") else None
        )
        or ((current_user() or {}).get("username")),
    )

    import produtividade_web

    produtividade_web.register_produtividade_routes(
        app,
        login_required=login_required,
        roles_required=roles_required,
        get_db=db.connect,
        render_template=render_template,
        redirect=redirect,
        url_for=url_for,
        request=request,
        flash=flash,
        current_user_fn=current_user,
    )

    # OS ENVIOS ÀS CENTRAIS (06/10/2026): a cobrança da conferência diária só
    # some com o envio registrado e o protocolo — e quem registra é quem mandou.
    import gestor_web
    gestor_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    # A VERIFICAÇÃO EM DUAS ETAPAS (LG02, 19/10/2026): o segundo passo do
    # login, a tela da conta e a do Gestor. Publica o desvio que o `/login`
    # consulta depois da senha.
    import dois_fatores_web
    dois_fatores_web.registrar_rotas(app, db, login_required, roles_required, audit)

    # O CAIXA QUE NÃO FECHA (06/10/2026): aviso vermelho depois do expediente,
    # e bloqueio das outras telas quando o caixa de ontem continua aberto.
    import caixa_aviso_web
    caixa_aviso_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    # O COMPROVANTE DA GRATUIDADE (11/10/2026): aviso insistente ao USUÁRIO que
    # obteve selo isento, em toda tela, até guardar o comprovante. Não trava o ato.
    import gratuidade_comprovante_web
    gratuidade_comprovante_web.registrar_rotas(app, db, login_required, roles_required, audit,
                                               fmt_date)

    # O QUE SE DEVE AO PORTAL DO SELO (LG07, 19/10/2026): o pedido de
    # cancelamento ao TJMA, com o aviso do cancelado não comunicado, e o pacote
    # do ressarcimento — por selo gratuito, comprovante + certidão do ato.
    import selo_portal_web
    selo_portal_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    # OS RELATOS DO DIA (12/10/2026): o despacho do gestor, a cobrança e o
    # boletim do RCPN numa janela do painel, e não em tarefa que se acumula.
    import relatos_diarios_web
    relatos_diarios_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    # A PASTA DO PROCESSO e o rascunho que vira processo (12/10/2026) — fase 1
    # do módulo único de Processos.
    import processo_pasta_web
    processo_pasta_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    # PROCESSOS — a lista única (fase 3, 12/10/2026): tarefas e expedientes
    # num módulo só; o expediente é a entrada do processo.
    import processos_web
    processos_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    # A REVISÃO ANTES DA LAVRATURA (06/10/2026): o Opus lê o ato do RI e das
    # Notas com o contexto, entre o preenchimento e a lavratura.
    import revisao_previa_web
    revisao_previa_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)
    # A CERTIDÃO DE ÔNUS POSITIVA OU NEGATIVA, com a sugestão da IA — 13/10/2026.
    import ri_onus_ia_web
    ri_onus_ia_web.registrar_rotas(app, db, login_required, roles_required, audit)
    # A IA CONFERE A TRANSCRIÇÃO CONTRA A PÁGINA ESCANEADA (LH11, 21/10/2026):
    # o botão no quadro da certidão de inteiro teor e o lote dos livros antigos.
    import revisao_transcricao_web
    revisao_transcricao_web.registrar_rotas(app, db, login_required, roles_required, audit)

    # O PLD/COAF (08/10/2026): a seleção do que se comunica ao COAF, a análise
    # documentada, o texto da comunicação e o registro do envio. Só do ADMIN.
    import pld_web
    pld_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    # A FICHA REDIGITALIZADA EM 7 DIAS DEPOIS DO ATO (06/10/2026): o aviso
    # vermelho; a cobrança e a notificação do administrador são do gestor.
    import ri_digi_prazo_web
    ri_digi_prazo_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    # O TERMO ASSINADO DO RCPN, DIGITALIZADO (problema #121, 07/10/2026): o
    # molde do RI por assento — enviar, ver, a lista dos registros que esperam
    # o termo e o aviso vermelho depois de 7 dias. Não trava: avisa.
    import rc_digitalizacao_web
    rc_digitalizacao_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    # A LEITURA DOS DOCUMENTOS DO REGISTRO (12/10/2026): a DNV ou a DO e os
    # documentos de identidade lidos pela IA viram rascunho do assento novo —
    # «vamos construir», depois do teste Sonnet × Opus numa DNV real.
    import rc_leitura_web
    rc_leitura_web.registrar_rotas(app, db, login_required, roles_required, audit, fmt_date)

    import nu_avisos_web
    nu_avisos_web.registrar_rotas(
        app, db, login_required, roles_required, audit, fmt_date
    )

    # O AGENTE DO SISTEMA — o console de quem responde pela serventia.
    #
    # VEM AO LADO DA AJUDA porque e a mesma familia: ele le o codigo desta
    # casa, o banco, a documentacao e os problemas anotados. E vem DEPOIS
    # dela porque `agente_ferramentas` usa `ajuda_codigo`, `ajuda_problemas`
    # e `ajuda_projeto` — a mesma ordem de quem le antes de quem mexe.
    #
    # A DIFERENCA DE FUNDO e de consequencia: a ajuda responde duvida de
    # balcao; isto aqui tem permissao de MUDAR o sistema. Por isso e so do
    # ADMIN, e por isso nasce com a escrita desligada.
    import agente_web
    agente_web.registrar_rotas(app, db, login_required, roles_required, audit,
                               fmt_date)

    # A AUTOMAÇÃO (24/10/2026) — a central única das rotinas: o cadastro, o
    # relatório de cada rodada, a configuração dos avisos e o cofre. A tela
    # não roda nada; quem roda é o despachante, fora do servidor.
    import automacao_web
    automacao_web.registrar_rotas(app, db, login_required, roles_required, audit,
                                  fmt_date)

    import acervo_correcao_web
    acervo_correcao_web.registrar_rotas(app, db, login_required,
                                        roles_required, audit, fmt_date)

    @app.errorhandler(403)
    def forbidden(_):
        return render_template("error.html", code=403, message="Você não tem permissão para acessar esta área."), 403

    @app.errorhandler(404)
    def not_found(_):
        return render_template("error.html", code=404, message="Registro ou página não encontrado."), 404

    # ============ A TELA QUE ESTOURA VIRA UMA LINHA NA LISTA DE PROBLEMAS
    #
    # O QUE ISTO CORRIGE
    #     Ate aqui, tela que estourava devolvia a pagina crua do servidor e o
    #     unico registro do defeito era a lembranca de quem estava no balcao —
    #     que em dia de movimento e o que se perde primeiro. O escrevente fecha
    #     a janela, atende o proximo, e o mesmo defeito volta na semana
    #     seguinte com outra pessoa, que tambem nao anota.
    #
    # ANOTAR NUNCA DERRUBA A PAGINA DE ERRO
    #     `anotar_falha_de_tela` engole a propria falha e devolve None.
    #     Transformar um defeito em dois — e esconder o primeiro — seria pior
    #     que nao anotar. E ele nem tenta quando o erro e `database is locked`:
    #     gravar no banco que acabou de travar e disputar a mesma trava, e
    #     essa especie ja esta contada em `disputas_de_escrita.log`.
    @app.errorhandler(500)
    def erro_interno(erro):
        original = getattr(erro, "original_exception", None) or erro
        try:
            user = current_user()
            ajuda_problemas.anotar_falha_de_tela(
                db, original, agora=db.now(), onde=request.endpoint,
                caminho=request.path, versao=VERSION,
                usuario=(user["username"] if user else None))
        except Exception:                                      # noqa: BLE001
            pass
        recado = ("O sistema não conseguiu terminar o que você pediu, e "
                  "NADA foi gravado pela metade — a operação voltou atrás "
                  "inteira. O defeito já ficou anotado, com a tela e a hora, "
                  "para quem cuida do sistema. Se era um ato, refaça; se "
                  "acontecer de novo, avise o administrador.")
        try:
            return render_template("error.html", code=500, message=recado), 500
        except Exception:                                      # noqa: BLE001
            # A PAGINA DE ERRO TAMBEM PODE FALHAR — ela estende `base.html`,
            # que le o banco para montar o menu. Um banco fora do ar levaria
            # o erro do erro para a cara do escrevente.
            return recado, 500

    return app


def local_url(host: str, port: int) -> str:
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{display_host}:{port}"


def main():
    # A RESERVA DE MAQUINA VEM ANTES DE TUDO — inclusive antes de montar a
    # aplicacao, que e o pedaco mais caro do arranque (medido: 7,8 s). O
    # servidor nascia em prioridade ABAIXO DO NORMAL, herdada do padrao do
    # Agendador de Tarefas do Windows, e com a maquina ocupada o pior
    # atendimento passava de 10 segundos. Ver `recursos_da_maquina`.
    #
    # ELA NAO DERRUBA A ABERTURA: `reservar` nunca levanta, e devolve por
    # escrito o que nao conseguiu. Servidor que nao sobe porque o Windows
    # negou uma preferencia de desempenho e pior do que servidor lento.
    import recursos_da_maquina
    print(recursos_da_maquina.linha_do_arranque(recursos_da_maquina.reservar()))

    app = create_app()
    db: Database = app.extensions["db"]

    # A FOTOGRAFIA DESTA VERSAO. E o que faz a ajuda saber o que mudou sem que
    # ninguem escreva: `ajuda.fotografar` mede telas, arquivos e tabelas e
    # guarda os nomes, para a diferenca contra a versao anterior ser medida.
    #
    # AQUI, E NAO EM `create_app`, por dois motivos. O primeiro e o custo: sao
    # cerca de um terco de segundo lendo mais de duzentos arquivos, e a suite
    # cria milhares de aplicacoes em memoria. O segundo e a hora: medir as
    # telas exige que todas as rotas existam, e aqui elas existem.
    #
    # E ELE NAO DERRUBA A ABERTURA. Se a fotografia falhar, o sistema sobe sem
    # ela - e a ajuda fica sem saber o que mudou, que e menos do que ela sabia
    # antes, e nao o fim do expediente.
    import ajuda
    ajuda.fotografar(db, app, versao=VERSION, agora=db.now())
    host = db.get_setting("network_host", "0.0.0.0") or "0.0.0.0"
    # Para a instalacao oficial em rede, 127.0.0.1 impediria os clientes.
    if "--service" in sys.argv and host in {"127.0.0.1", "localhost"}:
        host = "0.0.0.0"
    port = parse_int(db.get_setting("network_port", "8765")) or 8765
    discovery_enabled = db.get_setting("discovery_enabled", "1") == "1"
    discovery_port = parse_int(db.get_setting("discovery_port", "8766")) or 8766

    def discovery_payload(client_ip: str) -> dict:
        ip = best_local_ip_for(client_ip)
        return {
            "app": APP_NAME, "version": VERSION, "unit": db.get_setting("unit_name", "Serventia Extrajudicial"),
            "hostname": socket.gethostname(), "host": ip, "port": port, "url": f"http://{ip}:{port}",
        }

    DiscoveryResponder(discovery_port, discovery_payload, discovery_enabled).start()
    # A porta 8766 permanece como canal de descoberta compativel com o localizador
    # instalado nos clientes, mesmo que um administrador configure uma porta adicional.
    if discovery_enabled and discovery_port != 8766:
        DiscoveryResponder(8766, discovery_payload, True).start()
    url = local_url(host, port)
    print(f"{APP_NAME} v{VERSION}")
    print(f"Servidor local: {url}")
    for ip in lan_ipv4_addresses():
        print(f"Rede: http://{ip}:{port}")
    if discovery_enabled:
        print(f"Descoberta automatica: UDP {discovery_port}")
    no_browser = os.environ.get("CARTORIO_GESTAO_NO_BROWSER") == "1" or "--service" in sys.argv
    if not no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    serve(app, host=host, port=port, threads=12)


if __name__ == "__main__":
    main()
