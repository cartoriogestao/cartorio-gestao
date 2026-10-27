"""O termo assinado do RCPN, digitalizado — problema #121.

    «acrescentar uma dinâmica nova nos registros de rcpn, acrescentar a
     obrigatoriedade de digitalizar o termo no sistema depois da lavratura de
     registro, com visualização do termo assinado» — «nos moldes que temos no
     RI, com possibilidade de visualizar o registro, fica pronto pra emitir
     certidão reprográfica quando necessário»       — o oficial, 07/10/2026

    «no sistema também juntaremos o teor e digitalização para que tenhamos todo
     acervo do registro civil pronto para emitir certidão com um clique»
                                                     — o oficial, 08/10/2026

O MOLDE É O DO RI, E NÃO UMA CÓPIA DELE
    `ri_digitalizacao` guarda UM arquivo oficial por matrícula, com o anterior
    no `historico/`, e monta a certidão página a página. Aqui é o mesmo desenho
    por ASSENTO, em `arquivos/rc/digitalizacoes/<assento_id>/`. O que é peça
    comum (ler o PDF página a página, a miniatura, a gravação que tolera o
    arquivo travado no Windows) é CHAMADO de lá — duas versões da parte que
    abre o PDF divergiriam no primeiro conserto.

A OBRIGAÇÃO É SÓ DO QUE ESTE SISTEMA LAVRA DAQUI PARA A FRENTE
    Medido na produção em 08/10/2026: 7.149 assentos, dos quais 6.771
    `IMPORTACAO`, 244 `EOFICIO`, 111 `ARQUIVO` — e só 23 `MANUAL`. O acervo não
    vira pendência («o acervo não vira atraso», regra da casa): a obrigação
    vale para `origem='MANUAL'` lavrado DEPOIS do corte, e o corte é o instante
    em que esta versão subiu (`settings.rc_digitalizacao_obrigatoria_desde`,
    semeado UMA vez por `rc_schema`). Os 21 registros que a casa lavrou antes
    não viram atraso de um dia para o outro — se o oficial quiser que entrem,
    é mudar a data nessa configuração.

    E `ARQUIVO` NÃO É LAVRATURA, embora nasça hoje: são os 111 assentos que o
    balcão DIGITA do livro de papel («Digitar informações»), o último deles às
    09h53 de 08/10. Por isso a régua é a origem E a data, e não a data sozinha.

A TRAVA É A DO RI: AVISA, NÃO TRANCA — e isso é decisão a confirmar
    `ri_digi_prazo` diz, com todas as letras, «ele não impede lavrar: balcão
    parado por falta de escâner é pior que ficha atrasada». Aqui é igual:
    lavrado sem digitalização fica PENDENTE (aviso na ficha e lista própria),
    e passado o prazo de 7 dias corridos o aviso vermelho sobe para as telas do
    Registro Civil. **NADA aqui recusa certidão** — quem pede a certidão não
    tem culpa de o termo não ter sido escaneado. Bloquear novas lavraturas é
    decisão do oficial, e fica declarada.

QUEM DIGITALIZOU IMPORTA
    `digi_origem` diz de onde veio o arquivo oficial: `BALCAO` (uma pessoa
    enviou pela ficha) ou a origem da carga (`ACERVO_TRANSCRITO`, por padrão).
    É a régua da pasta 7 do RI: **a carga por programa nunca substitui o que
    uma pessoa enviou** — guarda o arquivo novo em `referencia/`, ao lado. E
    só o envio de pessoa baixa a pendência do registro novo: o termo
    assinado é o papel que o balcão tem na mão, e não o que um programa trouxe.
"""
from __future__ import annotations

import io
import json
import os
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import ri_digitalizacao as RDIGI
from bd_nativo import banco
import identidade_do_robo as IDR
from rc_schema import CHAVE_DO_CORTE_DA_DIGITALIZACAO
from storage import hash_file, safe_component, unique_path

#: A mesma lista do RI: PDF, TIFF (multipágina), PNG e JPEG.
EXTENSOES_OK = RDIGI.EXTENSOES_OK

#: Sete dias corridos, como a ficha do RI (`ri_digi_prazo.PRAZO_DIAS`).
PRAZO_DIAS = 7

#: Onde mora a data de corte. Semeada uma vez por `rc_schema.init_rc_schema`
#: — o nome vem de lá, e não é escrito duas vezes.
CHAVE_DO_CORTE = CHAVE_DO_CORTE_DA_DIGITALIZACAO

ORIGEM_BALCAO = "BALCAO"
ORIGEM_ACERVO_TRANSCRITO = "ACERVO_TRANSCRITO"
#: As origens que são de PESSOA: a carga não passa por cima delas.
ORIGENS_DE_PESSOA = frozenset({ORIGEM_BALCAO})

#: Só o registro lavrado neste sistema obriga (ver o docstring).
ORIGENS_QUE_OBRIGAM = frozenset({"MANUAL"})
#: O proclama é edital do Livro D, e não termo assinado pelas partes. Fica de
#: fora até o oficial dizer o contrário — decisão declarada no relatório.
ESPECIES_SEM_OBRIGACAO = frozenset({"PROCLAMAS"})

_COLUNAS = ("digi_path", "digi_nome", "digi_sha256", "digi_em", "digi_por",
            "digi_origem")


class DigitalizacaoError(ValueError):
    """Erro de regra, com a frase pronta para o balcão."""


# ------------------------------------------------------------------ lugares

def pasta_do_assento(raiz_arquivos: Path, assento_id: int) -> Path:
    """Onde mora o termo digitalizado deste assento (e o histórico)."""
    return Path(raiz_arquivos) / "rc" / "digitalizacoes" / str(int(assento_id))


def raiz_arquivos(db) -> Path:
    """A mesma raiz do RI: `archive_root`, ou `arquivos` ao lado do banco."""
    return RDIGI.raiz_arquivos(db)


def _agora() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _normalizar_instante(valor: Any) -> str:
    """'2026-09-07 17:57:34' e '2026-09-07T17:57:34' comparam igual. Só calcula.

    O banco tem as duas formas em `criado_em` (medido em 08/10/2026), e em
    texto o espaço (32) vem antes do `T` (84): comparar cru faria um assento
    das 10h com espaço parecer anterior a um corte das 9h com `T`.
    """
    return str(valor or "").strip().replace(" ", "T")


# ------------------------------------------------------------------ leitura

def atual_do_assento(con, assento_id: int) -> dict | None:
    """A digitalização oficial do assento, ou None. Só LÊ."""
    row = banco(con).um(
        f"SELECT {', '.join(_COLUNAS)} FROM rc_assentos WHERE id=%s",
        (int(assento_id),))
    if not row or not row["digi_path"]:
        return None
    dados = {c: row[c] for c in _COLUNAS}
    # PERGUNTA PELO ARQUIVO, E NÃO SÓ PELA COLUNA — a régua do RI
    # (`_tem_digitalizacao`): caminho gravado apontando para arquivo que sumiu
    # faria a certidão prometer uma reprodução que ninguém consegue montar.
    dados["tem_arquivo"] = Path(dados["digi_path"]).is_file()
    dados["e_de_pessoa"] = (dados.get("digi_origem") or ORIGEM_BALCAO) in ORIGENS_DE_PESSOA
    return dados


def obrigatoria_desde(con) -> str | None:
    """O instante a partir do qual o registro lavrado obriga. Só LÊ."""
    bd = banco(con)
    if not bd.tem_tabela("settings"):
        return None
    valor = _normalizar_instante(
        bd.valor("SELECT value FROM settings WHERE key=%s", (CHAVE_DO_CORTE,)) or "")
    return valor or None


def obriga(assento: dict, desde: str | None) -> bool:
    """Este assento tem de ter o termo digitalizado? Só calcula."""
    if not desde:
        return False
    if str(assento.get("origem") or "").upper() not in ORIGENS_QUE_OBRIGAM:
        return False
    if str(assento.get("situacao") or "ATIVO").upper() == "CANCELADO":
        return False
    if str(assento.get("especie") or "").upper() in ESPECIES_SEM_OBRIGACAO:
        return False
    return _normalizar_instante(assento.get("criado_em")) >= desde


def _baixou_a_pendencia(assento: dict) -> bool:
    """Há termo enviado por PESSOA, e o arquivo existe? Só calcula."""
    caminho = assento.get("digi_path")
    if not caminho:
        return False
    if (assento.get("digi_origem") or ORIGEM_BALCAO) not in ORIGENS_DE_PESSOA:
        return False
    return Path(caminho).is_file()


def _prazo(assento: dict, hoje: date) -> dict:
    lavrado = date.fromisoformat(_normalizar_instante(assento.get("criado_em"))[:10])
    prazo = lavrado + timedelta(days=PRAZO_DIAS)
    return {"lavrado_em": lavrado, "prazo": prazo, "vencida": hoje > prazo,
            "dias": (hoje - lavrado).days}


def situacao(con, assento_id: int,
             hoje: date | None = None) -> dict | None:
    """O que a ficha mostra sobre o termo digitalizado. Só LÊ."""
    hoje = hoje or date.today()
    bd = banco(con)
    assento = bd.um(
        f"""SELECT id, especie, origem, situacao, criado_em,
                   {', '.join(_COLUNAS)}
              FROM rc_assentos WHERE id=%s""", (int(assento_id),))
    if not assento:
        return None
    desde = obrigatoria_desde(bd)
    saida: dict[str, Any] = {
        "digi": atual_do_assento(bd, assento_id),
        "obrigatoria": obriga(assento, desde),
        "desde": desde,
        "pendente": False,
    }
    if saida["obrigatoria"] and not _baixou_a_pendencia(assento):
        saida["pendente"] = True
        saida.update(_prazo(assento, hoje))
    return saida


def pendentes(con, hoje: date | None = None) -> list[dict]:
    """Os registros lavrados aqui sem o termo assinado digitalizado. Só LÊ.

    Ordenados pelo prazo: o que venceu primeiro vem primeiro.
    """
    hoje = hoje or date.today()
    bd = banco(con)
    desde = obrigatoria_desde(bd)
    if not desde:
        return []
    saida = []
    marcas = ",".join("%s" for _ in ORIGENS_QUE_OBRIGAM)
    for assento in bd.ler(
            f"""SELECT id, especie, numero, nome, livro_volume, origem,
                       situacao, criado_em, {', '.join(_COLUNAS)}
                  FROM rc_assentos
                 WHERE origem IN ({marcas})
                   AND COALESCE(situacao, 'ATIVO') <> 'CANCELADO'
                 ORDER BY id""",
            tuple(sorted(ORIGENS_QUE_OBRIGAM))):
        if not obriga(assento, desde) or _baixou_a_pendencia(assento):
            continue
        assento.update(_prazo(assento, hoje))
        saida.append(assento)
    return sorted(saida, key=lambda p: (p["prazo"], p["id"]))


def guardados(raiz: Path, assento_id: int) -> dict[str, list[str]]:
    """Os arquivos antigos (`historico/`) e os da carga (`referencia/`). Só LÊ."""
    pasta = pasta_do_assento(raiz, assento_id)
    saida: dict[str, list[str]] = {}
    for sub in ("historico", "referencia"):
        d = pasta / sub
        saida[sub] = sorted(p.name for p in d.iterdir() if p.is_file()) if d.is_dir() else []
    return saida


# ------------------------------------------------------------------ escrita

def _validar_extensao(nome: str) -> str:
    ext = Path(nome or "").suffix.lower()
    if ext not in EXTENSOES_OK:
        raise DigitalizacaoError(
            "Formato não aceito para o termo digitalizado. Use PDF, TIFF, PNG "
            "ou JPEG.")
    return ext


def _guardar_no_historico(pasta: Path, atual: dict | None) -> str | None:
    """Copia o arquivo oficial de agora para `historico/`. Devolve o caminho."""
    if not atual or not atual.get("digi_path"):
        return None
    antigo = Path(atual["digi_path"])
    if not antigo.is_file():
        return None
    historico = pasta / "historico"
    historico.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = unique_path(
        historico, f"{carimbo}_{safe_component(atual.get('digi_nome') or antigo.name)}")
    shutil.copy2(antigo, destino)
    return str(destino)


def gravar_upload(db, *, assento_id: int, arquivo, usuario: str) -> dict:
    """O balcão envia o termo assinado pela ficha. ESCREVE.

    O anterior não some: vai para `historico/` com carimbo de tempo, para o
    caso de a nova varredura estar errada. Quem envia é PESSOA (`BALCAO`), e é
    isso que baixa a pendência do registro novo.
    """
    if arquivo is None or not getattr(arquivo, "filename", None):
        raise DigitalizacaoError("Escolha o arquivo do termo assinado (PDF ou imagem).")
    nome = Path(arquivo.filename or "termo").name
    ext = _validar_extensao(nome)
    with db.connect() as con:
        bd = banco(con)
        if not bd.um("SELECT 1 AS um FROM rc_assentos WHERE id=%s",
                     (int(assento_id),)):
            raise DigitalizacaoError("Assento não encontrado.")
        atual = atual_do_assento(bd, assento_id)
    pasta = pasta_do_assento(raiz_arquivos(db), assento_id)
    pasta.mkdir(parents=True, exist_ok=True)
    _guardar_no_historico(pasta, atual)
    # A gravação que tolera o PDF travado pelo próprio servidor (WinError 32,
    # HOTFIX-2026-10-06-01 do RI): uma só na casa.
    estavel = RDIGI._gravar_arquivo_estavel(pasta, ext, arquivo)
    sha = hash_file(estavel)
    agora = db.now()
    with db.transaction() as con:
        banco(con).escrever(
            """UPDATE rc_assentos
                  SET digi_path=%s, digi_nome=%s, digi_sha256=%s, digi_em=%s,
                      digi_por=%s, digi_origem=%s
                WHERE id=%s""",
            (str(estavel.resolve()), nome, sha, agora, usuario, ORIGEM_BALCAO,
             int(assento_id)))
    return {"path": str(estavel.resolve()), "nome": nome, "sha256": sha,
            "em": agora, "por": usuario, "origem": ORIGEM_BALCAO,
            "substituiu": bool(atual and atual.get("digi_path"))}


def _e_banco(db_ou_con) -> bool:
    return hasattr(db_ou_con, "transaction") and hasattr(db_ou_con, "connect")


#: Quem anexa ou transcreve por programa (carga do acervo) se identifica
#: (ordem do oficial, 26/10/2026). A carga pode dizer o próprio nome e a
#: pessoa que mandou (`agente=`, `a_mando_de=`); sem isso, vale este nome e o
#: responsável pelas rotinas automáticas.
AGENTE_DA_CARGA = "carga por programa do RCPN"


def _auditar(db_ou_con, quem: str, acao: str, assento_id: int, detalhes: dict,
             agora: str, agente: Any = None, a_mando_de: Any = None) -> None:
    """Auditoria FORA da transação quando é o `Database` (regra da casa);
    com `con`, na mesma transação de quem chamou — o script decide o commit."""
    agente = agente or AGENTE_DA_CARGA
    a_mando_de = a_mando_de or IDR.PELO_RESPONSAVEL
    if _e_banco(db_ou_con):
        db_ou_con.log(None, quem, acao, "rc_assentos", int(assento_id), detalhes,
                      agente=agente, a_mando_de=a_mando_de)
        return
    IDR.registrar(db_ou_con, ts=agora, user_id=None, username=quem, action=acao,
                  entity_type="rc_assentos", entity_id=int(assento_id),
                  details=json.dumps(detalhes, ensure_ascii=False, default=str),
                  agente=agente, a_mando_de=a_mando_de)


def _raiz_para(db_ou_con, raiz: Path | str | None) -> Path:
    if raiz:
        return Path(raiz)
    if _e_banco(db_ou_con):
        return raiz_arquivos(db_ou_con)
    configurada = banco(db_ou_con).valor(
        "SELECT value FROM settings WHERE key='archive_root'") or ""
    if configurada.strip():
        return Path(configurada.strip())
    raise DigitalizacaoError(
        "Com uma conexão crua não sei onde fica a pasta de arquivos (o "
        "`archive_root` está vazio). Passe `raiz_arquivos=` — na produção é "
        "a pasta «arquivos» ao lado do banco.")


def _copiar_conferindo(origem: Path, destino: Path, sha: str) -> Path:
    """Copia por um temporário na mesma pasta e confere o sha256 do destino."""
    tmp = unique_path(destino.parent, f".carga-tmp{destino.suffix}")
    shutil.copy2(origem, tmp)
    try:
        if destino.exists():
            destino.unlink()
        os.replace(tmp, destino)
    except PermissionError:
        # O oficial antigo travado (WinError 32): grava ao lado com carimbo.
        destino = unique_path(
            destino.parent,
            f"{destino.stem}-{datetime.now():%Y%m%d-%H%M%S}{destino.suffix}")
        os.replace(tmp, destino)
    if hash_file(destino) != sha:
        raise DigitalizacaoError(
            f"A cópia de {origem.name} não confere com a origem (sha256).")
    return destino


def anexar_digitalizacao(db_ou_con, assento_id: int, caminho_arquivo,
                         quem: str, origem: str = ORIGEM_ACERVO_TRANSCRITO, *,
                         raiz_arquivos: Path | str | None = None,
                         agora: str | None = None, agente: str | None = None,
                         a_mando_de: str | None = None) -> dict:
    """Anexa POR PROGRAMA o termo digitalizado de um assento. ESCREVE.

    Para a carga do acervo transcrito. Recebe o `Database` (abre a própria
    transação) ou uma `sqlite3.Connection` (escreve nela; quem chamou dá o
    commit). Devolve `{"acao": ...}`:

      IGUAL       o arquivo oficial já é este (mesmo sha256) — nada muda;
      REFERENCIA  já há termo enviado por PESSOA: ele fica, e este vai para
                  `referencia/` (a régua da pasta 7 do RI);
      OFICIAL     não havia termo, ou o que havia era de carga: este passa a
                  ser o oficial, e o anterior vai para `historico/`.

    NÃO CRIA PENDÊNCIA (a pendência é só do registro lavrado aqui) e NÃO A
    BAIXA (só o envio de pessoa baixa).
    """
    origem = (origem or ORIGEM_ACERVO_TRANSCRITO).strip().upper()
    if origem in ORIGENS_DE_PESSOA:
        raise DigitalizacaoError(
            f"A origem «{origem}» é a do envio pela ficha; a carga por programa "
            f"usa outra (ex.: {ORIGEM_ACERVO_TRANSCRITO}).")
    fonte = Path(caminho_arquivo)
    if not fonte.is_file():
        raise DigitalizacaoError(f"Arquivo não encontrado: {fonte}")
    ext = _validar_extensao(fonte.name)
    agora = agora or _agora()
    quem = (quem or "").strip() or "CARGA"

    con = db_ou_con.connect() if _e_banco(db_ou_con) else db_ou_con
    try:
        bd = banco(con)
        if not bd.um("SELECT 1 AS um FROM rc_assentos WHERE id=%s",
                     (int(assento_id),)):
            raise DigitalizacaoError(f"Assento {assento_id} não encontrado.")
        atual = atual_do_assento(bd, assento_id)
    finally:
        if con is not db_ou_con:
            con.close()

    sha = hash_file(fonte)
    pasta = pasta_do_assento(_raiz_para(db_ou_con, raiz_arquivos), assento_id)
    if atual and atual.get("digi_sha256") == sha and atual["tem_arquivo"]:
        return {"acao": "IGUAL", "path": atual["digi_path"], "sha256": sha}

    if atual and atual["tem_arquivo"] and atual["e_de_pessoa"]:
        ref = pasta / "referencia"
        ref.mkdir(parents=True, exist_ok=True)
        destino = _copiar_conferindo(
            fonte, unique_path(ref, f"{agora[:10]}_{safe_component(fonte.name)}"), sha)
        detalhes = {"nome": fonte.name, "sha256": sha, "origem": origem,
                    "referencia": str(destino),
                    "oficial_mantido": atual.get("digi_nome"),
                    "oficial_por": atual.get("digi_por")}
        _auditar(db_ou_con, quem, "RCPN_DIGITALIZACAO_REFERENCIA", assento_id,
                 detalhes, agora, agente, a_mando_de)
        return {"acao": "REFERENCIA", "path": str(destino), "sha256": sha}

    pasta.mkdir(parents=True, exist_ok=True)
    _guardar_no_historico(pasta, atual)
    destino = _copiar_conferindo(fonte, pasta / f"atual{ext}", sha)
    parametros = (str(destino.resolve()), fonte.name, sha, agora, quem, origem,
                  int(assento_id))
    sql = """UPDATE rc_assentos
                SET digi_path=%s, digi_nome=%s, digi_sha256=%s, digi_em=%s,
                    digi_por=%s, digi_origem=%s
              WHERE id=%s"""
    if _e_banco(db_ou_con):
        with db_ou_con.transaction() as tx:
            banco(tx).escrever(sql, parametros)
    else:
        banco(db_ou_con).escrever(sql, parametros)
    _auditar(db_ou_con, quem, "RCPN_DIGITALIZACAO_ANEXADA", assento_id,
             {"nome": fonte.name, "sha256": sha, "origem": origem,
              "fonte": str(fonte), "substituiu": (atual or {}).get("digi_nome")},
             agora, agente, a_mando_de)
    return {"acao": "OFICIAL", "path": str(destino.resolve()), "sha256": sha}


def gravar_teor_transcrito(db_ou_con, assento_id: int, teor: str, quem: str,
                           origem: str = ORIGEM_ACERVO_TRANSCRITO, *,
                           formato: str = "texto",
                           agora: str | None = None, agente: str | None = None,
                           a_mando_de: str | None = None) -> bool:
    """Grava o teor transcrito SÓ onde o assento está sem teor. ESCREVE.

    Devolve True se gravou e False se o assento já tinha teor — o que está lá
    não se sobrescreve (o termo lavrado aqui é o papel assinado; o de outra
    carga é de quem o pôs). A guarda está no próprio `UPDATE`, e não numa
    leitura antes dele: duas cargas ao mesmo tempo não passam uma por cima da
    outra.
    """
    texto = (teor or "").strip()
    if not texto:
        raise DigitalizacaoError("Teor vazio — não há o que gravar.")
    agora = agora or _agora()
    quem = (quem or "").strip() or "CARGA"
    sql = """UPDATE rc_assentos SET teor=%s, teor_formato=%s
              WHERE id=%s AND (teor IS NULL OR TRIM(teor)='')
          RETURNING id"""
    parametros = (texto, formato or "texto", int(assento_id))
    if _e_banco(db_ou_con):
        with db_ou_con.transaction() as tx:
            bd = banco(tx)
            if not bd.um("SELECT 1 AS um FROM rc_assentos WHERE id=%s",
                         (int(assento_id),)):
                raise DigitalizacaoError(f"Assento {assento_id} não encontrado.")
            gravou = len(bd.escrever(sql, parametros)) == 1
    else:
        bd = banco(db_ou_con)
        if not bd.um("SELECT 1 AS um FROM rc_assentos WHERE id=%s",
                     (int(assento_id),)):
            raise DigitalizacaoError(f"Assento {assento_id} não encontrado.")
        gravou = len(bd.escrever(sql, parametros)) == 1
    if gravou:
        _auditar(db_ou_con, quem, "RCPN_TEOR_TRANSCRITO", assento_id,
                 {"origem": (origem or "").upper(), "teor_len": len(texto)},
                 agora, agente, a_mando_de)
    return gravou


# ------------------------------------------------------------------ certidão

def congelar_para_certidao(db, assento_id: int) -> dict:
    """Copia congelada do termo para a certidão reprográfica. ESCREVE no disco.

    O nome é o sha256: a certidão emitida hoje continua apontando para o
    arquivo daquele dia mesmo que o termo seja reenviado amanhã, e a segunda
    certidão do mesmo arquivo não faz cópia nova.
    """
    with db.connect() as con:
        atual = atual_do_assento(con, assento_id)
    if not atual or not atual["tem_arquivo"]:
        raise DigitalizacaoError(
            "Este assento não tem o termo digitalizado no disco. Envie o termo "
            "assinado na ficha antes de emitir a certidão por reprodução.")
    origem = Path(atual["digi_path"])
    sha = hash_file(origem)
    pasta = pasta_do_assento(raiz_arquivos(db), assento_id) / "certidoes"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{sha[:24]}{origem.suffix.lower()}"
    if not destino.is_file():
        shutil.copy2(origem, destino)
    return {"path": str(destino.resolve()), "sha256": sha,
            "nome": atual.get("digi_nome") or origem.name}


def marcar_certidao(con, certidao_id: int, sha256: str) -> None:
    """A certidão saiu da digitalização oficial: guarda o sha. ESCREVE."""
    banco(con).escrever("UPDATE rc_certidoes SET digitalizacao_sha256=%s WHERE id=%s",
                (sha256, int(certidao_id)))


#: A área útil da folha da certidão (A4 com as margens de `ri_odt`, 2,5 cm dos
#: lados e 1,5/2 cm em cima e embaixo), com folga para não encostar.
AREA_W_CM = 16.0
AREA_H_CM = 25.0
#: A ÚLTIMA página é menor para o fecho caber embaixo dela: data, quem
#: assina e o carimbo do selo juntos. Medido no ensaio de 08/10/2026 (PDF
#: pelo LibreOffice): com 25 cm a data e o nome cabiam e o carimbo do selo
#: caía sozinho numa quarta folha — selo separado de quem assina.
AREA_H_ULTIMA_CM = 19.0


def odt_da_certidao(certidao: dict, sv: dict, *, hoje_extenso: str) -> bytes:
    """O `.odt` da certidão reprográfica: o cabeçalho e a introdução da casa,
    uma página do termo por folha, e o fecho com o selo. Só LÊ o disco.

    O texto (cabeçalho, «Era o que cabia certificar.», quem assina e o carimbo
    do selo) é o MESMO da via reprográfica que já existia
    (`rc_certidao_inteiro_teor.html_da_certidao_repro`); o que muda é a imagem:
    em vez de UMA foto num quadro, as páginas do PDF/TIFF, cada uma escalada na
    folha sem esticar — a montagem do RI (`ri_digitalizacao.paginas_png`).
    """
    import rc_certidao_inteiro_teor as RCIT
    from ri_odt import ESTILOS_EXTRA, gerar_odt, html_para_odf

    caminho = Path(str(certidao.get("imagem_caminho") or ""))
    if not caminho.is_file():
        raise RCIT.InteiroTeorError(
            "A cópia do termo digitalizado guardada para esta certidão não está "
            "no disco. Emita de novo pela ficha do assento.")
    paginas = RDIGI.paginas_png(caminho)

    ESTILOS_EXTRA.setdefault(
        "P-rcdigi-pagina",
        '<style:style style:name="P-rcdigi-pagina" style:family="paragraph">'
        '<style:paragraph-properties fo:break-before="page" '
        'fo:text-align="center" fo:margin-top="0cm" fo:margin-bottom="0cm"/>'
        "</style:style>")

    imagens: dict[str, tuple[bytes, str]] = {}
    selo_odf, imgs_selo = RCIT._selo_odf_e_imagens(certidao)
    imagens.update(imgs_selo)
    partes = []
    for i, png in enumerate(paginas, 1):
        nome = f"rcdigi{i}.png"
        imagens[nome] = (png, "image/png")
        try:
            from PIL import Image
            with Image.open(io.BytesIO(png)) as im:
                w, h = RDIGI._escala_ficha_na_folha(
                    im.size[0], im.size[1], area_w_cm=AREA_W_CM,
                    area_h_cm=AREA_H_ULTIMA_CM if i == len(paginas) else AREA_H_CM)
        except Exception:                                   # noqa: BLE001
            w, h = AREA_W_CM, AREA_H_CM
        partes.append(
            f'<text:p text:style-name="P-rcdigi-pagina">'
            f'<draw:frame draw:name="{nome}" text:anchor-type="as-char" '
            f'svg:width="{w}cm" svg:height="{h}cm">'
            f'<draw:image xlink:href="Pictures/{nome}" xlink:type="simple" '
            f'xlink:show="embed" xlink:actuate="onLoad"/></draw:frame></text:p>')
    marca = "##IMG_REPRO##"
    html = RCIT.html_da_certidao_repro(certidao, sv, hoje_extenso=hoje_extenso,
                                       marca_imagem=marca)
    corpo = html_para_odf(html, fragmentos={"@@SELO@@": selo_odf,
                                            marca: "".join(partes)})
    return gerar_odt(
        corpo,
        titulo=f"Certidão inteiro teor {certidao.get('numero')}/{certidao.get('ano')}",
        imagens=imagens, cabecalho_odf="")
