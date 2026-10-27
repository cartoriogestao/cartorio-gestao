from __future__ import annotations

import nome_humano as NOMEHUM

import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import banco_pg
from ajuda import init_ajuda_schema
from ajuda_base import init_ajuda_base_schema
from ajuda_problemas import init_problemas_schema
import dev_projetos
import produtividade
from rs_schema import init_rs_schema
from protesto_ar import init_pt_ar_schema
from protesto_boleto import init_pt_boleto_schema
from hc_schema import init_hc_schema
from ibge_schema import init_ibge_schema
import papel_seguranca as PAPEL
import agente as AG
import tarefa_processo as TP
import expediente_tarefa as EXPT
from atrib_certidao import init_atrib_certidao_schema
from caixa_schema import FUNCOES as FUNCOES_DE_FABRICA
from caixa_schema import init_caixa_schema
from nfse import init_nfse_schema
from as_schema import init_as_schema
from fr_schema import init_fr_schema
from identidade_do_robo import init_identidade_schema
# O RELATÓRIO DA INSPEÇÃO desta casa (12/08/2026) é dado dela, e não código:
# instalado, vira o plano de ação na primeira configuração; ausente — o
# repositório público não o leva (sanitização B2, 11/10/2026) —, não se
# importa plano nenhum.
try:
    from inspection_seed import RECOMMENDATIONS, REPORT_DATE, REPORT_SOURCE, REPORT_TITLE
except ImportError:
    RECOMMENDATIONS, REPORT_DATE, REPORT_SOURCE, REPORT_TITLE = [], "", "", ""
from notas_schema import init_notas_schema
from notas_certidao import init_notas_certidao_schema
from nt_publica_forma import init_nt_publica_forma_schema
from nt_veiculo_detran import init_nt_veiculo_detran_schema
from rg_livro_contabil import init_rg_livro_contabil_schema
from rg_notificacao import init_rg_notificacao_schema
import notas_modelos
from nucleo_schema import init_nucleo_schema
from cn_schema import init_cn_schema
from pt_schema import init_pt_schema
from ra_schema import init_ra_schema
from rc_certidao import init_rc_certidao_schema
from rc_pedidos_schema import init_rc_pedidos_schema
from rc_modelos_livres_schema import init_rc_modelos_livres_schema
from modelos_elementos_schema import init_modelos_elementos_schema
from modelos_moldes import init_modelos_moldes_schema
from modelos_editor_schema import init_modelos_editor_schema
from rc_schema import init_rc_schema
from rg_schema import init_rg_schema
from ri_onr_central_schema import init_ri_onr_central_schema
from ri_mapa_onr import init_mapa_onr_schema
from apostila import init_apostila_schema
from livro_diario import init_livro_diario_schema
from livro_visitas import init_livro_visitas_schema
from centrais_schema import init_centrais_schema
from onr_endereco_schema import init_ri_onr_endereco_schema
from ri_schema import init_ri_schema
from security import hash_password, validate_password_strength, verify_password
from selador_config import init_selador_schema
from rt_schema import init_rt_schema
from us_schema import init_us_schema
from ex_schema import init_ex_schema
from tarefa_suspensao import init_suspensao_schema
import tarefa_suspensao as TS
from nu_avisos_gestao import init_nu_avisos_schema
from rascunho_de_tela import init_rascunho_schema
from protocolo_documentos import init_protocolo_documentos_schema
from rr_schema import init_rr_schema
from wa_schema import init_wa_schema
from robo_schema import init_robo_schema
from agente_schema import init_agente_schema
from ia_uso import init_ia_schema
from dois_fatores import init_dois_fatores_schema
from selo_portal import init_selo_portal_schema
from compliance import init_schema as init_compliance_schema
from gestor_schema import init_gestor_schema
from gestor_expedientes import init_schema as init_triagem_schema
from gestor_leitura import init_leitura_schema
from malote_agente import init_schema as init_malote_schema
from malote_fraudes import init_schema_ia as init_malote_fraudes_schema
from rc_leitura_documentos import init_schema as init_rc_leitura_schema
from ri_onus_ia import init_schema as init_ri_onus_ia_schema
from revisao_previa import init_schema as init_revisao_schema
from revisao_anexos import init_schema as init_revisao_anexos_schema
from minuta_ia import init_schema as init_minuta_ia_schema
from revisao_transcricao_lote import init_schema as init_revisao_transcricao_schema
from bd_nativo import banco

ISO_DT = "%Y-%m-%dT%H:%M:%S"

_FICTICIO: list[tuple[str, str]] = []


def _registro_ficticio() -> tuple[str, str]:
    """Sal e hash de uma senha que ninguém tem, para gastar o mesmo PBKDF2
    quando o usuário não existe. Feito na primeira vez, e não no import: são
    310 mil voltas, e a suíte importa este módulo milhares de vezes."""
    if not _FICTICIO:
        rec = hash_password("ficticio-" + datetime.now().isoformat())
        _FICTICIO.append((rec.salt_hex, rec.hash_hex))
    return _FICTICIO[0]


def _pg(sql: str) -> str:
    """Os pedaços de SQL que `tarefa_processo`, `tarefa_suspensao` e
    `tarefa_ordem` ENTREGAM ainda trazem `?`, porque outros consumidores deles
    passam pela ponte. Aqui, que executa nativo, a troca é feita no ponto de
    uso — como em `tarefa_processo._pg`. Sai quando eles entregarem `%s`."""
    return sql.replace("%", "%%").replace("?", "%s")


def _segundos(inicio: str | None, fim: str | None) -> float | None:
    """`fim - inicio` em segundos, das horas ISO gravadas. Hora que não se lê
    não entra na média — como o `julianday` nulo que ela fazia no SQL."""
    try:
        return (datetime.fromisoformat(fim) - datetime.fromisoformat(inicio)).total_seconds()
    except (TypeError, ValueError):
        return None


# AS SEMENTES DA IDENTIDADE DA SERVENTIA NASCEM VAZIAS — sanitização B2b,
# 10/10/2026. Elas guardavam o nome, o CNS, a cidade, o titular, a substituta,
# os feriados municipais e a pasta de backup DESTA casa, e por elas o código
# público levaria a casa junto. Vazias, quem as preenche numa instalação nova é
# o PERFIL LOCAL (`tools/migrar_settings_serventia_b0.py`, que só grava chave
# ausente ou em branco) e a tela de Configurações; quem lê uma delas em branco
# cai no padrão genérico de `serventia.PADRAO`. A produção não muda: as oito
# chaves estão gravadas lá (medido em 10/10/2026), e `ON CONFLICT DO NOTHING`
# não as toca.
DEFAULT_SETTINGS = {
    "unit_name": "",
    "alert_days": "5",
    "session_timeout_minutes": "60",
    # O PRAZO ABSOLUTO DA SESSÃO (B7 do LS01, lote LX11), em horas desde o login.
    "session_absolute_hours": "12",
    "require_backup_assignee": "1",
    "auto_backup": "1",
    "backup_retention": "30",
    # Backup completo (banco + digitalizacoes) uma vez por semana. As imagens
    # sao imutaveis: repeti-las todo dia gastaria disco sem proteger mais nada.
    "backup_completo_dia": "6",
    "backup_completo_retencao": "8",
    "archive_root": "",
    # AS PASTAS DE ONDE O BALCÃO IMPORTA, uma por linha (LX12, 19/10/2026).
    # Caminho digitado nas telas de importação (acervo, Livro 3, matrículas
    # digitadas, assinaturas) só vale dentro da pasta de dados, da raiz dos
    # arquivos ou de uma destas — ver `pastas_da_casa.dentro_da_casa`. Vazio =
    # só as duas primeiras. Quem grava é o oficial, em Configurações.
    "pastas_de_importacao": "",
    "backup_dir": "",
    # A copia fora do servidor, exigida pelo Provimento CN-CNJ 213/2026: as
    # copias de seguranca ficam em ambiente tecnicamente independente do
    # processamento primario. Quem leva ate la e o ESPELHAR_BACKUP.cmd, e nao
    # o servico: o servidor roda como SYSTEM e nao enxerga a nuvem montada na
    # sessao do usuario.
    "backup_espelho": "",
    "network_host": "0.0.0.0",
    "network_port": "8765",
    "discovery_enabled": "1",
    "discovery_port": "8766",
    # Feriados estaduais e municipais, uma data ISO por linha. Os nacionais e
    # os moveis (carnaval, sexta-santa, corpus christi) o sistema ja calcula.
    # Vazio = `<arquivos>/eoficio/ONR_IMAGENS` (ver pastas_da_casa).
    "ri_imagens_raiz": "",
    "ri_cns": "",
    # QUANDO A TABELA DE CUSTAS EM USO PASSOU A VALER — so a data.
    #
    # O selo leva a versao da tabela, e ela e o numero da SECAO da atribuicao
    # mais esta data: `01` no civil, `02` no imovel, `03` no protesto, `04` no
    # RTD/PJ, `05` nas notas. O prefixo e medido e mora no codigo; a data e
    # configuracao, porque muda quando o TJMA publica tabela nova — e nesse dia
    # ninguem quer mexer no codigo para o balcao voltar a selar.
    #
    # Medido em 27/08/2026 nos selos de 2026 do acervo.
    "selo_tabela_custas_em": "20260101",
    "ri_cidade": "",
    "ri_uf": "",
    # O NOME DO TITULAR JÁ ESTEVE ESCRITO AQUI COM UMA LETRA A MENOS
    # (corrigido em 07/09/2026), e em 16/09/2026 mudou de caixa por ordem do
    # oficial — e como `DEFAULT_SETTINGS` só entra com `ON CONFLICT DO NOTHING`, o
    # valor errado já gravado num banco não se corrige sozinho: salva-se de
    # novo pela tela de Configurações. Desde a B2b a semente é vazia e o nome
    # vem do perfil local; a lição continua: semente não conserta o que já está
    # gravado.
    "ri_registrador": "",
    "ri_substituta": "",
    "ri_feriados_locais": "",
    "password_min_length": "6",
    "password_require_upper": "0",
    "password_require_lower": "0",
    "password_require_digit": "0",
    "categories": json.dumps(["Circulares", "Editais Interinidade", "Para Cumprimento", "Portarias", "Ordens Judiciais", "Ofícios", "Outros"], ensure_ascii=False),
    "sources": json.dumps(["Malote Digital", "PJe", "E-mail institucional", "Ofício físico", "COGEX", "CNJ", "Outro"], ensure_ascii=False),
    "sectors": json.dumps(["Gestão", "Administração", "Atendimento", "TI", "LGPD", "Compliance", "Protesto", "Notas", "RCPJ", "RTD", "RCPN", "Registro de Imóveis"], ensure_ascii=False),
    # OS CARGOS ERAM FIXOS NO CÓDIGO — pedido do oficial em 08/09/2026, logo
    # depois de a tela passar a deixar editar nome e usuário. `FUNCOES` em
    # `caixa_schema.py` continua sendo o de fábrica (a nomenclatura da Lei
    # 8.935/94, arts. 20 e 21), e semeia esta configuração uma vez; dali em
    # diante quem manda é o que estiver gravado aqui — a serventia pode ter
    # cargo que a Lei não nomeia. Nenhum código decide nada pelo TEXTO do
    # cargo (é só o que sai impresso embaixo da assinatura), então renomear
    # não quebra nada além do rótulo.
    "funcoes_cargos": json.dumps(list(FUNCOES_DE_FABRICA), ensure_ascii=False),
}


class Database:
    # QUANTO UM BALCAO ESPERA O OUTRO antes de desistir. Dez segundos: e o
    # tempo em que ninguem acha que travou, e e mais do que qualquer escrita
    # desta casa leva. Estourar isso e o que vira "database is locked" — e o
    # que o sistema anota em `disputas_de_escrita.log`.
    #
    # E atributo, e nao numero solto, para o teste poder baixa-lo: com dez
    # segundos, provar uma disputa de verdade custaria dez segundos por teste.
    BUSY_TIMEOUT_MS = 10_000

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if banco_pg.ativo():
            banco_pg.registrar_banco(self.db_path)
            banco_pg.instalar_desvio()
            # O ARQUIVO VAZIO É MARCA, E NÃO BANCO: 45 testes (e quem mais
            # procurar) acham o banco pelo arquivo `*.sqlite3` na pasta de
            # dados, e no PostgreSQL ele não nascia (medido pelo L6, 15/10
            # 20h). Quem o abre pelo sqlite3 cai no desvio e vai ao schema.
            if not self.db_path.exists():
                self.db_path.touch()
            # Banco novo: reproduz a criação gravada (ver banco_pg); o primeiro
            # do processo roda o init_schema e grava. Banco existente migra
            # pelo init_schema de sempre.
            if not banco_pg.schema_existe(self.db_path):
                if banco_pg.tomar_da_reserva(self.db_path):
                    return
                if banco_pg.criar_por_reproducao(self.db_path):
                    return
                banco_pg.comecar_gravacao(self.db_path)
                deu_certo = False
                try:
                    self.init_schema()
                    deu_certo = True
                finally:
                    banco_pg.terminar_gravacao(deu_certo)
                if deu_certo:
                    banco_pg.guardar_semente(self.db_path)
                return
        self.init_schema()

    def connect(self) -> banco_pg.Conexao:
        # O BANCO É O POSTGRESQL (migração de 15/10/2026, `banco_pg.py`; este
        # módulo é nativo desde o lote L072). A conexão devolvida é a da ponte,
        # que o resto do sistema ainda usa como a do sqlite3: linhas com nome e
        # o `with` que fecha. Sem `CG_PG_DSN`, `banco()` recusa — módulo nativo
        # não roda no SQLite.
        con = banco_pg.conectar(self.db_path, fechar_no_with=True,
                                linhas_com_nome=True)
        try:
            # A ESPERA PELA TRAVA é a da casa (`BUSY_TIMEOUT_MS`), e não a que
            # a conexão trouxe do reservatório.
            banco(con).ler(f"SET lock_timeout = '{int(self.BUSY_TIMEOUT_MS)}ms'")
        except BaseException:
            con.close()
            raise
        return con

    # ------------------------------------------------- disputa de escrita
    #
    # `db.transaction()` e `BEGIN IMMEDIATE`: um escritor por vez, e os outros
    # esperam ate `busy_timeout`. Quando a espera estoura, o SQLite devolve
    # "database is locked" e a transacao volta atras inteira — nada se perde,
    # mas o balcao leva um erro na cara.
    #
    # UMA VEZ OU OUTRA E NORMAL. Virar rotina e o sinal MEDIDO de que o SQLite
    # deixou de bastar para esta casa — e e o unico gatilho honesto para a
    # conversa sobre trocar de banco. Ver `DOCUMENTACAO/MIGRAR_DE_BANCO.md`.
    #
    # O REGISTRO VAI PARA ARQUIVO, E NAO PARA O BANCO. Gravar a disputa dentro
    # do banco que acabou de travar seria disputar a mesma trava — e no pior
    # caso perder justamente o registro que interessa.
    NOME_DO_REGISTRO_DE_DISPUTAS = "disputas_de_escrita.log"

    @property
    def registro_de_disputas(self) -> Path:
        return self.db_path.parent / self.NOME_DO_REGISTRO_DE_DISPUTAS

    @staticmethod
    def _e_disputa(erro: BaseException) -> bool:
        """`database is locked` e `database is busy`, e mais nada."""
        if not isinstance(erro, sqlite3.OperationalError):
            return False
        texto = str(erro).lower()
        return "locked" in texto or "busy" in texto

    def _anotar_disputa(self, erro: BaseException) -> None:
        """Uma linha por disputa. Nunca estoura: aviso nao derruba atendimento."""
        try:
            with self.registro_de_disputas.open("a", encoding="utf-8") as f:
                f.write(self.now() + "\t" + str(erro).strip() + "\n")
        except OSError:
            pass

    def disputas_de_escrita(self, desde_dias: int = 30) -> dict:
        """Quantas vezes o banco travou, e quando. So LE.

        Devolve `{"total", "recentes", "primeira", "ultima", "arquivo"}`.
        Arquivo que nao existe e casa sem disputa nenhuma — que e o caso
        conferido em 25/08/2026, sobre um ano de uso.
        """
        vazio = {"total": 0, "recentes": 0, "primeira": None, "ultima": None,
                 "arquivo": str(self.registro_de_disputas)}
        try:
            linhas = [x for x in self.registro_de_disputas.read_text(
                encoding="utf-8", errors="replace").splitlines() if x.strip()]
        except OSError:
            return vazio
        if not linhas:
            return vazio
        quando = [x.split("\t")[0] for x in linhas]
        corte = (datetime.fromisoformat(self.now())
                 - timedelta(days=int(desde_dias))).date().isoformat()
        return {"total": len(linhas),
                "recentes": sum(1 for q in quando if q[:10] >= corte),
                "primeira": quando[0][:19], "ultima": quando[-1][:19],
                "arquivo": str(self.registro_de_disputas)}

    # ------------------------------------------------- a saude do banco
    #
    # A CONFERENCIA MORA AQUI PORQUE A CONEXAO MORA AQUI. Quem pergunta e
    # `ajuda_problemas.py`, que recebe a MEDICAO pronta e nao sabe de banco
    # nenhum.
    #
    # NO POSTGRESQL (lote L072) nao ha `quick_check` nem `foreign_key_check`:
    # a integridade das paginas e do servidor, e a chave estrangeira o proprio
    # banco recusa quebrar na gravacao. O que se confere aqui e que o banco
    # RESPONDE — e banco que nao responde continua sendo o achado.
    #
    # SO LE, e nao abre transacao de escrita: e chamada de tela.
    def conferencia_do_banco(self, limite_de_orfas: int = 50) -> dict:
        """Integridade e chaves orfas. So LE.

        Devolve `{"integridade", "orfas", "orfas_detalhe"}`. Falhar aqui nao
        pode derrubar tela: um banco que nao responde a conferencia ja e o
        proprio achado, e e assim que ele sai escrito.
        """
        resultado = {"integridade": "ok", "orfas": 0, "orfas_detalhe": ""}
        try:
            con = self.connect()
        except sqlite3.Error as erro:
            return {"integridade": f"nao consegui abrir o banco: {erro}",
                    "orfas": 0, "orfas_detalhe": ""}
        try:
            resposta = banco(con).valor("SELECT 'ok' AS integridade")
            resultado["integridade"] = str(resposta or "sem resposta")
        except sqlite3.Error as erro:
            resultado["integridade"] = f"a conferencia nao terminou: {erro}"
        finally:
            con.close()
        return resultado

    @contextmanager
    def transaction(self):
        con = self.connect()
        try:
            # Um escritor por vez, como era o `BEGIN IMMEDIATE`: a transação
            # abre já com a trava da ponte, e a trava que não vem sobe como
            # "database is locked".
            banco(con)._escrita()
            yield con
            con.commit()
        except Exception as erro:
            con.rollback()
            # A ANOTACAO NAO MUDA O QUE ACONTECE: o erro sobe igual, e a
            # transacao volta atras igual. Ela so deixa o rastro para depois.
            if self._e_disputa(erro):
                self._anotar_disputa(erro)
            raise
        finally:
            con.close()

    def init_schema(self) -> None:
        con = self.connect()
        bd = banco(con)
        # O DDL e nativo (lote L072), um comando por vez. A ORDEM IMPORTA no
        # PostgreSQL: chave estrangeira para tabela que ainda nao existe
        # estoura, e por isso `inspections` e `recurring_obligations` vem
        # antes de `tasks`.
        for comando in re.split(r";[ \t]*\n", """
            CREATE TABLE IF NOT EXISTS users (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE public.cg_nocase,
                full_name TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'USER',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                created_by INTEGER,
                FOREIGN KEY(created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                ts TEXT NOT NULL,
                user_id INTEGER,
                username_snapshot TEXT,
                action TEXT NOT NULL,
                entity_type TEXT,
                entity_id INTEGER,
                details TEXT,
                ip_address TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS expedientes (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                internal_protocol TEXT UNIQUE,
                source TEXT NOT NULL,
                external_reference TEXT,
                sender TEXT,
                subject TEXT NOT NULL,
                category TEXT NOT NULL,
                sector TEXT,
                received_at TEXT NOT NULL,
                deadline_start TEXT,
                deadline_days INTEGER,
                deadline_date TEXT,
                priority TEXT NOT NULL DEFAULT 'MEDIA',
                assigned_user_id INTEGER,
                backup_user_id INTEGER,
                stage TEXT NOT NULL DEFAULT 'RECEBIDO',
                notes TEXT,
                response_reference TEXT,
                responded_at TEXT,
                completed_at TEXT,
                completed_by INTEGER,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(assigned_user_id) REFERENCES users(id),
                FOREIGN KEY(backup_user_id) REFERENCES users(id),
                FOREIGN KEY(completed_by) REFERENCES users(id),
                FOREIGN KEY(created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS inspections (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                title TEXT NOT NULL,
                report_date TEXT,
                source_filename TEXT,
                start_date TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recurring_obligations (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                title TEXT NOT NULL,
                system_name TEXT,
                sector TEXT,
                frequency TEXT NOT NULL,
                due_day INTEGER,
                due_month INTEGER,
                lead_days INTEGER NOT NULL DEFAULT 5,
                assigned_user_id INTEGER,
                backup_user_id INTEGER,
                active INTEGER NOT NULL DEFAULT 1,
                next_due_date TEXT,
                evidence_required INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(assigned_user_id) REFERENCES users(id),
                FOREIGN KEY(backup_user_id) REFERENCES users(id),
                FOREIGN KEY(created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                source_type TEXT NOT NULL DEFAULT 'MANUAL',
                source_ref TEXT,
                inspection_id INTEGER,
                recurrence_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                sector TEXT,
                system_name TEXT,
                priority TEXT NOT NULL DEFAULT 'MEDIA',
                status TEXT NOT NULL DEFAULT 'ABERTA',
                due_days INTEGER,
                start_date TEXT,
                due_date TEXT,
                assigned_user_id INTEGER,
                backup_user_id INTEGER,
                linked_expediente_id INTEGER,
                evidence_required INTEGER NOT NULL DEFAULT 1,
                source_page INTEGER,
                legal_ref TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                completed_by INTEGER,
                FOREIGN KEY(inspection_id) REFERENCES inspections(id),
                FOREIGN KEY(recurrence_id) REFERENCES recurring_obligations(id),
                FOREIGN KEY(assigned_user_id) REFERENCES users(id),
                FOREIGN KEY(backup_user_id) REFERENCES users(id),
                FOREIGN KEY(linked_expediente_id) REFERENCES expedientes(id),
                FOREIGN KEY(created_by) REFERENCES users(id),
                FOREIGN KEY(completed_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS task_history (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                task_id INTEGER NOT NULL,
                ts TEXT NOT NULL,
                user_id INTEGER,
                action TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                note TEXT,
                FOREIGN KEY(task_id) REFERENCES tasks(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS attachments (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes BIGINT NOT NULL,
                description TEXT,
                uploaded_by INTEGER,
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY(uploaded_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS checklist_templates (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                sector TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS checklist_items (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                template_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                text TEXT NOT NULL,
                required INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(template_id) REFERENCES checklist_templates(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS checklist_runs (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                template_id INTEGER NOT NULL,
                reference TEXT,
                run_date TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'ABERTO',
                notes TEXT,
                completed_at TEXT,
                FOREIGN KEY(template_id) REFERENCES checklist_templates(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS checklist_run_items (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                run_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                checked INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                FOREIGN KEY(run_id) REFERENCES checklist_runs(id) ON DELETE CASCADE,
                FOREIGN KEY(item_id) REFERENCES checklist_items(id)
            );

            CREATE TABLE IF NOT EXISTS assets (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                identifier TEXT,
                location TEXT,
                responsible_user_id INTEGER,
                status TEXT NOT NULL DEFAULT 'REGULAR',
                expiry_date TEXT,
                last_check_date TEXT,
                notes TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(responsible_user_id) REFERENCES users(id),
                FOREIGN KEY(created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS lgpd_items (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                item_type TEXT NOT NULL,
                title TEXT NOT NULL,
                owner_user_id INTEGER,
                status TEXT NOT NULL DEFAULT 'PENDENTE',
                review_date TEXT,
                notes TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(owner_user_id) REFERENCES users(id),
                FOREIGN KEY(created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS service_tickets (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                ticket_no INTEGER NOT NULL,
                ticket_date TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 0,
                service_type TEXT,
                status TEXT NOT NULL DEFAULT 'AGUARDANDO',
                created_at TEXT NOT NULL,
                called_at TEXT,
                started_at TEXT,
                finished_at TEXT,
                attendant_user_id INTEGER,
                notes TEXT,
                FOREIGN KEY(attendant_user_id) REFERENCES users(id),
                UNIQUE(ticket_date, ticket_no)
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_status_due ON tasks(status, due_date);
            CREATE INDEX IF NOT EXISTS idx_tasks_sector ON tasks(sector);
            CREATE INDEX IF NOT EXISTS idx_exp_stage_deadline ON expedientes(stage, deadline_date);
            CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_logs(ts);
            CREATE INDEX IF NOT EXISTS idx_attach_entity ON attachments(entity_type, entity_id);
            CREATE INDEX IF NOT EXISTS idx_ticket_date_status ON service_tickets(ticket_date, status);
            """):
            if comando.strip():
                bd.escrever(comando)
        # A CORRENTE DE HASH DA AUDITORIA (revisao de seguranca de 22/10/2026).
        # Duas colunas que so se acrescentam — a producao migra ao subir, e as
        # linhas antigas ficam sem hash: a corrente comeca na primeira linha
        # gravada depois disto. Quem preenche e o GATILHO do PostgreSQL, para
        # valer tambem nos 31 arquivos que inserem na tabela por fora de
        # `db.log`; o lado Python que recalcula esta em `auditoria_cadeia`.
        for coluna in ("hash_anterior", "hash_linha"):
            if not bd.tem_coluna("audit_logs", coluna):
                bd.escrever(f"ALTER TABLE audit_logs ADD COLUMN {coluna} TEXT")
        # QUEM AGE POR PROGRAMA DIZ QUEM E E A MANDO DE QUEM (ordem do
        # oficial, 26/10/2026): `audit_logs.agente`, `audit_logs.a_mando_de` e
        # `users.robo_responsavel_id`. So ADD COLUMN; quem preenche e
        # `identidade_do_robo.registrar`, por onde passa o `log` daqui de baixo.
        # E `audit_logs.hash_versao`: desde a revisao de seguranca de 26/10 as
        # duas colunas ENTRAM no hash da corrente (formula 2), e a versao por
        # linha deixa as antigas conferirem pela formula de 22/10
        # (`cg_auditoria_encadear` e `auditoria_cadeia.hash_da_linha`).
        init_identidade_schema(con)
        gatilho = ("CREATE OR REPLACE TRIGGER audit_logs_cadeia BEFORE INSERT ON audit_logs "
                   "FOR EACH ROW EXECUTE FUNCTION public.cg_auditoria_encadear()")
        # `_cru` porque a ponte recusa `CREATE TRIGGER` (o do SQLite nao se traduz)
        # — e por isso ela tambem NAO anota o comando na gravacao do banco novo:
        # os schemas reproduzidos (`banco_pg.criar_por_reproducao`, a suite com
        # -n 4) nasciam sem o gatilho, e so o primeiro tinha a corrente. Medido
        # em 22/10/2026: 3 vermelhas em paralelo, verdes em serie. A anotacao vai
        # a mao; fora da gravacao ela nao faz nada.
        bd._cru(gatilho)
        if getattr(bd, "_ponte", None) is not None:
            bd._ponte._anotar(None, gatilho, None)
        init_nucleo_schema(con)   # o nucleo primeiro: as outras apontam para ele
        init_pt_schema(con)
        # A INTIMACAO DIGITAL vem LOGO DEPOIS do Protesto, e nao antes:
        # `rs_intimacoes` tem chave estrangeira para `pt_titulos`, e a tabela
        # apontada precisa existir primeiro.
        init_rs_schema(con)
        # O AR DIGITAL E O BOLETO DO DEVEDOR (LG06, 19/10/2026) vem logo depois,
        # pela mesma razao: `pt_ar_postagens` aponta para `pt_avisos`, e as
        # duas apontam para `pt_titulos` e `pt_atos`. As integracoes nascem
        # desligadas; as tabelas existem para o dia em que forem ligadas.
        init_pt_ar_schema(con)
        init_pt_boleto_schema(con)
        # AS PENDENCIAS DA CENPROT vem LOGO DEPOIS do Protesto, porque a
        # `titulo_id` delas aponta para `pt_titulos`: chave estrangeira para
        # tabela que ainda nao existe estoura ao abrir o banco.
        init_cn_schema(con)
        # A LISTA DE ATENCAO PARA FRAUDES serve as SEIS atribuicoes, como o
        # nucleo — por isso entra aqui, e nao dentro de uma delas.
        init_fr_schema(con)
        # A FILA DE ASSINATURA E DA CASA INTEIRA, como o nucleo e a lista de
        # fraudes: hoje o sistema emite nove papeis, e o instrumento de
        # protesto e o decimo. O que muda de um para o outro e o documento, e
        # nao a assinatura.
        init_as_schema(con)
        init_rc_schema(con)
        init_rc_certidao_schema(con)
        # A fila da Central de Certidoes vem DEPOIS de rc_assentos:
        # `rc_pedidos.assento_id` e `rc_certidoes_eletronicas.assento_id`
        # apontam para ela.
        init_rc_pedidos_schema(con)
        # OS MODELOS DO ESCREVENTE vem depois de `rc_assentos` pela mesma
        # razao da fila: eles se montam de um assento, e a tela que os
        # emite parte dele.
        init_rc_modelos_livres_schema(con)
        init_ajuda_schema(con)
        # OS VERBETES DA BASE DE CONHECIMENTO vem junto, e NÃO depois: é a
        # mesma família de `aj_consultas` — a ajuda lê os dois no mesmo
        # contexto, e uma instalação sem esta tabela responderia «o oficial não
        # escreveu nada» com cara de medição. O `init` é idempotente.
        init_ajuda_base_schema(con)
        # Os PROBLEMAS vem logo depois da ajuda: e a mesma familia, e
        # `aj_problemas` so faz sentido com `aj_consultas` de pe — o
        # diagnostico de um problema e uma consulta.
        init_problemas_schema(con)
        dev_projetos.init_dev_projetos_schema(con)
        produtividade.init_produtividade_schema(con)
        # **AS NOTAS DO DESENVOLVIMENTO CHEGAM AQUI** — relato #35, «os que
        # forem resolvidos a IA ou desenvolvedor ja coloca a prova do
        # cumprimento ou relata alguma pendencia».
        #
        #   Elas viajam no pacote porque quem as escreve **so le** o banco do
        #   servidor: uma nota digitada no projeto nao chegaria a maquina do
        #   balcao de jeito nenhum, e entregar um arquivo para o oficial
        #   aplicar poria nele um trabalho de digitacao que e do
        #   desenvolvimento.
        #
        #   **Nao sobrescreve o que uma pessoa escreveu** e **nao fecha
        #   problema nenhum** — `situacao` continua sendo o clique dele.
        #
        #   E **nao derruba a subida**: `aplicar` nao estoura, e o que ela nao
        #   conseguir fazer vem no que ela devolve. Balcao parado e pior que
        #   nota faltando.
        #   AS NOTAS SÃO O DIÁRIO DESTA CASA, e o repositório público não as
        #   leva (sanitização B2, 11/10/2026): sem o módulo, não há o que aplicar.
        try:
            import notas_do_desenvolvimento as NOTAS_DEV
            self.notas_do_desenvolvimento = NOTAS_DEV.aplicar(
                con, agora=self.now())
        except ModuleNotFoundError:
            self.notas_do_desenvolvimento = {}
        except Exception as erro:                          # noqa: BLE001
            self.notas_do_desenvolvimento = {"erro": str(erro)}
        # QUEM CRIOU CADA PROBLEMA — relato #87, 23/09/2026. Os antigos ganham
        # o dono pela auditoria; idempotente, e na mesma regra das notas: nao
        # derruba a subida.
        # `from ... import`, e nao `import ... as`: e a forma pela qual o
        # varredor de funcao sem tela reconhece o que a subida chama — a
        # mesma dos `init_*_schema`.
        try:
            from ajuda_problemas import preencher_criado_por
            self.criado_por_dos_problemas = preencher_criado_por(con)
        except Exception as erro:                          # noqa: BLE001
            self.criado_por_dos_problemas = {"erro": str(erro)}
        # O PAPEL DE SEGURANCA e do Registro Civil, e vem depois dele:
        # a folha se amarra ao ato, e o ato mora nas tabelas do civil.
        PAPEL.init_papel_schema(con)
        # A HABILITACAO DE CASAMENTO — o processo que antecede o assento
        # do Livro B. Depende de `rc_assentos` para amarrar o proclama e
        # o casamento, e por isso entra depois do esquema do civil.
        init_hc_schema(con)
        # O DE-PARA DO IBGE nao depende de tabela nenhuma — e cadastro oficial,
        # trazido do acervo. Entra aqui, ao lado do civil, porque e a remessa
        # do Registro Civil que o usa.
        init_ibge_schema(con)
        init_selador_schema(con)
        init_ri_schema(con)
        # OS ELEMENTOS DOS MODELOS vem DEPOIS de `ri_schema`, que e onde
        # mora `mo_modelos`: a resolucao de um elemento cai no legado
        # daquela tabela quando nao ha linha nova, e ela precisa existir.
        init_modelos_elementos_schema(con)
        # O PAPEL DA CERTIDAO DO RCPN — o `.odt` que o oficial desenha. Vem
        # junto dos elementos porque e a mesma tela (Administrativo →
        # Modelos), e **nao depende de tabela nenhuma**: a chave e o nome do
        # papel no catalogo do proprio modulo.
        init_modelos_moldes_schema(con)
        # VERSIONAMENTO DO EDITOR DE MODELOS (Marco 1)
        init_modelos_editor_schema(con)
        init_ra_schema(con)  # o Livro 3 conta pelo contador do RI, logo depois dele
        init_us_schema(con)  # usucapiao aponta para ri_matriculas e ri_atos
        # O RASTRO DO QUE SOBE AO ONR VEM DEPOIS DAS DUAS QUE ELE CITA —
        # `ri_matriculas` (o indicador real) e `us_processos` (o edital). Com a
        # trava de chave estrangeira ligada, criar a tabela antes delas faria a
        # primeira gravacao estourar.
        init_ri_onr_central_schema(con)
        # A BASE DO MAPA DO ONR (LF02, 19/10/2026) — a VIEW que o plugin do
        # QGIS le e o de-para da area, refeito a cada subida. Depois do RI,
        # porque a VIEW le `ri_matriculas` e `ri_partes`.
        init_mapa_onr_schema(con)
        # A APOSTILA DE HAIA (LG03, 19/10/2026) — o pedido, o documento e o
        # controle numerado. As duas tabelas só apontam uma para a outra; a
        # cobrança é pelo item do protocolo geral, sem chave estrangeira.
        init_apostila_schema(con)
        # OS LIVROS ADMINISTRATIVOS DE TODA SERVENTIA (LG08, 19/10/2026) —
        # Código de Normas do MA, art. 188: o de Visitas e Correições e o
        # Diário Auxiliar (despesas e as versões geradas). Não apontam para
        # tabela de outro módulo: a receita do Diário é LIDA do selo.
        init_livro_visitas_schema(con)
        init_livro_diario_schema(con)
        # A FILA GENERICA DAS CENTRAIS e o log delas (marco (a), 05/10/2026).
        # Nao apontam para tabela de dominio nenhuma — `payload_ref` e texto —,
        # e por isso podem nascer em qualquer ponto; ficam ao lado do ONR.
        init_centrais_schema(con)
        # A FILA DA CONFERENCIA DO ENDERECO vem logo depois, e pelo mesmo
        # motivo: ela aponta para `ri_matriculas`, que acabou de existir.
        init_ri_onr_endereco_schema(con)
        # A retificacao de area aponta para as MESMAS duas tabelas, e pelo
        # mesmo motivo: ela termina numa averbacao e numa matricula nova.
        init_rt_schema(con)
        # Retificacao, restauracao e suprimento do RCPN — depois do
        # `rc_schema`, porque `rr_processos` aponta para `rc_assentos`
        # e `rc_atos`.
        init_rr_schema(con)
        # AS DUAS TABELAS DO «o que comecou e nao terminou». Podem vir
        # por ultimo: nenhuma aponta para tabela nenhuma — `ex_anotacoes`
        # guarda o nome da tabela como TEXTO, porque serve nove delas.
        init_ex_schema(con)
        # A SUSPENSÃO DA TAREFA — relato #132, 15/10/2026: colunas novas em
        # `tasks`, só acrescentadas, e a produção migra ao subir.
        init_suspensao_schema(con)
        # O RASCUNHO DE QUALQUER TELA — relato #36 do oficial:
        # «em todos os atos (...) um campo para salvar o
        # progresso e continuar depois».
        init_rascunho_schema(con)
        # OS DOCUMENTOS PARA QUALIFICACAO DO PROTOCOLO GERAL — relato #135,
        # 15/10/2026. So `ADD COLUMN` em `attachments` (o tipo do documento e a
        # retirada com motivo): a tabela de anexo continua sendo uma so.
        init_protocolo_documentos_schema(con)
        # A FILA DO WHATSAPP mora DENTRO desta casa (mesmo SQLite).
        init_wa_schema(con)
        # ROBOS DE RASCUNHO (fatia 1) — mesmo SQLite, nunca livro.
        init_robo_schema(con)
        # O AGENTE DO SISTEMA — as sessoes dele, os passos, as mudancas
        # reversiveis e a configuracao. Tabelas proprias, e nao campos em
        # `aj_consultas`: apagar o historico do agente nao pode levar junto o
        # registro de uma consulta que o balcao fez. Tabelas separadas erram
        # separado — e aqui as duas guardam mascara, que e o que torna a
        # separacao tambem uma questao de risco.
        init_agente_schema(con)
        # O REGISTRO DO USO DE IA (LF01) — `ia_uso`, os incidentes e os dados
        # dos fornecedores, para o relatório anual à COGEX. Não aponta para
        # tabela nenhuma: a referência ao registro de origem é texto.
        init_ia_schema(con)
        # AS TABELAS DOS AGENTES E DAS LEITURAS DE IA NASCEM NA SUBIDA (LH09,
        # 21/10/2026), e não só na primeira vez que a função do módulo roda.
        # Medido no banco da produção: 19 tabelas com dados (cp_*, ge_*, mt_*,
        # rc_leituras, ri_onus_sugestoes, rv_*) que a subida do código no
        # PostgreSQL não criava — cada módulo as criava preguiçoso, ao rodar (a
        # 20ª, `_ping`, não é do sistema: ver `banco_pg.TABELAS_FORA_DA_CARGA`). A
        # carga da virada precisa delas ANTES, com os tipos que o código grava;
        # e quem confere a carga contra o banco recém-subido as dava como
        # «não vieram». Cada `init` é o do módulo dono (o mesmo DDL que ele já
        # roda sozinho, idempotente), e nenhuma tabela aponta para outra: a
        # posição não depende de ordem. A lista tabela → quem cria → como a
        # carga leva está em `docs/VIRADA_TABELAS_E_ACERVO.md`.
        init_compliance_schema(con)
        init_gestor_schema(con)
        init_triagem_schema(con)
        init_leitura_schema(con)
        init_malote_schema(con)
        init_malote_fraudes_schema(con)
        init_rc_leitura_schema(con)
        init_ri_onus_ia_schema(con)
        init_revisao_schema(con)
        init_revisao_anexos_schema(con)
        # O AGENTE DE MINUTAS (23/10/2026) — `mi_pedidos`, os pedidos e as
        # versões de cada minuta. Não aponta para tabela nenhuma.
        init_minuta_ia_schema(con)
        # A REVISÃO DAS TRANSCRIÇÕES DO RI (LH11) também nasce aqui (LH12): a
        # emissão da certidão de inteiro teor grava em `ri_transcricao_
        # emissoes` dentro da transação que numera, e o DDL ali viria depois do
        # número. O `init` do lote cria as quatro (revisões, emissões, lotes e
        # itens); os itens apontam para os lotes, criados antes no mesmo init.
        init_revisao_transcricao_schema(con)
        # A VERIFICAÇÃO EM DUAS ETAPAS (LG02) — o segredo cifrado e os códigos
        # de recuperação. Aponta para `users`, que nasceu lá em cima.
        init_dois_fatores_schema(con)
        # O QUE SE DEVE AO PORTAL DO SELO (LG07) — o pedido de cancelamento ao
        # TJMA e o pacote do ressarcimento das gratuidades. Aponta para
        # `sd_selos` e `attachments`, que nasceram lá em cima.
        init_selo_portal_schema(con)
        init_nu_avisos_schema(con)
        # A SESSAO QUE FICOU ABERTA PORQUE O PROGRAMA PAROU NO MEIO VIRA
        # INTERROMPIDA, e volta a poder ser continuada: `responder` recusa sessao
        # aberta — «alguem esta rodando agora» —, e e essa recusa que impede duas
        # rodadas da mesma conversa. Sem esta passada, fechar o console no meio de
        # um turno prenderia o diagnostico que ja foi pago, com a lista mostrando
        # «em curso» para sempre. E idempotente, como a recuperacao das folhas
        # presas: o que ja esta fechado nao se move de novo.
        self.sessoes_interrompidas_no_inicio = (
            AG.recuperar_sessoes_interrompidas(con, agora=self.now()))
        init_caixa_schema(con)
        # A TRAVA DO SELO PAGO (LX16, 19/10/2026) — o rastro ato↔item, o
        # protocolo em atendimento, o diferimento do Protesto, o débito do
        # depósito, as liberações do ADMIN. Logo depois do caixa: o
        # diferimento entra em `cx_protocolo_atos`.
        import ato_selado
        ato_selado.init_trava_do_selo_schema(con)
        # A NFS-e DOS EMOLUMENTOS (LG01, 19/10/2026) — `nfse_*` e as duas
        # colunas do recibo que guardam o número e a chave da nota. Logo depois
        # do caixa, porque as notas apontam para `cx_recibos`.
        init_nfse_schema(con)
        # RCPJ/RTD vem DEPOIS do caixa: `rg_titulos.protocolo_geral_id` aponta
        # para `cx_protocolos`, e o PostgreSQL cobra a FK ja na criacao (o
        # SQLite aceitava FK para tabela que ainda nao existe). Nenhum esquema
        # entre a posicao antiga e esta le ou aponta para `rg_*`.
        init_rg_schema(con)
        # A certidao das demais atribuicoes: depois de rg e ra, que ela le.
        init_atrib_certidao_schema(con)
        init_notas_schema(con)
        # A certidao das Notas (15/10/2026) depende de `nt_atos`, e por isso
        # vem logo depois do esquema das Notas.
        init_notas_certidao_schema(con)
        # OS ATOS DO LG04 (19/10/2026) — a notificação extrajudicial e a
        # autenticação de livros do RCPJ/RTD, a pública forma e a comunicação
        # de venda de veículo das Notas. Depois das Notas e do RCPJ/RTD, porque
        # apontam para `rg_registros`, `nt_reconhecimentos` e `nt_cartoes`.
        init_rg_notificacao_schema(con)
        init_rg_livro_contabil_schema(con)
        init_nt_publica_forma_schema(con)
        init_nt_veiculo_detran_schema(con)
        # FOLHA PRESA A ITEM JA CANCELADO VOLTA SOZINHA AO ESTOQUE. Esta
        # reconciliacao vem depois de TODOS os esquemas porque alcanca as
        # certidoes das quatro atribuicoes, os atos do RI e os assentos do
        # Registro Civil. E idempotente: folha ja recuperada nao se move de
        # novo; o caminho anterior fica em pp_movimentos.
        self.folhas_recuperadas_no_inicio = PAPEL.recuperar_cancelados_existentes(
            con, agora=self.now(), usuario="SISTEMA")
        # A BIBLIOTECA DE MODELOS DAS NOTAS ENTRA A CADA ABERTURA DO BANCO, e
        # não só depois da carga do acervo. Até 07/09/2026 só `notas_web.
        # notas_importar` chamava `notas_modelos.instalar` — instalação nova
        # sem carga nascia com a tela de abrir ato sem um modelo sequer, e
        # uma correção no texto de um modelo já instalado (como a da
        # escritura pública, ajustada ao padrão da minuta no mesmo dia) não
        # alcançava quem já tinha rodado a carga antes. `instalar()` só
        # escreve por cima do que ninguém editou (`atualizado_em IS NULL`).
        notas_modelos.instalar(con, self.now())
        # **AS COLUNAS QUE A BUSCA CONSULTA SE COMPLETAM AQUI** — e não só na
        # importação. Elas são derivadas (`_norm`) e quem grava a linha tem de
        # lembrar de calculá-las: em 15/09/2026 a ficha 3.110 entrou pelo
        # importador padrão com `livro_norm` vazio, e **nenhum filtro de livro a
        # achava** — a ficha existia, abria pelo número, e sumia da busca
        # (relato #55). O importador foi consertado no mesmo dia; isto aqui
        # devolve a vista ao que **já está gravado**, que é o que o balcão
        # procura e não acha.
        #
        #   A régua é uma só, e mora em `importar_padrao.DERIVACOES`: de que
        #   campos cada coluna se compõe e com que função da casa. Escrevê-la de
        #   novo aqui daria duas versões do cálculo que a busca usa — e a
        #   segunda passaria a divergir da primeira sem ninguém ver.
        #
        #   **Não sobrescreve coluna que já tem valor** (divergir da função é
        #   assunto do oficial) e **não inventa valor onde não há fonte**. É
        #   idempotente, como as folhas presas e as sessões interrompidas logo
        #   acima: coluna preenchida não se move de novo. E **não derruba a
        #   subida** — o que ela não conseguir vem no que devolve.
        try:
            import importar_padrao as IMP_PADRAO
            self.colunas_norm_preenchidas = IMP_PADRAO.preencher_colunas_derivadas(con)
        except Exception as erro:                          # noqa: BLE001
            self.colunas_norm_preenchidas = {"erro": str(erro)}
        # The defaults go in only after the whole schema exists.
        for key, value in DEFAULT_SETTINGS.items():
            bd.escrever("INSERT INTO settings(key,value) VALUES (%s,%s) "
                        "ON CONFLICT (key) DO NOTHING", (key, value))
        con.commit()
        con.close()
        self.seed_checklists()

    @staticmethod
    def now() -> str:
        return datetime.now().replace(microsecond=0).strftime(ISO_DT)

    def has_users(self) -> bool:
        with self.connect() as con:
            return banco(con).valor("SELECT COUNT(*) AS n FROM users") > 0

    def validate_password(self, password: str) -> tuple[bool, str]:
        try:
            min_length = int(self.get_setting("password_min_length", "6") or 6)
        except ValueError:
            min_length = 6
        min_length = max(4, min(64, min_length))
        return validate_password_strength(
            password,
            min_length=min_length,
            require_upper=self.get_setting("password_require_upper", "0") == "1",
            require_lower=self.get_setting("password_require_lower", "0") == "1",
            require_digit=self.get_setting("password_require_digit", "0") == "1",
        )

    def create_user(self, username: str, full_name: str, password: str, role: str = "USER", created_by: int | None = None, eh_robo: int = 0) -> int:
        username = username.strip()
        full_name = full_name.strip()
        if not username:
            raise ValueError("Informe o usuário.")
        if not full_name:
            raise ValueError("Informe o nome.")
        eh_robo = 1 if int(eh_robo or 0) else 0
        if (NOMEHUM.eh_rotulo_de_maquina(full_name)
                or NOMEHUM.eh_rotulo_de_maquina(username)
                or "grok" in (username + " " + full_name).casefold()):
            eh_robo = 1
        if not eh_robo and (
                NOMEHUM.eh_rotulo_de_maquina(full_name)
                or NOMEHUM.eh_rotulo_de_maquina(username)):
            raise ValueError(
                "Nome de usuario ou nome completo nao pode ser rotulo de robo "
                "ou maquina — marque a opcao Robo no cadastro.")
        role = role.strip().upper() or "USER"
        if role not in {"ADMIN", "MANAGER", "USER", "AUDITOR"}:
            raise ValueError("Perfil inválido.")
        # ROBÔ NÃO ADMINISTRA (revisão de segurança de 22/10/2026, A6): a
        # credencial dele mora num script; com ADMIN ou MANAGER ela abriria
        # usuários, atualizações, backup e caixa a quem a lesse.
        if eh_robo and role not in {"USER", "AUDITOR"}:
            raise ValueError(
                "Conta de robô só pode ter o perfil USER ou AUDITOR: robô não "
                "administra, não mexe no caixa e não atualiza o sistema.")
        ok, msg = self.validate_password(password)
        if not ok:
            raise ValueError(msg)
        rec = hash_password(password)
        with self.transaction() as con:
            try:
                novo = banco(con).escrever(
                    "INSERT INTO users(username,full_name,password_salt,password_hash,role,active,created_at,created_by,eh_robo) VALUES (%s,%s,%s,%s,%s,1,%s,%s,%s) RETURNING id",
                    (username, full_name, rec.salt_hex, rec.hash_hex, role, self.now(), created_by, eh_robo),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Usuário já existe.") from exc
            uid = int(novo[0]["id"])
        return uid

    def update_user(self, user_id: int, username: str, full_name: str,
                    role: str, eh_robo: int | None = None) -> None:
        """Corrige a identidade do usuário — nome, usuário e perfil.

        Pedido do oficial em 08/09/2026, ao achar o nome do próprio delegatário
        gravado errado (`ri_registrador`) sem tela nenhuma para corrigir: um
        erro de digitação no cadastro do usuário tinha o mesmo problema, e
        `/usuarios` só sabia CRIAR, nunca CORRIGIR o que foi digitado errado.
        """
        username = username.strip()
        full_name = full_name.strip()
        if not username:
            raise ValueError("Informe o usuário.")
        if not full_name:
            raise ValueError("Informe o nome.")
        if eh_robo is None:
            with self.connect() as _c:
                _row = banco(_c).um(
                    "SELECT COALESCE(eh_robo,0) AS eh_robo FROM users WHERE id=%s",
                    (user_id,))
                eh_robo = int((_row["eh_robo"] if _row else 0) or 0)
        else:
            eh_robo = 1 if int(eh_robo or 0) else 0
        if (NOMEHUM.eh_rotulo_de_maquina(full_name)
                or NOMEHUM.eh_rotulo_de_maquina(username)
                or "grok" in (username + " " + full_name).casefold()):
            eh_robo = 1
        role = role.strip().upper() or "USER"
        if role not in {"ADMIN", "MANAGER", "USER", "AUDITOR"}:
            raise ValueError("Perfil inválido.")
        # ROBÔ NÃO ADMINISTRA (revisão de segurança de 22/10/2026, A6): a
        # credencial dele mora num script; com ADMIN ou MANAGER ela abriria
        # usuários, atualizações, backup e caixa a quem a lesse.
        if eh_robo and role not in {"USER", "AUDITOR"}:
            raise ValueError(
                "Conta de robô só pode ter o perfil USER ou AUDITOR: robô não "
                "administra, não mexe no caixa e não atualiza o sistema.")
        with self.transaction() as con:
            try:
                banco(con).escrever(
                    "UPDATE users SET username=%s, full_name=%s, role=%s, eh_robo=%s WHERE id=%s",
                    (username, full_name, role, eh_robo, user_id))
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    "Já existe outro usuário com este nome de usuário."
                ) from exc

    def authenticate(self, username: str, password: str) -> dict | None:
        with self.connect() as con:
            row = banco(con).um(
                "SELECT * FROM users WHERE username = %s COLLATE public.cg_nocase "
                "ORDER BY id LIMIT 1", (username.strip(),))
        if not row or not row["active"]:
            # O MESMO PBKDF2 PARA QUEM NÃO ENTRA (B4 do LS01, lote LX11): sem
            # ele, «usuário não existe» respondia na hora e «senha errada»
            # depois de 310 mil voltas — o relógio dizia quem é cadastrado.
            verify_password(password, *_registro_ficticio())
            return None
        if not verify_password(password, row["password_salt"], row["password_hash"]):
            return None
        return row

    def list_users(self, active_only: bool = False) -> list[dict]:
        # COALESCE porque a coluna e migracao: banco antigo ainda pode nao
        # ter a funcao preenchida, e a tela nao pode quebrar por isso.
        sql = ("SELECT id,username,full_name,role,active,created_at,"
               "COALESCE(funcao,'') funcao,"
               "COALESCE(eh_robo,0) eh_robo, robo_responsavel_id FROM users")
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY full_name COLLATE public.cg_nocase, id"
        with self.connect() as con:
            return banco(con).ler(sql)

    def get_user(self, user_id: int) -> dict | None:
        # A FUNCAO VEM JUNTO, e e o ponto: e ela que sai impressa embaixo da
        # assinatura em todo ato. Faltando aqui, quem monta o ato tinha de ir
        # busca-la por conta propria — e ia pelo NOME, que nao identifica
        # pessoa. COALESCE porque a coluna e migracao: banco antigo pode ainda
        # nao te-la preenchida, e nenhuma tela pode quebrar por isso.
        with self.connect() as con:
            return banco(con).um(
                "SELECT id,username,full_name,role,active,COALESCE(funcao,'') funcao,"
                "COALESCE(eh_robo,0) eh_robo FROM users WHERE id=%s", (user_id,))

    def set_user_active(self, user_id: int, active: bool) -> None:
        with self.transaction() as con:
            banco(con).escrever("UPDATE users SET active=%s WHERE id=%s", (1 if active else 0, user_id))

    def reset_password(self, user_id: int, password: str) -> None:
        ok, msg = self.validate_password(password)
        if not ok:
            raise ValueError(msg)
        rec = hash_password(password)
        with self.transaction() as con:
            banco(con).escrever("UPDATE users SET password_salt=%s,password_hash=%s WHERE id=%s", (rec.salt_hex, rec.hash_hex, user_id))

    def get_setting(self, key: str, default: str = "") -> str:
        with self.connect() as con:
            row = banco(con).um("SELECT value FROM settings WHERE key=%s", (key,))
        return row["value"] if row else default

    def get_settings(self) -> dict[str, str]:
        with self.connect() as con:
            return {r["key"]: r["value"] for r in banco(con).ler("SELECT key,value FROM settings ORDER BY key")}

    def set_settings(self, values: dict[str, str]) -> None:
        with self.transaction() as con:
            bd = banco(con)
            for key, value in values.items():
                bd.escrever("INSERT INTO settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

    def log(self, user_id: int | None, username: str | None, action: str, entity_type: str | None = None, entity_id: int | None = None, details: Any = None, ip_address: str | None = None, *, agente: str | None = None, a_mando_de: str | None = None) -> None:
        # QUEM AGE POR PROGRAMA SE IDENTIFICA (26/10/2026): `agente` e
        # `a_mando_de` sao para quem grava SEM usuario (rotina, agente, script);
        # com usuario de robo, a identidade sai da conta dele. A regra «avisar
        # ou recusar» mora em `identidade_do_robo.decidir`, e so la.
        # entity_id e INTEGER (no PostgreSQL compara-se com id numerico). Chave de
        # TEXTO (ex.: mo_elementos «ato/parte») vai para os detalhes, e a coluna
        # fica vazia - antes ia para a coluna e quebrava as telas (19/10/2026).
        if entity_id is not None and not str(entity_id).strip().lstrip('-').isdigit():
            details = dict(details) if isinstance(details, dict) else ({} if details is None else {'detalhes': details})
            details['entidade'] = str(entity_id)
            entity_id = None
        # CPF E CNPJ NAO FICAM EM CLARO NA AUDITORIA (revisao de seguranca de
        # 22/10/2026, M9): so os campos de documento, pelo nome, e sem cortar
        # nada. O ato guarda o documento inteiro; a auditoria aponta para ele.
        if isinstance(details, (dict, list, tuple)):
            import centrais_log
            details = centrais_log.mascarar_documentos(details)
        payload = json.dumps(details, ensure_ascii=False, default=str) if details is not None else None
        try:
            with self.connect() as con:
                # ESPERA CURTA, DE PROPOSITO.
                #
                # O `busy_timeout` padrao e de dez segundos, e faz sentido para
                # o ato que o balcao esta gravando: melhor esperar do que
                # perder. Para a linha de auditoria e o contrario — ela nao
                # pode fazer o usuario esperar dez segundos por um documento
                # que ja esta pronto. Oitocentos milissegundos absorvem a
                # escrita normal de outro balcao; alem disso, desiste.
                bd = banco(con)
                bd.ler("SET lock_timeout = '800ms'")
                bd._escrita()
                import identidade_do_robo as IDR
                IDR.registrar(bd, ts=self.now(), user_id=user_id, username=username,
                              action=action, entity_type=entity_type,
                              entity_id=entity_id, details=payload,
                              ip_address=ip_address, agente=agente,
                              a_mando_de=a_mando_de)
                con.commit()
        except sqlite3.OperationalError as erro:
            # BANCO TRAVADO POR OUTRO BALCAO.
            #
            # Auditoria e escrita curta, mas ela abre `BEGIN IMMEDIATE` como
            # qualquer outra: com outro balcao dentro de uma transacao longa,
            # esta linha esperava os dez segundos do `busy_timeout` e subia,
            # derrubando a requisicao inteira. Era o que fazia a rota do
            # TRASLADO — uma leitura — devolver HTTP 500, e nenhuma outra tela
            # de leitura fazia mais isso.
            #
            # A troca e consciente e nao e confortavel: o traslado sai e a
            # linha de auditoria nao entra na tabela. Ela nao se perde — vai
            # para o log do servidor, com o mesmo conteudo, no nivel ERROR.
            # Entre entregar o documento sem a linha de auditoria e nao
            # entregar documento nenhum, a serventia precisa do documento.
            #
            # MAS NAO CRU (LX14; M9 do LS03). O detalhe da auditoria traz teor
            # de ato, CPF e nome da lista de fraude, e o `servidor.log` e lido
            # por quem nao le a auditoria. Vai pela mesma mascara do log das
            # Centrais: CPF/CNPJ com os dois ultimos digitos, chave de segredo
            # «omitido», texto cortado em 500 caracteres.
            import centrais_log
            logging.getLogger("cartorio.auditoria").error(
                "AUDITORIA NAO GRAVADA (%s): %s user=%s agente=%s a_mando_de=%s acao=%s %s#%s %s",
                type(erro).__name__, erro, username, agente, a_mando_de, action, entity_type,
                entity_id, json.dumps(centrais_log.sanitizar(details),
                                      ensure_ascii=False, default=str)
                if details is not None else None)

    def list_logs(self, limit: int = 1000) -> list[dict]:
        with self.connect() as con:
            return banco(con).ler("SELECT * FROM audit_logs ORDER BY id DESC LIMIT %s", (limit,))

    def next_protocol(self, con: Any = None) -> str:
        owns = con is None
        con = con or self.connect()
        try:
            year = date.today().year
            prefix = f"EXP-{year}-"
            row = banco(con).um("SELECT internal_protocol FROM expedientes WHERE internal_protocol ILIKE %s ORDER BY id DESC LIMIT 1", (prefix + "%",))
            n = 1
            if row and row["internal_protocol"]:
                try:
                    n = int(row["internal_protocol"].split("-")[-1]) + 1
                except Exception:
                    pass
            return f"{prefix}{n:06d}"
        finally:
            if owns:
                con.close()

    def create_expediente(self, data: dict[str, Any], user_id: int) -> int:
        now = self.now()
        with self.transaction() as con:
            bd = banco(con)
            bd.travar("expedientes.internal_protocol")
            protocol = self.next_protocol(con)
            novo = bd.escrever(
                """INSERT INTO expedientes(
                    internal_protocol,source,external_reference,sender,subject,category,sector,received_at,
                    deadline_start,deadline_days,deadline_date,priority,assigned_user_id,backup_user_id,stage,
                    notes,created_by,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (
                    protocol, data.get("source") or "Outro", data.get("external_reference"), data.get("sender"),
                    data.get("subject") or "Sem assunto", data.get("category") or "Outros", data.get("sector"),
                    data.get("received_at") or date.today().isoformat(), data.get("deadline_start"), data.get("deadline_days"),
                    data.get("deadline_date"), data.get("priority") or "MEDIA", data.get("assigned_user_id"),
                    data.get("backup_user_id"), data.get("stage") or "RECEBIDO", data.get("notes"), user_id, now, now,
                ),
            )
            return int(novo[0]["id"])

    def update_expediente_stage(self, expediente_id: int, stage: str, user_id: int, response_reference: str | None = None) -> None:
        now = self.now()
        # A mesma régua da lista dos abertos e do contador (problema #96).
        completed = now if EXPT.esta_encerrado(stage) else None
        with self.transaction() as con:
            banco(con).escrever(
                "UPDATE expedientes SET stage=%s, response_reference=COALESCE(%s,response_reference), responded_at=CASE WHEN %s='RESPONDIDO' THEN %s ELSE responded_at END, completed_at=%s, completed_by=CASE WHEN %s IS NOT NULL THEN %s ELSE completed_by END, updated_at=%s WHERE id=%s",
                (stage, response_reference, stage, now, completed, completed, user_id, now, expediente_id),
            )

    def list_expedientes(self, limit: int = 500, only_open: bool = False,
                         busca: str | None = None) -> list[dict]:
        # «ABERTO» É O QUE AINDA NÃO ENCERROU, e quem diz o que encerra é
        # `expediente_tarefa.ETAPAS_QUE_ENCERRAM` - problema #96, 23/09/2026.
        # Aqui estava escrito à mão `NOT IN ('ARQUIVADO')`, a metade da regra:
        # o expediente RESPONDIDO, que a ficha dá por encerrado (e que tem
        # `completed_at`), continuava no painel como «em andamento», e quem o
        # abria não achava como encerrar o que já estava encerrado.
        #
        # Busca (07/10/2026, Beatriz): um único campo no Malote procura o nº
        # do ofício (external_reference / response_reference), o protocolo
        # interno, o assunto/descrição, o remetente e as observações — quem
        # está no balcão digita o que tem na mão.
        encerram = EXPT.ETAPAS_QUE_ENCERRAM
        clauses: list[str] = []
        params: list = []
        if only_open:
            clauses.append(
                f"e.stage NOT IN ({', '.join(['%s'] * len(encerram))})"
            )
            params.extend(encerram)
        texto = (busca or "").strip()
        if texto:
            like = f"%{texto}%"
            clauses.append(
                "(coalesce(e.external_reference,'') ILIKE %s"
                " OR coalesce(e.subject,'') ILIKE %s"
                " OR coalesce(e.notes,'') ILIKE %s"
                " OR coalesce(e.sender,'') ILIKE %s"
                " OR coalesce(e.internal_protocol,'') ILIKE %s"
                " OR coalesce(e.response_reference,'') ILIKE %s)"
            )
            params.extend([like] * 6)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with self.connect() as con:
            return banco(con).ler(
                f"""SELECT e.*, u.full_name assigned_name, b.full_name backup_name
                FROM expedientes e LEFT JOIN users u ON u.id=e.assigned_user_id LEFT JOIN users b ON b.id=e.backup_user_id
                {where} ORDER BY CASE WHEN e.deadline_date IS NULL THEN 1 ELSE 0 END, e.deadline_date, e.id DESC LIMIT %s""",
                params,
            )
    def get_expediente(self, expediente_id: int) -> dict | None:
        with self.connect() as con:
            return banco(con).um(
                """SELECT e.*, u.full_name assigned_name, b.full_name backup_name, c.full_name creator_name
                FROM expedientes e LEFT JOIN users u ON u.id=e.assigned_user_id LEFT JOIN users b ON b.id=e.backup_user_id LEFT JOIN users c ON c.id=e.created_by WHERE e.id=%s""",
                (expediente_id,),
            )

    def create_task(self, data: dict[str, Any], user_id: int | None) -> int:
        now = self.now()
        with self.transaction() as con:
            # TAREFA IGUAL NÃO NASCE DE NOVO (ordem do oficial, 12/10/2026:
            # «precisamos evitar tarefas repetidas»). Se já há uma ABERTA com o
            # mesmo título, o mesmo responsável e a mesma referência, o pedido
            # vira uma nota nela, e devolve-se o número da que já existe.
            import carga_da_equipe as CARGA
            bd = banco(con)
            existente = CARGA.tarefa_igual_aberta(con, data)
            if existente:
                bd.escrever("INSERT INTO task_history(task_id,ts,user_id,action,new_value,note) VALUES (%s,%s,%s,%s,%s,%s)",
                            (existente, now, user_id, "NOTA", None,
                             "Pedido repetido de criação desta mesma tarefa — não se abriu outra."))
                return existente
            novo = bd.escrever(
                """INSERT INTO tasks(source_type,source_ref,inspection_id,recurrence_id,title,description,sector,system_name,priority,status,
                due_days,start_date,due_date,assigned_user_id,backup_user_id,linked_expediente_id,evidence_required,source_page,legal_ref,created_by,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (
                    data.get("source_type") or "MANUAL", data.get("source_ref"), data.get("inspection_id"), data.get("recurrence_id"),
                    data.get("title"), data.get("description"), data.get("sector"), data.get("system_name"), data.get("priority") or "MEDIA",
                    data.get("status") or "ABERTA", data.get("due_days"), data.get("start_date"), data.get("due_date"), data.get("assigned_user_id"),
                    data.get("backup_user_id"), data.get("linked_expediente_id"), int(data.get("evidence_required", 0)), data.get("source_page"), data.get("legal_ref"),
                    user_id, now, now,
                ),
            )
            task_id = int(novo[0]["id"])
            bd.escrever("INSERT INTO task_history(task_id,ts,user_id,action,new_value,note) VALUES (%s,%s,%s,%s,%s,%s)", (task_id, now, user_id, "CRIADA", data.get("status") or "ABERTA", data.get("description")))
            return task_id

    def list_tasks(self, status: str | None = None, sector: str | None = None, limit: int = 1000, usuario_id: int | None = None,
                   filtros: dict | None = None, busca: str | None = None) -> list[dict]:
        # AS VISTAS SAO DO RELATO #59 — o oficial pediu que a tarefa funcione
        # como processo, com transito de responsabilidade:
        #
        #   «permitir um sistema de processamento e transito de responsabilidades
        #    durante a tarefa»
        #
        # «Comigo» e «passou por mim» sao as duas perguntas que quem trabalha no
        # balcao faz — o que esta na minha mao, e o que saiu dela e continua
        # andando. A REGUA MORA EM `tarefa_processo`, e nao aqui: a tela oferece
        # as vistas e esta lista as monta, e duas versoes do mesmo WHERE
        # divergiriam no primeiro conserto.
        filters, params = TP.filtro_da_vista(status, usuario_id)
        filters = [_pg(f) for f in filters]
        if sector:
            filters.append("t.sector=%s")
            params.append(sector)
        # OS FILTROS E AS ORDENS DE 13/10/2026 — «quero todas opções». A régua
        # é a de Processos (`tarefa_ordem`): as duas telas respondem igual.
        import tarefa_ordem as TO
        filtros = dict(filtros or {})
        andamento = "COALESCE((SELECT MAX(h.ts) FROM task_history h WHERE h.task_id = t.id), t.created_at)"
        if filtros:
            from datetime import date as _date
            cond_aberta, args_aberta = TP.condicao_aberta("t.status")
            conds, args = TO.filtros_sql(filtros, hoje=_date.today(), cond_aberta=cond_aberta,
                                         args_aberta=list(args_aberta), andamento=andamento)
            filters += [_pg(c) for c in conds]
            params += args
        # A BUSCA POR TEXTO — relato #122, 07/10/2026: número, título,
        # descrição e responsável, pela régua que Processos também usa.
        conds, args = TO.busca_sql(busca, responsavel="u.full_name")
        # O `LIKE` que a régua entrega é o do SQLite, que não liga para caixa;
        # nativo, é `ILIKE` (o mesmo que `processos.py` faz com o mesmo pedaço).
        filters += [_pg(c).replace(" LIKE ", " ILIKE ") for c in conds]
        params += args
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        # A ORDEM usa a MESMA lista de situacoes em aberto da vista. Escrita a
        # mao aqui, ela envelheceria sozinha no dia em que a sexta situacao
        # nascesse, e a palavra desconhecida subiria para o topo da lista como
        # se fosse servico a fazer — o palpite que a vista «Em aberto» recusa.
        marcadores_abertas = ",".join(["%s"] * len(TP.SITUACOES_ABERTAS))
        ordenacao = [*TP.SITUACOES_ABERTAS, limit]
        # SEM ORDEM ESCOLHIDA, a de sempre (abertas, prioridade, prazo); COM
        # ordem, a da régua — e as abertas continuam antes das encerradas só
        # quando ninguém pediu outra coisa.
        if filtros.get("ordem"):
            ordem_sql = _pg(TO.ordem_sql(filtros.get("ordem"), filtros.get("inverter"),
                                         responsavel="u.full_name", andamento="ultimo_andamento", tipo=None))
            ordenacao = [limit]
        else:
            ordem_sql = None
        with self.connect() as con:
            return banco(con).ler(
                f"""SELECT t.*, u.full_name assigned_name, b.full_name backup_name,
                (SELECT COUNT(*) FROM attachments a WHERE a.entity_type='TASK' AND a.entity_id=t.id) evidence_count,
                COALESCE((SELECT MAX(h.ts) FROM task_history h WHERE h.task_id = t.id), t.created_at) ultimo_andamento
                FROM tasks t LEFT JOIN users u ON u.id=t.assigned_user_id LEFT JOIN users b ON b.id=t.backup_user_id
                {where}
                ORDER BY {ordem_sql or f'''CASE WHEN t.status IN ({marcadores_abertas}) THEN 0 ELSE 1 END,
                         CASE t.priority WHEN 'CRITICA' THEN 0 WHEN 'ALTA' THEN 1 WHEN 'MEDIA' THEN 2 ELSE 3 END,
                         CASE WHEN t.due_date IS NULL THEN 1 ELSE 0 END, t.due_date, t.id DESC'''} LIMIT %s""",
                [*params, *ordenacao],
            )

    def get_task(self, task_id: int) -> dict | None:
        with self.connect() as con:
            return banco(con).um(
                """SELECT t.*, u.full_name assigned_name, b.full_name backup_name, c.full_name creator_name
                FROM tasks t LEFT JOIN users u ON u.id=t.assigned_user_id LEFT JOIN users b ON b.id=t.backup_user_id LEFT JOIN users c ON c.id=t.created_by WHERE t.id=%s""",
                (task_id,),
            )

    @staticmethod
    def _texto_do_historico(con: Any, coluna: str, valor: Any) -> str | None:
        """O que vai para a linha do tempo: NOME, quando a coluna guarda pessoa.

        Ate 17/09/2026 o historico gravava `str(user_id)` em toda coluna, e a
        ficha mostrava «5 -> 2» onde a pergunta do balcao e «passou para quem?».
        Medido na producao antes do conserto: zero linhas assim — o defeito era
        latente, e a passagem de responsabilidade do relato #59 o alcancaria no
        primeiro uso. Se a pessoa nao existir mais, fica o numero: numero e
        pior que nome, e melhor que nada, porque e um fato.
        """
        if valor is None:
            return None
        if coluna.upper() in TP.COLUNAS_DE_PESSOA:
            try:
                return TP.nome_do_usuario(con, int(valor)) or str(valor)
            except (TypeError, ValueError):
                return str(valor)
        return str(valor)

    def update_task(self, task_id: int, fields: dict[str, Any], user_id: int) -> None:
        allowed = {"title","description","sector","system_name","priority","status","due_days","start_date","due_date","assigned_user_id","backup_user_id","evidence_required","legal_ref"}
        updates = []
        params: list[Any] = []
        with self.transaction() as con:
            bd = banco(con)
            # Lê e grava a mesma linha: a tarefa fica presa até o fim.
            bd._escrita()
            old = bd.um("SELECT * FROM tasks WHERE id=%s FOR UPDATE", (task_id,))
            if not old:
                raise ValueError("Tarefa não encontrada.")
            for k, v in fields.items():
                if k not in allowed:
                    continue
                if old[k] != v:
                    updates.append(f"{k}=%s")
                    params.append(v)
                    bd.escrever(
                        "INSERT INTO task_history(task_id,ts,user_id,action,old_value,new_value) VALUES (%s,%s,%s,%s,%s,%s)",
                        (task_id, self.now(), user_id, f"ALTEROU_{k.upper()}",
                         self._texto_do_historico(con, k, old[k]),
                         self._texto_do_historico(con, k, v)))
            if not updates:
                return
            now = self.now()
            updates.append("updated_at=%s")
            params.append(now)
            # O CARIMBO DE CONCLUSAO E DE QUEM CONCLUIU — e so disso. Ate
            # 17/09/2026 bastava a situacao INFORMADA ser `CONCLUIDA` para o
            # carimbo ser reescrito com a hora da gravacao: quem corrigisse uma
            # virgula no titulo de uma tarefa concluida em marco via o carimbo
            # pular para setembro, e a ficha afirmava que o servico terminou no
            # dia da correcao. Medido nas cinco concluidas da producao: nas
            # cinco a ultima edicao foi a propria conclusao, de modo que o
            # defeito nao aparece no dado — ele aparece no codigo, e ha teste
            # que edita o titulo de uma concluida e confere que o carimbo fica.
            situacao = fields.get("status")
            if situacao is None:
                # Nao se mexeu na situacao: o carimbo fica como esta.
                pass
            elif TP.carimba_o_status(situacao) and not TP.carimba_o_status(old["status"]):
                updates += ["completed_at=%s", "completed_by=%s"]
                params += [now, user_id]
            elif not TP.carimba_o_status(situacao):
                # Qualquer outra situacao nao tem carimbo — inclusive as que a
                # tela oferece. Carimbo que fica depois de a tarefa voltar a
                # andar mente sobre o dia em que o servico terminou.
                updates += ["completed_at=NULL", "completed_by=NULL"]
            params.append(task_id)
            bd.escrever(f"UPDATE tasks SET {', '.join(updates)} WHERE id=%s", params)
            # A SUSPENSÃO ACOMPANHA A TAREFA — relato #132. Concluir ou cancelar
            # encerra a suspensão junto; mudar o vencimento à mão durante ela
            # move também o vencimento de antes, de onde a retomada recalcula —
            # senão retomar desfaria a correção de quem editou.
            if situacao is not None and not TP.tem_servico_em_andamento(situacao):
                TS.encerrar_pelo_fim_da_tarefa(con, task_id, situacao, user_id, now)
            elif "due_date" in fields and old["due_date"] != fields["due_date"]:
                TS.vencimento_editado(con, task_id, old["due_date"], fields["due_date"])

    def add_task_note(self, task_id: int, user_id: int, note: str, tipo: str | None = None) -> None:
        """Registra andamento (NOTA). `tipo` vai em new_value (código TIPOS_ANDAMENTO)."""
        codigo = TP.normalizar_tipo_andamento(tipo)
        with self.transaction() as con:
            banco(con).escrever(
                "INSERT INTO task_history(task_id,ts,user_id,action,new_value,note) VALUES (%s,%s,%s,%s,%s,%s)",
                (task_id, self.now(), user_id, "NOTA", codigo, note),
            )

    def task_history(self, task_id: int) -> list[dict]:
        with self.connect() as con:
            return banco(con).ler("SELECT h.*,u.full_name FROM task_history h LEFT JOIN users u ON u.id=h.user_id WHERE task_id=%s ORDER BY h.id DESC", (task_id,))

    def add_attachment(self, entity_type: str, entity_id: int, fileinfo: dict[str, Any], user_id: int, description: str | None = None) -> int:
        with self.transaction() as con:
            novo = banco(con).escrever(
                "INSERT INTO attachments(entity_type,entity_id,original_name,stored_name,stored_path,sha256,size_bytes,description,uploaded_by,uploaded_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (entity_type, entity_id, fileinfo["original_name"], fileinfo["stored_name"], fileinfo["stored_path"], fileinfo["sha256"], fileinfo["size_bytes"], description, user_id, self.now()),
            )
            return int(novo[0]["id"])

    def get_attachments(self, entity_type: str, entity_id: int) -> list[dict]:
        with self.connect() as con:
            return banco(con).ler("SELECT a.*,u.full_name uploader_name FROM attachments a LEFT JOIN users u ON u.id=a.uploaded_by WHERE entity_type=%s AND entity_id=%s ORDER BY a.id DESC", (entity_type, entity_id))

    def get_attachment(self, attachment_id: int) -> dict | None:
        with self.connect() as con:
            return banco(con).um("SELECT * FROM attachments WHERE id=%s", (attachment_id,))

    def delete_attachment(self, attachment_id: int) -> dict | None:
        """Retira o vinculo do arquivo. O binario no disco permanece."""
        with self.transaction() as con:
            bd = banco(con)
            row = bd.um(
                "SELECT * FROM attachments WHERE id=%s", (attachment_id,)
            )
            if not row:
                return None
            bd.escrever("DELETE FROM attachments WHERE id=%s", (attachment_id,))
            return row


    def seed_inspection(self) -> int:
        """O plano de ação da inspeção, se esta instalação tiver o relatório.
        Sem ele devolve 0 e não grava nada."""
        if not REPORT_TITLE:
            return 0
        with self.transaction() as con:
            bd = banco(con)
            existing = bd.um("SELECT id FROM inspections WHERE title=%s ORDER BY id LIMIT 1", (REPORT_TITLE,))
            if existing:
                return int(existing["id"])
            novo = bd.escrever("INSERT INTO inspections(title,report_date,source_filename,active,notes,created_at) VALUES (%s,%s,%s,1,%s,%s) RETURNING id", (REPORT_TITLE, REPORT_DATE, REPORT_SOURCE, "Importado do relatório preliminar. Defina a data-base de ciência antes de calcular vencimentos.", self.now()))
            inspection_id = int(novo[0]["id"])
            now = self.now()
            for item in RECOMMENDATIONS:
                bd.escrever(
                    """INSERT INTO tasks(source_type,source_ref,inspection_id,title,description,sector,system_name,priority,status,due_days,evidence_required,source_page,created_at,updated_at)
                    VALUES ('INSPECAO',%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s)""",
                    (REPORT_SOURCE, inspection_id, item["title"], item.get("description"), item.get("sector"), item.get("system_name"), item.get("priority","ALTA"), "ABERTA", item.get("due_days"), item.get("page"), now, now),
                )
            return inspection_id

    def list_inspections(self) -> list[dict]:
        with self.connect() as con:
            # 13/10/2026: a tarefa CANCELADA sai do total. Na revisão aprovada pelo
            # oficial, recomendações repetidas foram juntadas numa tarefa só, e a
            # juntada (cancelada) deixaria a barra da inspeção presa abaixo de 100%.
            return banco(con).ler("SELECT i.*, (SELECT COUNT(*) FROM tasks t WHERE t.inspection_id=i.id AND t.status <> 'CANCELADA') total_tasks, (SELECT COUNT(*) FROM tasks t WHERE t.inspection_id=i.id AND t.status='CONCLUIDA') done_tasks FROM inspections i ORDER BY i.id DESC")

    def get_inspection(self, inspection_id: int) -> dict | None:
        with self.connect() as con:
            return banco(con).um("SELECT * FROM inspections WHERE id=%s", (inspection_id,))

    def set_inspection_start_date(self, inspection_id: int, start_date: str, user_id: int) -> None:
        base = date.fromisoformat(start_date)
        with self.transaction() as con:
            bd = banco(con)
            bd.escrever("UPDATE inspections SET start_date=%s WHERE id=%s", (start_date, inspection_id))
            rows = bd.ler("SELECT id,due_days FROM tasks WHERE inspection_id=%s AND status NOT IN ('CONCLUIDA','CANCELADA') ORDER BY id", (inspection_id,))
            for r in rows:
                days = r["due_days"]
                due = (base + timedelta(days=int(days or 0))).isoformat()
                bd.escrever("UPDATE tasks SET start_date=%s,due_date=%s,updated_at=%s WHERE id=%s", (start_date, due, self.now(), r["id"]))
                bd.escrever("INSERT INTO task_history(task_id,ts,user_id,action,new_value,note) VALUES (%s,%s,%s,%s,%s,%s)", (r["id"], self.now(), user_id, "PRAZO_CALCULADO", due, f"Data-base da inspeção: {start_date}"))

    def bulk_assign_inspection_tasks(self, inspection_id: int, sector: str, assigned_user_id: int | None, backup_user_id: int | None, user_id: int) -> int:
        with self.transaction() as con:
            bd = banco(con)
            rows = bd.ler("SELECT id FROM tasks WHERE inspection_id=%s AND sector=%s AND status NOT IN ('CONCLUIDA','CANCELADA') ORDER BY id", (inspection_id, sector))
            now = self.now()
            for r in rows:
                bd.escrever("UPDATE tasks SET assigned_user_id=%s,backup_user_id=%s,updated_at=%s WHERE id=%s", (assigned_user_id, backup_user_id, now, r["id"]))
                # NOMES, E NAO NUMEROS: quem abre a ficha meses depois pergunta
                # «passou para quem?», e «4» nao responde. Ver o relato #59.
                para = TP.nome_do_usuario(con, assigned_user_id) or (
                    f"#{assigned_user_id}" if assigned_user_id else "ninguém")
                substituto = TP.nome_do_usuario(con, backup_user_id) or (
                    f"#{backup_user_id}" if backup_user_id else "não definido")
                bd.escrever("INSERT INTO task_history(task_id,ts,user_id,action,new_value,note) VALUES (%s,%s,%s,%s,%s,%s)", (r["id"], now, user_id, "ATRIBUICAO_EM_LOTE", para, f"Setor {sector}; substituto {substituto}"))
            return len(rows)

    def ensure_overdue_escalations(self, today: date | None = None) -> int:
        today = today or date.today()
        # A SUSPENSA NÃO SE ESCALONA — relato #132: enquanto ela espera o
        # cliente (ou a data), o substituto não tem o que regularizar.
        nao_suspensa, params_suspensao = TS.condicao_nao_suspensa(None, today)
        with self.transaction() as con:
            bd = banco(con)
            rows = bd.ler(f"SELECT id,due_date,backup_user_id FROM tasks WHERE status NOT IN ('CONCLUIDA','CANCELADA') AND due_date IS NOT NULL AND due_date < %s AND backup_user_id IS NOT NULL AND {_pg(nao_suspensa)} ORDER BY id", (today.isoformat(), *params_suspensao))
            count = 0
            for r in rows:
                key = f"vencimento:{r['due_date']}"
                exists = bd.um("SELECT 1 AS ha FROM task_history WHERE task_id=%s AND action='ESCALONAMENTO_AUTOMATICO' AND new_value=%s LIMIT 1", (r["id"], key))
                if exists:
                    continue
                # O NOME DO SUBSTITUTO, E NAO O NUMERO. Medido em 17/09/2026: as
                # **13** linhas de escalonamento da producao diziam «Responsável
                # substituto #2 deve acompanhar a regularização» — numero que o
                # escrevente le na ficha e nao sabe de quem e. As treze ficam
                # como estao: fato do passado nao se regrava.
                substituto = TP.nome_do_usuario(con, r["backup_user_id"]) or f"#{r['backup_user_id']}"
                bd.escrever("INSERT INTO task_history(task_id,ts,user_id,action,new_value,note) VALUES (%s,%s,NULL,'ESCALONAMENTO_AUTOMATICO',%s,%s)", (r["id"], self.now(), key, f"Tarefa vencida. Responsável substituto {substituto} deve acompanhar a regularização."))
                count += 1
            return count

    def encerrar_suspensoes_vencidas(self, today: date | None = None) -> int:
        """A volta automática das suspensões por prazo — relato #132.

        A cobrança já volta sozinha no dia, na leitura; esta passada da
        manutenção diária só escreve o rastro («retomada automática») e limpa
        as colunas. Idempotente."""
        with self.transaction() as con:
            return TS.encerrar_as_vencidas(con, agora=self.now(), hoje=today)

    def create_recurrence(self, data: dict[str, Any], user_id: int) -> int:
        now = self.now()
        with self.transaction() as con:
            novo = banco(con).escrever(
                """INSERT INTO recurring_obligations(title,system_name,sector,frequency,due_day,due_month,lead_days,assigned_user_id,backup_user_id,active,next_due_date,evidence_required,notes,created_by,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (data["title"], data.get("system_name"), data.get("sector"), data.get("frequency","MONTHLY"), data.get("due_day"), data.get("due_month"), data.get("lead_days",5), data.get("assigned_user_id"), data.get("backup_user_id"), data.get("next_due_date"), int(data.get("evidence_required",0)), data.get("notes"), user_id, now, now),
            )
            return int(novo[0]["id"])

    def get_recurrence(self, recurrence_id: int) -> dict | None:
        with self.connect() as con:
            return banco(con).um("SELECT * FROM recurring_obligations WHERE id=%s", (recurrence_id,))

    def update_recurrence(self, recurrence_id: int, data: dict[str, Any]) -> None:
        with self.transaction() as con:
            banco(con).escrever("""UPDATE recurring_obligations SET title=%s,system_name=%s,sector=%s,frequency=%s,due_day=%s,due_month=%s,lead_days=%s,assigned_user_id=%s,backup_user_id=%s,active=%s,next_due_date=%s,evidence_required=%s,notes=%s,updated_at=%s WHERE id=%s""",
                (data.get("title"),data.get("system_name"),data.get("sector"),data.get("frequency"),data.get("due_day"),data.get("due_month"),data.get("lead_days",5),data.get("assigned_user_id"),data.get("backup_user_id"),int(data.get("active",1)),data.get("next_due_date"),int(data.get("evidence_required",0)),data.get("notes"),self.now(),recurrence_id))

    def list_recurrences(self) -> list[dict]:
        with self.connect() as con:
            return banco(con).ler("SELECT r.*,u.full_name assigned_name,b.full_name backup_name FROM recurring_obligations r LEFT JOIN users u ON u.id=r.assigned_user_id LEFT JOIN users b ON b.id=r.backup_user_id ORDER BY r.active DESC,r.next_due_date NULLS FIRST,r.title,r.id")

    def ensure_recurring_tasks(self, today: date | None = None) -> int:
        today = today or date.today()
        created = 0
        with self.transaction() as con:
            bd = banco(con)
            rows = bd.ler("SELECT * FROM recurring_obligations WHERE active=1 AND next_due_date IS NOT NULL ORDER BY id")
            for r in rows:
                due = date.fromisoformat(r["next_due_date"])
                lead = int(r["lead_days"] or 0)
                if today < due - timedelta(days=lead):
                    continue
                key = f"{r['id']}:{due.isoformat()}"
                exists = bd.um("SELECT id FROM tasks WHERE source_type='RECORRENTE' AND source_ref=%s ORDER BY id LIMIT 1", (key,))
                if not exists:
                    now = self.now()
                    bd.escrever(
                        """INSERT INTO tasks(source_type,source_ref,recurrence_id,title,description,sector,system_name,priority,status,start_date,due_date,assigned_user_id,backup_user_id,evidence_required,created_at,updated_at)
                        VALUES ('RECORRENTE',%s,%s,%s,%s,%s,%s,'ALTA','ABERTA',%s,%s,%s,%s,%s,%s,%s)""",
                        (key, r["id"], r["title"], r["notes"], r["sector"], r["system_name"], today.isoformat(), due.isoformat(), r["assigned_user_id"], r["backup_user_id"], r["evidence_required"], now, now),
                    )
                    created += 1
                next_due = self._next_due(due, r["frequency"], r["due_day"], r["due_month"])
                bd.escrever("UPDATE recurring_obligations SET next_due_date=%s,updated_at=%s WHERE id=%s", (next_due.isoformat(), self.now(), r["id"]))
        return created

    @staticmethod
    def _next_due(current: date, frequency: str, due_day: int | None, due_month: int | None) -> date:
        f = (frequency or "MONTHLY").upper()
        if f == "DAILY":
            return current + timedelta(days=1)
        if f == "WEEKLY":
            return current + timedelta(days=7)
        if f == "MONTHLY":
            y, m = current.year, current.month + 1
            if m == 13: y, m = y + 1, 1
            d = min(int(due_day or current.day), _last_day(y, m))
            return date(y, m, d)
        if f == "QUARTERLY":
            months = 3
        elif f == "SEMIANNUAL":
            months = 6
        else:
            months = 12
        y = current.year + (current.month - 1 + months) // 12
        m = (current.month - 1 + months) % 12 + 1
        if f == "ANNUAL" and due_month:
            m = int(due_month)
            y = current.year + 1
        d = min(int(due_day or current.day), _last_day(y, m))
        return date(y, m, d)

    def seed_checklists(self) -> None:
        templates = {
            "Checklist diário - Malote e expedientes": ("Gestão", [
                "Acessar as vias oficiais de entrada e verificar novas comunicações",
                "Cadastrar todos os expedientes recebidos no sistema",
                "Definir responsável e substituto quando houver diligência",
                "Conferir prazos e pendências críticas do dia",
                "Confirmar que não há documento recebido sem triagem",
            ]),
            "Checklist de Protesto - antes da conclusão": ("Protesto", [
                "Protocolização e ordem cronológica conferidas",
                "Prazo do tríduo calculado e conferido",
                "Intimação realizada dentro do prazo e na forma adequada",
                "Motivo/tipo do protesto corretamente indicado",
                "Pagamentos/ocorrências registrados no Livro de Protocolo",
                "Selos, emolumentos e demais dados obrigatórios conferidos",
            ]),
            "Checklist de Notas - antes da conclusão": ("Notas", [
                "Número do termo e ordem conferidos",
                "Item da tabela de emolumentos indicado",
                "Selos e selos de arquivamento conferidos",
                "Emolumentos e fundos discriminados",
                "QR Codes/informações dos selos incluídos quando aplicável",
                "Documentos instrutórios arquivados e vinculados",
            ]),
            "Checklist RCPN - antes da conclusão": ("RCPN", [
                "Assinaturas obrigatórias conferidas",
                "Gratuidade/isencão registrada quando aplicável",
                "Categoria do selo eletrônico conferida",
                "Emolumentos e destinações legais registrados",
                "Notas/averbações/retificações possuem espaço próprio",
                "Procedimentos especiais, inclusive paternidade, verificados",
            ]),
        }
        with self.transaction() as con:
            bd = banco(con)
            for name, (sector, items) in templates.items():
                row = bd.um("SELECT id FROM checklist_templates WHERE name=%s", (name,))
                if row:
                    continue
                novo = bd.escrever("INSERT INTO checklist_templates(name,sector,active,created_at) VALUES (%s,%s,1,%s) RETURNING id", (name, sector, self.now()))
                tid = int(novo[0]["id"])
                for pos, text in enumerate(items, 1):
                    bd.escrever("INSERT INTO checklist_items(template_id,position,text,required) VALUES (%s,%s,%s,1)", (tid, pos, text))


    def create_checklist_template(self, name: str, sector: str | None, items: list[str]) -> int:
        name = name.strip()
        clean_items = [x.strip() for x in items if x.strip()]
        if not name or not clean_items:
            raise ValueError("Informe o nome e ao menos um item do checklist.")
        with self.transaction() as con:
            bd = banco(con)
            try:
                novo = bd.escrever("INSERT INTO checklist_templates(name,sector,active,created_at) VALUES (%s,%s,1,%s) RETURNING id", (name, sector, self.now()))
            except sqlite3.IntegrityError as exc:
                raise ValueError("Já existe um checklist com esse nome.") from exc
            tid = int(novo[0]["id"])
            for pos, text in enumerate(clean_items, 1):
                bd.escrever("INSERT INTO checklist_items(template_id,position,text,required) VALUES (%s,%s,%s,1)", (tid, pos, text))
            return tid

    def list_checklist_templates(self) -> list[dict]:
        with self.connect() as con:
            return banco(con).ler("SELECT t.*, (SELECT COUNT(*) FROM checklist_items i WHERE i.template_id=t.id) item_count FROM checklist_templates t WHERE active=1 ORDER BY t.sector NULLS FIRST,t.name,t.id")

    def start_checklist(self, template_id: int, reference: str, user_id: int) -> int:
        with self.transaction() as con:
            bd = banco(con)
            novo = bd.escrever("INSERT INTO checklist_runs(template_id,reference,run_date,user_id,status) VALUES (%s,%s,%s,%s, 'ABERTO') RETURNING id", (template_id, reference, self.now(), user_id))
            run_id = int(novo[0]["id"])
            items = bd.ler("SELECT id FROM checklist_items WHERE template_id=%s ORDER BY position, id", (template_id,))
            for item in items:
                bd.escrever("INSERT INTO checklist_run_items(run_id,item_id,checked) VALUES (%s,%s,0)", (run_id, item["id"]))
            return run_id

    def get_checklist_run(self, run_id: int) -> tuple[dict | None, list[dict]]:
        with self.connect() as con:
            bd = banco(con)
            run = bd.um("SELECT r.*,t.name template_name,t.sector,u.full_name user_name FROM checklist_runs r JOIN checklist_templates t ON t.id=r.template_id JOIN users u ON u.id=r.user_id WHERE r.id=%s", (run_id,))
            items = bd.ler("SELECT ri.*,i.text,i.required FROM checklist_run_items ri JOIN checklist_items i ON i.id=ri.item_id WHERE ri.run_id=%s ORDER BY i.position, ri.id", (run_id,))
            return run, items

    def save_checklist_run(self, run_id: int, checked_ids: set[int], notes: dict[int, str], finish: bool) -> None:
        with self.transaction() as con:
            bd = banco(con)
            rows = bd.ler("SELECT id FROM checklist_run_items WHERE run_id=%s ORDER BY id", (run_id,))
            for r in rows:
                rid = int(r["id"])
                bd.escrever("UPDATE checklist_run_items SET checked=%s,note=%s WHERE id=%s", (1 if rid in checked_ids else 0, notes.get(rid), rid))
            if finish:
                required_missing = bd.valor("SELECT COUNT(*) AS n FROM checklist_run_items ri JOIN checklist_items i ON i.id=ri.item_id WHERE ri.run_id=%s AND i.required=1 AND ri.checked=0", (run_id,))
                if required_missing:
                    raise ValueError("Há itens obrigatórios não conferidos.")
                bd.escrever("UPDATE checklist_runs SET status='CONCLUIDO',completed_at=%s WHERE id=%s", (self.now(), run_id))

    def create_asset(self, data: dict[str, Any], user_id: int) -> int:
        now = self.now()
        with self.transaction() as con:
            novo = banco(con).escrever("INSERT INTO assets(kind,name,identifier,location,responsible_user_id,status,expiry_date,last_check_date,notes,created_by,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id", (data.get("kind"),data.get("name"),data.get("identifier"),data.get("location"),data.get("responsible_user_id"),data.get("status","REGULAR"),data.get("expiry_date"),data.get("last_check_date"),data.get("notes"),user_id,now,now))
            return int(novo[0]["id"])

    def get_asset(self, asset_id: int) -> dict | None:
        with self.connect() as con:
            return banco(con).um("SELECT * FROM assets WHERE id=%s", (asset_id,))

    def update_asset(self, asset_id: int, data: dict[str, Any]) -> None:
        with self.transaction() as con:
            banco(con).escrever("UPDATE assets SET kind=%s,name=%s,identifier=%s,location=%s,responsible_user_id=%s,status=%s,expiry_date=%s,last_check_date=%s,notes=%s,updated_at=%s WHERE id=%s", (data.get("kind"),data.get("name"),data.get("identifier"),data.get("location"),data.get("responsible_user_id"),data.get("status"),data.get("expiry_date"),data.get("last_check_date"),data.get("notes"),self.now(),asset_id))

    def list_assets(self) -> list[dict]:
        with self.connect() as con:
            return banco(con).ler("SELECT a.*,u.full_name responsible_name FROM assets a LEFT JOIN users u ON u.id=a.responsible_user_id ORDER BY a.kind,a.name,a.id")

    def create_lgpd_item(self, data: dict[str, Any], user_id: int) -> int:
        now = self.now()
        with self.transaction() as con:
            novo = banco(con).escrever("INSERT INTO lgpd_items(item_type,title,owner_user_id,status,review_date,notes,created_by,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id", (data.get("item_type"),data.get("title"),data.get("owner_user_id"),data.get("status","PENDENTE"),data.get("review_date"),data.get("notes"),user_id,now,now))
            return int(novo[0]["id"])

    def get_lgpd_item(self, item_id: int) -> dict | None:
        with self.connect() as con:
            return banco(con).um("SELECT * FROM lgpd_items WHERE id=%s", (item_id,))

    def update_lgpd_item(self, item_id: int, data: dict[str, Any]) -> None:
        with self.transaction() as con:
            banco(con).escrever("UPDATE lgpd_items SET item_type=%s,title=%s,owner_user_id=%s,status=%s,review_date=%s,notes=%s,updated_at=%s WHERE id=%s", (data.get("item_type"),data.get("title"),data.get("owner_user_id"),data.get("status"),data.get("review_date"),data.get("notes"),self.now(),item_id))

    def list_lgpd_items(self) -> list[dict]:
        with self.connect() as con:
            return banco(con).ler("SELECT l.*,u.full_name owner_name FROM lgpd_items l LEFT JOIN users u ON u.id=l.owner_user_id ORDER BY l.status,l.review_date NULLS FIRST,l.item_type,l.title,l.id")

    def next_ticket_no(self, ticket_date: str) -> int:
        with self.connect() as con:
            maior = banco(con).valor("SELECT MAX(ticket_no) AS maior FROM service_tickets WHERE ticket_date=%s", (ticket_date,))
            return int(maior or 0) + 1

    def create_ticket(self, priority: bool, service_type: str | None = None) -> int:
        d = date.today().isoformat()
        with self.transaction() as con:
            bd = banco(con)
            bd.travar("service_tickets.ticket_no")
            maior = bd.valor("SELECT MAX(ticket_no) AS maior FROM service_tickets WHERE ticket_date=%s", (d,))
            n = int(maior or 0) + 1
            novo = bd.escrever("INSERT INTO service_tickets(ticket_no,ticket_date,priority,service_type,status,created_at) VALUES (%s,%s,%s,%s, 'AGUARDANDO',%s) RETURNING id", (n,d,1 if priority else 0,service_type,self.now()))
            return int(novo[0]["id"])

    def list_tickets_today(self) -> list[dict]:
        d = date.today().isoformat()
        with self.connect() as con:
            return banco(con).ler("SELECT s.*,u.full_name attendant_name FROM service_tickets s LEFT JOIN users u ON u.id=s.attendant_user_id WHERE ticket_date=%s ORDER BY CASE status WHEN 'CHAMADO' THEN 0 WHEN 'EM_ATENDIMENTO' THEN 1 WHEN 'AGUARDANDO' THEN 2 ELSE 3 END, priority DESC, ticket_no", (d,))

    def update_ticket(self, ticket_id: int, action: str, user_id: int) -> None:
        now = self.now()
        with self.transaction() as con:
            bd = banco(con)
            if action == "call":
                bd.escrever("UPDATE service_tickets SET status='CHAMADO',called_at=%s,attendant_user_id=%s WHERE id=%s", (now,user_id,ticket_id))
            elif action == "start":
                bd.escrever("UPDATE service_tickets SET status='EM_ATENDIMENTO',started_at=COALESCE(started_at,%s),attendant_user_id=%s WHERE id=%s", (now,user_id,ticket_id))
            elif action == "finish":
                bd.escrever("UPDATE service_tickets SET status='FINALIZADO',finished_at=%s,attendant_user_id=%s WHERE id=%s", (now,user_id,ticket_id))

    def service_metrics_today(self) -> dict[str, Any]:
        d = date.today().isoformat()
        with self.connect() as con:
            bd = banco(con)
            total = bd.valor("SELECT COUNT(*) AS n FROM service_tickets WHERE ticket_date=%s", (d,))
            priority = bd.valor("SELECT COUNT(*) AS n FROM service_tickets WHERE ticket_date=%s AND priority=1", (d,))
            # A espera e o atendimento se calculam em Python (regra da casa:
            # data e hora não se calculam no SQL).
            horas = bd.ler("SELECT created_at, started_at, finished_at FROM service_tickets WHERE ticket_date=%s ORDER BY id", (d,))
            waits = [s for s in (_segundos(r["created_at"], r["started_at"]) for r in horas if r["started_at"] is not None) if s is not None]
            service = [s for s in (_segundos(r["started_at"], r["finished_at"]) for r in horas if r["finished_at"] is not None and r["started_at"] is not None) if s is not None]
            hourly = bd.ler("SELECT substr(created_at,12,2) AS hour, COUNT(*) AS count FROM service_tickets WHERE ticket_date=%s GROUP BY substr(created_at,12,2) ORDER BY hour", (d,))
        return {"total":int(total),"priority":int(priority),"avg_wait_seconds":(sum(waits)/len(waits) if waits else 0),"avg_service_seconds":(sum(service)/len(service) if service else 0),"hourly":hourly}

    def dashboard_stats(self, alert_days: int = 5) -> dict[str, int]:
        today = date.today()
        soon = (today + timedelta(days=alert_days)).isoformat()
        # O CONTADOR USA A MESMA RÉGUA DA LISTA — `TP.condicao_aberta`. Com o
        # filtro negativo (`NOT IN ('CONCLUIDA','CANCELADA')`) a palavra que o
        # sistema não conhece inflava «Tarefas abertas» e «Vencidas»: o painel
        # dizia haver serviço de hoje onde havia uma linha que ninguém sabe ler.
        # Duas telas discordando sobre a mesma palavra é o carimbo que mente — e
        # o número que fica fora é declarado logo abaixo.
        aberta, params_abertas = TP.condicao_aberta()
        # A SUSPENSA SAI DA COBRANÇA — relato #132, 15/10/2026: não é aberta a
        # cobrar nem vencida, e aparece contada à parte («suspensas»), para o
        # número de cima não ficar menor sem dizer por quê.
        suspensa, params_suspensa = TS.condicao_suspensa(None, today)
        aberta, suspensa = _pg(aberta), _pg(suspensa)
        cobravel = f"{aberta} AND NOT {suspensa}"
        params_cobravel = [*params_abertas, *params_suspensa]
        with self.connect() as con:
            bd = banco(con)
            row = bd.um(
                f"""SELECT
                SUM(CASE WHEN {cobravel} THEN 1 ELSE 0 END) open_tasks,
                SUM(CASE WHEN {cobravel} AND due_date < %s THEN 1 ELSE 0 END) overdue,
                SUM(CASE WHEN {cobravel} AND due_date >= %s AND due_date <= %s THEN 1 ELSE 0 END) soon,
                SUM(CASE WHEN status='AGUARDANDO_TERCEIRO' THEN 1 ELSE 0 END) waiting,
                SUM(CASE WHEN {aberta} AND {suspensa} THEN 1 ELSE 0 END) suspensas
                FROM tasks""",
                (
                    *params_cobravel,
                    *params_cobravel, today.isoformat(),
                    *params_cobravel, today.isoformat(), soon,
                    *params_abertas, *params_suspensa,
                ),
            )
            # A MESMA RÉGUA DA LISTA — problema #96: o contador «Expedientes
            # ativos» contava o RESPONDIDO como ativo.
            _encerram = EXPT.ETAPAS_QUE_ENCERRAM
            exp = bd.valor(
                "SELECT COUNT(*) AS n FROM expedientes WHERE stage NOT IN "
                f"({', '.join(['%s'] * len(_encerram))})", _encerram)
            pendentes_base, params_pendentes = TP.condicao_aberta()
            pending_base = bd.valor(f"SELECT COUNT(*) AS n FROM tasks WHERE inspection_id IS NOT NULL AND {_pg(pendentes_base)} AND due_date IS NULL", params_pendentes)
            # O QUE SAIU DAS VISTAS APARECE — não entra nos números acima e não
            # desaparece do sistema: a régua é a mesma da tela de tarefas.
            fora_do_vocabulario = TP.tarefas_fora_do_vocabulario(con)
        # A DISPUTA DE ESCRITA VIAJA COM O RESTO DOS AVISOS, para aparecer em
        # qualquer tela: ela e rara, e aviso raro que mora numa tela so e
        # aviso que ninguem ve.
        disputas = self.disputas_de_escrita()
        # O QUE SO O OFICIAL PODE INFORMAR viaja junto, pelo mesmo motivo: sao
        # coisas que travam o balcao e que ninguem ve se morarem numa aba so.
        # A consulta e uma, sobre indice, e a tabela pode nem existir num banco
        # antigo — por isso o try.
        try:
            with self.connect() as con:
                falta = banco(con).valor(
                    "SELECT COUNT(*) c FROM nu_implantacao "
                    "WHERE situacao='ABERTA'")
        except sqlite3.Error:
            falta = 0
        return {"open_tasks": int(row["open_tasks"] or 0), "overdue": int(row["overdue"] or 0), "soon": int(row["soon"] or 0), "waiting": int(row["waiting"] or 0), "open_expedientes": int(exp), "inspection_without_start": int(pending_base),
                "tarefas_fora_do_vocabulario": int(fora_do_vocabulario or 0),
                "tarefas_suspensas": int(row["suspensas"] or 0),
                "disputas_de_escrita": int(disputas["total"]),
                "disputas_recentes": int(disputas["recentes"]),
                "disputas_desde": disputas["primeira"],
                "implantacao_abertas": int(falta or 0)}

    def backup_database(self, dest_path: Path) -> Path:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        # No PostgreSQL a cópia é um pg_dump do schema deste banco (o módulo é
        # nativo desde o lote L072: não há mais o caminho do SQLite).
        return banco_pg.copiar_para_arquivo(self.db_path, dest_path)


def _last_day(year: int, month: int) -> int:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return (next_month - timedelta(days=1)).day
