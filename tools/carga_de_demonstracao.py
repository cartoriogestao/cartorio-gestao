"""A carga de demonstração do sandbox — dados FICTÍCIOS, e rodar de novo não duplica.

O QUE ELA PÕE NO BANCO DO SANDBOX
    - a serventia fictícia (Configurações → Serventia): «Ofício Único de Cidade
      Exemplo/MA», CNS 000000, titular «Mario Exemplo dos Santos», substituta
      «Beatriz Exemplo de Souza» — os mesmos nomes de mentira da suíte de testes;
    - três usuários de demonstração (admin, escrevente, auditor), com senhas
      fracas e óbvias DE PROPÓSITO: o sandbox é fechado, só nesta máquina, e
      serve para conhecer o sistema;
    - um livro aberto em cada série do núcleo (os diários, o do dia de hoje),
      pela função de domínio `escrituracao.abrir_livro` — com termo de abertura;
    - uma caixa de folhas de segurança de teste (faixa 99900001–99900100, série
      SB), por `papel_seguranca.receber_remessa`;
    - atos de exemplo onde já há função de domínio que os monta:
        RCPN    — um nascimento e um óbito, com certidão (os ensaios
                  `rcpn_nascimento_ensaio` e `rcpn_obito_ensaio`);
        Notas   — uma procuração pública lavrada no livro
                  (`notas_procuracao_ensaio` + `notas_livro.lancar_ato`);
        Protesto— uma certidão negativa (`protesto_certidao.emitir`);
        RI      — uma matrícula aberta pela própria tela «Matrícula nova».

POR QUE ELA NÃO INVENTA O QUE NÃO TEM
    Não há tabela de emolumentos aqui: na instalação real ela é importada do
    E-Ofício ou do tribunal, e preço inventado num sistema de cartório é pior que
    preço nenhum. Os selos dos atos de exemplo são «obtidos à mão» com números de
    mentira (os mesmos dos ensaios); o selador de mentira, ligado pelo
    `iniciar_sandbox.py`, cuida dos atos que você praticar na tela.

IDEMPOTENTE
    Cada passo pergunta antes se já foi feito (usuário que existe, livro aberto
    na série, folha já cadastrada, ato com a marca de demonstração) e, se foi,
    não faz de novo. O que você mudou no sandbox depois da carga fica como está:
    a serventia só preenche chave em branco, e senha de usuário não se refaz.

RECUSA
    Só roda num banco cuja pasta tenha o arquivo de marca do sandbox
    (`SANDBOX_DEMONSTRACAO.txt`) e que não seja a pasta de uma instalação real —
    a mesma régua de `tools/iniciar_sandbox.py`.

USO (o INICIAR_SANDBOX.cmd já roda isto sozinho)
    python tools/carga_de_demonstracao.py [--dados PASTA]
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from tools import iniciar_sandbox as KIT  # noqa: E402

#: (usuário, nome, perfil, senha) — senhas fracas e óbvias DE PROPÓSITO.
USUARIOS_DE_DEMONSTRACAO = (
    ("admin", "Mario Exemplo dos Santos", "ADMIN", "admin123"),
    ("escrevente", "Beatriz Exemplo de Souza", "USER", "escrevente123"),
    ("auditor", "Carla Exemplo Lima", "AUDITOR", "auditor123"),
)

#: A serventia fictícia — só entra onde a chave estiver em branco.
SERVENTIA_DE_DEMONSTRACAO = {
    "unit_name": "Ofício Único de Cidade Exemplo/MA",
    "ri_cns": "000000",
    "ri_cidade": "Cidade Exemplo",
    "ri_uf": "MA",
    "ri_registrador": "Mario Exemplo dos Santos",
    "serventia_titular": "Mario Exemplo dos Santos",
    "serventia_titulo": "Tabelião e Oficial de Registro",
    "ri_substituta": "Beatriz Exemplo de Souza",
    "serventia_cnpj": "00.000.001/0000-55",
    "serventia_endereco": "Rua da Demonstração, 100, Centro",
    "serventia_cep": "00000-000",
    "serventia_telefone": "(00) 0000-0000",
    "serventia_email": "sandbox@exemplo.invalid",
    "selo_tabela_custas_em": "2026-01-01",
}

#: Estas valem SEMPRE no sandbox: mesmo que alguém suba o `app.py` direto sobre
#: esta pasta, ele escuta só nesta máquina, sem a descoberta UDP e fora da porta
#: da instalação real.
REDE_DO_SANDBOX = {
    "network_host": "127.0.0.1",
    "network_port": str(KIT.PORTA_PADRAO),
    "discovery_enabled": "0",
}

FAIXA_DAS_FOLHAS = ("99900001", "99900100")
OPERADOR = "SANDBOX — CARGA DE DEMONSTRAÇÃO"
MARCA_PROCURACAO = "demonstracao-procuracao"
REQUERENTE_PROTESTO = "SANDBOX — DEMONSTRAÇÃO"
LOGRADOURO_RI = "Rua da Demonstração"


class CargaRecusada(KIT.SandboxRecusado):
    """A carga não roda neste banco. A mensagem diz por quê."""


def _conferir_banco(db) -> Path:
    pasta = Path(db.db_path).resolve().parent
    KIT.conferir_pasta_de_dados(pasta)
    if not (pasta / KIT.MARCA).exists():
        raise CargaRecusada(
            f"Recusado: a carga de demonstração só roda na pasta de um sandbox "
            f"(falta o arquivo {KIT.MARCA} em {pasta}). Nada foi gravado.")
    return pasta


# ------------------------------------------------------------------ os passos


def _serventia(db, pasta: Path) -> str:
    atuais = db.get_settings()
    faltando = {k: v for k, v in SERVENTIA_DE_DEMONSTRACAO.items()
                if not str(atuais.get(k) or "").strip()}
    imagens = str(atuais.get("ri_imagens_raiz") or "")
    ajustes = dict(REDE_DO_SANDBOX)
    if not imagens or not KIT._dentro(KIT._resolver(imagens), pasta):
        ajustes["ri_imagens_raiz"] = str(pasta / "arquivos" / "ri_imagens")
    db.set_settings({**faltando, **ajustes})
    return f"{len(faltando)} campo(s) preenchido(s)" if faltando else "já estava preenchida"


def _usuarios(db) -> str:
    criados = []
    for usuario, nome, papel, senha in USUARIOS_DE_DEMONSTRACAO:
        with db.connect() as con:
            existe = con.execute("SELECT 1 FROM users WHERE username=? COLLATE NOCASE",
                                 (usuario,)).fetchone()
        if not existe:
            db.create_user(usuario, nome, senha, papel)
            criados.append(usuario)
    return ("criados: " + ", ".join(criados)) if criados else "já existiam"


def _livros(db) -> str:
    import escrituracao as ESC
    import livro_nucleo as LN
    import serventia
    from ri_web import data_por_extenso

    hoje = str(db.now())[:10]
    sv = serventia.dados(db.get_settings)
    abertos = 0
    for codigo in sorted(LN.SERIES):
        dia = hoje if LN.SERIES[codigo].diario else None
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            if ESC.livro_da_vez(con, codigo, dia=dia):
                continue
        with db.transaction() as con:
            ESC.abrir_livro(con, codigo, sv=sv, agora=db.now(),
                            data_extenso=data_por_extenso(date.fromisoformat(hoje)),
                            dia=dia, usuario=OPERADOR)
        abertos += 1
    return f"{abertos} livro(s) aberto(s)" if abertos else "todos já estavam abertos"


def _folhas(db) -> str:
    import papel_seguranca as PS
    de, ate = FAIXA_DAS_FOLHAS
    with db.connect() as con:
        if con.execute("SELECT 1 FROM pp_folhas WHERE codigo=?", (de,)).fetchone():
            return "já estavam no estoque"
    with db.transaction() as con:
        caixa = PS.receber_remessa(
            con, fornecedor="SANDBOX — papel de teste", codigo_de=de, codigo_ate=ate,
            agora=db.now(), serie="SB", tipo="Papel de Segurança - DEMONSTRAÇÃO",
            observacao="Faixa de demonstração do sandbox: não existe no Tribunal.",
            usuario=OPERADOR)
    return f"{caixa['quantas']} folha(s) recebida(s)"


def _rcpn(db) -> str:
    import rcpn_nascimento_ensaio as RNE
    import rcpn_obito_ensaio as ROE
    operador = USUARIOS_DE_DEMONSTRACAO[0][1]
    feitos = []
    for nome, modulo in (("nascimento", RNE), ("óbito", ROE)):
        assento = modulo.garantir_assento(db, operador=operador)
        modulo.garantir_certidao(db, assento["assento_id"], operador=operador)
        if assento.get("feito"):
            feitos.append(nome)
    return ("lavrados: " + ", ".join(feitos)) if feitos else "já existiam"


def _notas(db) -> str:
    import json
    import ato_selado as AS
    import notas_livro as NL
    import notas_partes as NP
    import notas_procuracao_ensaio as NPE
    from ri_web import data_por_extenso

    with db.connect() as con:
        if con.execute("SELECT 1 FROM nt_atos WHERE origem='MANUAL' AND origem_chave=?",
                       (MARCA_PROCURACAO,)).fetchone():
            return "já existia"
    agora = db.now()
    hoje = agora[:10]
    sv = db.get_settings()
    oficial = USUARIOS_DE_DEMONSTRACAO[0][1]
    with db.transaction() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(
            """INSERT INTO nt_atos
               (tipo, serie, data, hora, situacao, natureza, modelo_codigo,
                interessado, teor_formato, lavrado_nome, lavrado_titulo,
                origem, origem_chave, criado_em)
               VALUES ('PROCURACAO','PROCURACAO',?,?,'EM_LAVRATURA','Procuracao',?,?,
                       'html',?,?,'MANUAL',?,?)""",
            (hoje, agora[11:16], NPE.MODELO_CODIGO, NPE.INTERESSADO, oficial,
             "Tabelião e Oficial de Registro", MARCA_PROCURACAO, agora))
        ato_id = int(cur.lastrowid)
        for p in NPE.PARTES:
            con.execute(
                """INSERT INTO nt_ato_partes
                   (ato_id, nome, nome_norm, documento, tipo_pessoa, qualificacao,
                    nacionalidade, estado_civil, profissao, endereco, testemunha,
                    ordem, criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ato_id, p["nome"], NP.normalizar(p["nome"]), p["documento"],
                 p["tipo_pessoa"], p["qualificacao"], p["nacionalidade"],
                 p["estado_civil"], p["profissao"], p["endereco"], p["testemunha"],
                 p["ordem"], agora))
        teor = NPE.montar_teor(con, db, lavrado_nome=oficial)
        con.execute(
            "UPDATE nt_atos SET teor=?, modelo_valores=? WHERE id=?",
            (teor, json.dumps(NPE.MODELO_VALORES, ensure_ascii=False), ato_id))
        NL.lancar_ato(con, ato_id, sv, agora,
                      data_por_extenso(date.fromisoformat(hoje)),
                      paginas=NL.estimar_paginas(teor), usuario=oficial)
        cns = db.get_setting("ri_cns", "")
        AS.registrar_selo_obtido_a_mao(
            con, NPE.SELO_ENSAIO.format(cns=cns), tabela="nt_atos", ato_id=ato_id,
            atribuicao="NOTAS", agora=agora, cns=cns, usuario=oficial,
            texto="Selo de demonstração — procuração pública do sandbox")
        con.execute("UPDATE nt_atos SET situacao='LAVRADO' WHERE id=?", (ato_id,))
    return "procuração lavrada"


def _protesto(db) -> str:
    import protesto_certidao as PC
    with db.connect() as con:
        if con.execute("SELECT 1 FROM pt_certidoes WHERE requerente=?",
                       (REQUERENTE_PROTESTO,)).fetchone():
            return "já existia"
    nome = "FULANO DE TAL DEMONSTRAÇÃO"
    agora = db.now()
    with db.transaction() as con:
        achados = PC.buscar(con, nome=nome)
        PC.emitir(con, nome=nome, documento="000.000.001-91", hoje=agora[:10],
                  agora=agora, requerente=REQUERENTE_PROTESTO,
                  finalidade="Demonstração do sandbox", usuario=OPERADOR,
                  achados=achados, tipo="NEGATIVA")
    return "certidão negativa emitida"


def _ri(db, app) -> str:
    if app is None:
        return None  # sem o aplicativo não há a tela; o passo fica de fora
    with db.connect() as con:
        if con.execute("SELECT 1 FROM ri_matriculas WHERE logradouro=?",
                       (LOGRADOURO_RI,)).fetchone():
            return "já existia"
        admin = con.execute("SELECT id FROM users WHERE username=?",
                            (USUARIOS_DE_DEMONSTRACAO[0][0],)).fetchone()
    if not admin:
        raise CargaRecusada("o usuário admin de demonstração não existe")
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao["user_id"] = int(admin[0])
        sessao["csrf_token"] = "carga-de-demonstracao"
        sessao["last_activity"] = db.now()
    resposta = cliente.post("/registro-imoveis/nova", data={
        "csrf_token": "carga-de-demonstracao", "livro": "2",
        "cidade": "Cidade Exemplo", "uf": "MA", "rural_urbano": "URBANO",
        "logradouro": LOGRADOURO_RI, "numero_predial": "10", "bairro": "Centro",
        "area_valor": "360", "area_unidade": "m2",
        "descricao_perimetro": "Lote urbano FICTÍCIO, só para demonstração do sandbox.",
    })
    with db.connect() as con:
        if con.execute("SELECT 1 FROM ri_matriculas WHERE logradouro=?",
                       (LOGRADOURO_RI,)).fetchone():
            return "matrícula aberta"
    corpo = resposta.get_data(as_text=True)
    aviso = re.search(r'class="[^"]*alert[^"]*"[^>]*>\s*(.*?)\s*<', corpo, re.S)
    raise CargaRecusada("a tela não abriu a matrícula"
                        + (f": {aviso.group(1)[:200]}" if aviso else
                           f" (HTTP {resposta.status_code})"))


PASSOS = (
    ("serventia", lambda db, app, pasta: _serventia(db, pasta)),
    ("usuários", lambda db, app, pasta: _usuarios(db)),
    ("livros", lambda db, app, pasta: _livros(db)),
    ("folhas de segurança", lambda db, app, pasta: _folhas(db)),
    ("RCPN", lambda db, app, pasta: _rcpn(db)),
    ("Notas", lambda db, app, pasta: _notas(db)),
    ("Protesto", lambda db, app, pasta: _protesto(db)),
    ("Registro de Imóveis", lambda db, app, pasta: _ri(db, app)),
)
#: Sem estes o sandbox não serve para nada; os outros são exemplo e podem faltar.
PASSOS_ESSENCIAIS = {"serventia", "usuários"}


def carregar(db, app=None) -> dict:
    """Roda os passos. Devolve {'feitos': {passo: o que fez}, 'pulados': {passo: motivo}}.

    Passo de exemplo que falha não derruba a carga: o motivo vai para «pulados» e
    aparece no quadro do sandbox. Os essenciais (serventia, usuários) estouram.
    """
    pasta = _conferir_banco(db)
    relatorio = {"feitos": {}, "pulados": {}}
    for nome, passo in PASSOS:
        try:
            resultado = passo(db, app, pasta)
        except Exception as erro:  # noqa: BLE001 — o motivo vai para o quadro
            if nome in PASSOS_ESSENCIAIS:
                raise
            relatorio["pulados"][nome] = str(erro) or erro.__class__.__name__
            continue
        if resultado is None:
            relatorio["pulados"][nome] = "precisa do aplicativo montado (rode pelo INICIAR_SANDBOX)"
        else:
            relatorio["feitos"][nome] = resultado
    return relatorio


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description="Carga de demonstração do sandbox.")
    ap.add_argument("--dados", help="pasta de dados do sandbox (padrão: a do INICIAR_SANDBOX)")
    a = ap.parse_args(argv)
    try:
        KIT.conferir_raiz_do_programa()
        ambiente = KIT.preparar_pasta(Path(a.dados) if a.dados else KIT.pasta_padrao())
        KIT.aplicar_ambiente(ambiente)
    except KIT.SandboxRecusado as erro:
        print(str(erro))
        return 2
    KIT.armar_trava_de_rede()
    app = KIT.montar_app()
    try:
        relatorio = carregar(app.extensions["db"], app=app)
    except (CargaRecusada, KIT.SandboxRecusado) as erro:
        print(str(erro))
        return 2
    for passo, feito in relatorio["feitos"].items():
        print(f"  {passo:<22} {feito}")
    for passo, motivo in relatorio["pulados"].items():
        print(f"  {passo:<22} NÃO FEITO: {motivo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
