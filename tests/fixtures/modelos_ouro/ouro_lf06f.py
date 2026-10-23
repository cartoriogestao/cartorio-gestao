"""O OURO DO LF06F — os papéis do RCPJ/RTD e do caixa ANTES de o texto sair do código.

`LF06F_papeis.json`, ao lado, foi gravado em 19/10/2026 na árvore do commit
2c41e90, ANTES de qualquer linha do LF06F, pelo `gerar()` abaixo: as frases
ainda estavam nas f-strings, nas constantes e nos templates, e cada saída saiu
delas. Sem dado real de pessoa — os nomes são de exemplo, o CPF/CNPJ é o de
teste, e a serventia é a do banco de teste.

    funcoes[nome]   o que os montadores puros devolvem (`chamadas()`): teor da
                    certidão, intro/encerramento do teor, rascunhos do
                    WhatsApp, e o que o desenho do PDF ESCREVE na folha (a
                    lista dos textos, e não os pixels — a fonte muda de uma
                    máquina para outra, o texto não)
    telas[nome]     o papel montado pelas rotas, com o banco de teste
                    (`chamadas_com_casa()`): nota devolutiva, etiquetas,
                    certidão em .odt, objeto do PDF da certidão, orçamento

O dia de hoje entra em alguns papéis (a nota, a etiqueta, a data da certidão
em .odt); `sem_o_dia_de_hoje` o troca por «HOJE» dos dois lados, e o resto é
comparado byte a byte.

**NÃO SE REGERA.** Depois do LF06F as frases não estão mais no código, e
`gerar()` leria a base: o teste passaria a comparar a base com ela mesma. Para
conferir o gerador, rode-o numa cópia do commit 2c41e90 (`git worktree add`).
"""
from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
from io import BytesIO
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent / "LF06F_papeis.json"
COMMIT_DE_ANTES = "2c41e90"


def _imprimir(c, url, **kw):
    """A etiqueta é POST com o token desde o LX11 (M8 do LS01): GET que grava
    a contagem não passava pelo CSRF."""
    with c.session_transaction() as sessao:
        token = sessao["csrf_token"]
    return c.post(url, data={"csrf_token": token}, **kw)


def normal(valor):
    """A forma com que o valor foi gravado (tupla vira lista, chave ordenada)."""
    return json.loads(json.dumps(valor, ensure_ascii=False, sort_keys=True))


def tenta(f):
    try:
        return {"ok": f()}
    except Exception as erro:  # noqa: BLE001 — o erro também é saída
        return {"erro": f"{type(erro).__name__}: {erro}"}


def sem_o_dia_de_hoje(texto: str) -> str:
    """Troca o dia de hoje (e a hora) por marcas fixas. Só calcula."""
    from ri_web import data_por_extenso
    hoje = datetime.date.today()
    for forma in (data_por_extenso(hoje), hoje.strftime("%d/%m/%Y"),
                  hoje.isoformat()):
        texto = texto.replace(forma, "«HOJE»")
    return re.sub(r"às \d\d:\d\d", "às «HORA»", texto)


def _textos_desenhados(f) -> list[str]:
    """O que o desenho ESCREVE na folha, palavra por palavra, na ordem.

    Nem os pixels nem as linhas: a quebra de linha depende da largura da letra,
    e a fonte muda de uma máquina para outra (Arial no Windows, a do Pillow
    aqui). As palavras, e a ordem delas, não mudam."""
    from PIL import ImageDraw
    escritos: list[str] = []
    original = ImageDraw.ImageDraw.text

    def anota(self, xy, text, *args, **kwargs):
        escritos.append(str(text))
        return original(self, xy, text, *args, **kwargs)

    ImageDraw.ImageDraw.text = anota
    try:
        f()
    finally:
        ImageDraw.ImageDraw.text = original
    return " ".join(escritos).split()


SERVENTIA_DE_EXEMPLO = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DE EXEMPLO",
    "cidade_uf": "Cidade Exemplo/MA",
    "serventia_telefone": "(99) 0000-0000",
    "serventia_email": "contato@exemplo.invalid",
    "serventia_endereco": "Rua de Exemplo, 100",
    "serventia_cep": "00000-000",
    "ri_cidade": "Cidade Exemplo",
    "ri_uf": "MA",
}

SELO_DE_EXEMPLO = {
    "numero": "AVESVD000000EXEMPLO0000001",
    "texto": ("Poder Judiciário - TJMA. Selo: AVESVD000000EXEMPLO0000001, "
              "08/09/2026 10:30:00, Ato: 15.1, Parte(s): ASSOCIAÇÃO DE "
              "EXEMPLO, Total R$ 20,00 Emol R$ 18,00 FERC R$ 0,50 FADEP R$ 0,75 "
              "FEMP R$ 0,75. Consulte em https://selo.tjma.jus.br"),
    "qr_texto": "https://selo.tjma.jus.br/#/resumo/AVESVD000000EXEMPLO0000001",
}


def _dados_rcpj(**mudar) -> dict:
    registro = {"numero": 148, "serie": "PJ_A", "atribuicao": 3, "volume": "05",
                "natureza": "ATA DE CONSTITUIÇÃO",
                "teor": "Teor de exemplo do registro da associação."}
    registro.update(mudar.pop("registro", {}))
    atos = mudar.pop("atos", None) or [
        {"id": 1, "tipo": "REGISTRO", "folha": "67", "data_ato": "2022-01-31",
         "teor": "Teor de exemplo do registro da associação."},
        {"id": 2, "tipo": "AVERBACAO", "numero_ordem": "374",
         "teor": "Tipo do ato: ALTERAÇÃO DE ESTATUTO.\nAverbação de exemplo."},
        {"id": 3, "tipo": "AVERBACAO", "rotulo": "AV-2",
         "teor": "Outra averbação de exemplo."},
        {"id": 4, "tipo": "AVERBACAO", "numero_ordem": "376", "teor": ""},
    ]
    return {"registro": registro, "atos": atos}


def chamadas() -> dict:
    """Cada montador puro — o caminho em que ele cai no padrão."""
    from PIL import Image

    import atrib_certidao as AC
    import caixa_schema as CXS
    import rg_certidao_pdf as CERT
    import rg_teor_rtdpj as TEOR
    import wa_balcao as WAB
    import wa_textos as WATX

    f: dict = {}

    # ------------------------------------------- a certidão de inteiro teor
    td = _dados_rcpj(registro={"serie": "TD_B", "atribuicao": 4, "volume": None,
                               "numero": 1508})
    td["atos"][0] = {"id": 1, "tipo": "REGISTRO", "teor": "Registro de exemplo."}
    sem_serie = _dados_rcpj(registro={"serie": None, "atribuicao": 9,
                                      "volume": None, "numero": None})
    casos = {
        "registro_e_averbacoes": (_dados_rcpj(), {}),
        "so_averbacoes": (_dados_rcpj(), {"ato_ids": [2, 3]}),
        "so_uma_averbacao": (_dados_rcpj(), {"ato_ids": [3]}),
        "registro_e_uma_averbacao": (_dados_rcpj(), {"ato_ids": [1, 3]}),
        "td_sem_folha_nem_data": (td, {}),
        "td_so_averbacoes": (td, {"ato_ids": [2]}),
        "sem_serie_nem_numero": (sem_serie, {}),
        "so_averbacoes_sem_teor": (_dados_rcpj(), {"ato_ids": [4]}),
        "modelo_da_casa": (_dados_rcpj(), {"modelo": "AJUSTE {onde}{natureza}: {teor}"}),
    }
    for nome, (dados, extra) in casos.items():
        f[f"atrib_certidao.montar_teor({nome})"] = (
            lambda d=dados, e=extra: AC.montar_teor("RCPJ_RTD", d, **e))

    # ------------------------------------------- o teor do RCPJ/RTD (PDF)
    for tipo in ("AVERBACAO", "REGISTRO"):
        for nat, data in (("", ""), ("ALTERAÇÃO DE ESTATUTO", "01/09/2026"),
                          ("ALTERAÇÃO DE ESTATUTO", ""), ("", "01/09/2026")):
            f[f"rg_teor_rtdpj.intro({tipo},{nat!r},{data!r})"] = (
                lambda t=tipo, n=nat, d=data: TEOR.intro(
                    1508, tipo_ato=t, natureza_ato=n, data_assinatura=d))
        f[f"rg_teor_rtdpj.encerramento({tipo})"] = (lambda t=tipo: TEOR.encerramento(
            lavrante_nome="FULANO DE EXEMPLO", lavrante_funcao="Escrevente",
            tipo_ato=t))
    f["rg_teor_rtdpj.intro(sem numero)"] = lambda: TEOR.intro("")
    f["rg_teor_rtdpj.teor_texto_curto"] = lambda: TEOR.teor_texto_curto(
        148, natureza_ato="ATA", data_assinatura="02/09/2026")
    f["rg_teor_rtdpj.encerramento(sem nome)"] = lambda: TEOR.encerramento(
        lavrante_nome="", lavrante_funcao="Escrevente")
    for serie in ("PJ_A", "TD_B", None):
        f[f"rg_teor_rtdpj.linhas_cabecalho({serie})"] = (lambda s=serie: TEOR.linhas_cabecalho(
            cns="000000", unit_short="OFÍCIO ÚNICO DE EXEMPLO / UF", serie=s))
    f["rg_teor_rtdpj.linha_data"] = lambda: TEOR.linha_data(
        cidade="Cidade Exemplo", uf="MA", dia=datetime.date(2026, 9, 8))

    def _textos_teor(modelo: str, *, tipo="AVERBACAO", serie="PJ_A"):
        antigo = TEOR.corpo_do_modelo
        TEOR.corpo_do_modelo = lambda chave, con=None: modelo
        try:
            return {k: v for k, v in TEOR.textos_prontos(
                numero_registro=148, lavrante_nome="FULANO DE EXEMPLO",
                lavrante_funcao="Escrevente", cns="000000",
                unit_short="OFÍCIO ÚNICO DE EXEMPLO / UF", cidade="Cidade Exemplo",
                uf="MA", dia=datetime.date(2026, 9, 8), serie=serie, tipo_ato=tipo,
                natureza_ato="ATA", data_assinatura="").items()
                if isinstance(v, (str, list))}
        finally:
            TEOR.corpo_do_modelo = antigo

    # O AJUSTE DA CASA QUE PERDEU PARTES: cada parte que falta cai na regra
    # de sempre — o cabeçalho curto, a intro, o encerramento e a data.
    f["rg_teor_rtdpj.textos_prontos(ajuste com partes vazias)"] = lambda: _textos_teor(
        "===CABECALHO===\n===INTRO===\n")
    f["rg_teor_rtdpj.textos_prontos(ajuste sem marcas, RTD registro)"] = lambda: _textos_teor(
        "texto solto sem marca nenhuma", tipo="REGISTRO", serie="TD_B")

    def _pagina(**kw):
        textos = TEOR.textos_prontos(
            numero_registro=148, lavrante_nome="FULANO DE EXEMPLO",
            lavrante_funcao="Escrevente", cns="000000",
            unit_short="OFÍCIO ÚNICO DE EXEMPLO / UF", cidade="Cidade Exemplo",
            uf="MA", dia=datetime.date(2026, 9, 8), serie="PJ_A")
        return _textos_desenhados(lambda: TEOR.montar_pagina(
            Image.new("RGB", (60, 80), "white"), textos=textos, with_header=True,
            with_closing=True, rotulo="1/1", com_faixa_selo=True, **kw))
    f["rg_teor_rtdpj.montar_pagina(faixa)"] = lambda: _pagina()
    f["rg_teor_rtdpj.montar_pagina(arquivamento)"] = lambda: _pagina(
        com_arquivamento=True)
    f["rg_teor_rtdpj.montar_pagina(com selo)"] = lambda: _pagina(
        com_arquivamento=True, selo_averbacao=SELO_DE_EXEMPLO,
        selos_extra=[{**SELO_DE_EXEMPLO, "rotulo": "selo 15.9.1"}])

    # ------------------------------------------- a certidão em PDF
    for nat, obj in (("ATA DE CONSTITUIÇÃO", ""), ("", ""),
                     ("ATA", "a(s) averbação(ões) nº 374")):
        f[f"rg_certidao_pdf.contexto_certidao({nat!r},{obj!r})"] = (
            lambda n=nat, o=obj: {k: v for k, v in CERT.contexto_certidao(
                numero=148, natureza=n, objeto_certificado=o,
                data_registro="2022-01-31", serie="PJ_A", volume="05",
                dia=datetime.date(2026, 9, 8)).items()})
    for serie, volume in (("PJ_A", "05"), ("TD_B", None), (None, None),
                          ("TD_B", "007")):
        f[f"rg_certidao_pdf.livro_impresso({serie},{volume})"] = (
            lambda s=serie, v=volume: CERT.livro_impresso(s, v))

    def _textos_cert(serie="TD_B"):
        return CERT.textos_prontos(
            numero=148, lavrante_nome="FULANO DE EXEMPLO",
            lavrante_funcao="Escrevente", serie=serie, volume="7",
            natureza="ATA", data_registro="2022-01-31",
            dia=datetime.date(2026, 9, 8), unit_short="OFÍCIO ÚNICO DE EXEMPLO / UF",
            cns="000000", cidade="Cidade Exemplo")
    # «moldura» (as frases do desenho, lidas da casa) só existe depois do
    # LF06F; o que o ouro guarda é o texto da certidão e o contexto.
    f["rg_certidao_pdf.textos_prontos(TD, natureza)"] = lambda: {
        k: v for k, v in _textos_cert().items()
        if isinstance(v, (str, dict)) and k != "moldura"}
    for com_selo in (False, True):
        f[f"rg_certidao_pdf.montar_capa(selo={com_selo})"] = (
            lambda c=com_selo: _textos_desenhados(lambda: CERT.montar_capa(
                _textos_cert("PJ_A"), com_emolumentos=True,
                selo=SELO_DE_EXEMPLO if c else None)))
    f["rg_certidao_pdf.montar_folha_interna"] = lambda: _textos_desenhados(
        lambda: CERT.montar_folha_interna(
            Image.new("RGB", (60, 80), "white"), textos=_textos_cert(),
            pagina=2, total_paginas=3, com_emolumentos=True))

    # ------------------------------------------- o caixa
    f["caixa_schema.AVISO_ORCAMENTO"] = lambda: CXS.AVISO_ORCAMENTO

    # ------------------------------------------- o WhatsApp
    sem_cidade = {k: v for k, v in SERVENTIA_DE_EXEMPLO.items() if k != "cidade_uf"}
    com_endereco = {**SERVENTIA_DE_EXEMPLO,
                    "endereco_completo": "Praça de Exemplo, s/n, Centro"}
    for rotulo, sv in (("sem serventia", None), ("serventia", SERVENTIA_DE_EXEMPLO),
                       ("sem cidade_uf", sem_cidade), ("endereco completo", com_endereco)):
        f[f"wa_textos.bloco_contato({rotulo})"] = lambda s=sv: WATX.bloco_contato(s)
        f[f"wa_textos.endereco_da_casa({rotulo})"] = lambda s=sv: WATX.endereco_da_casa(s)
        for etiqueta in sorted(WATX.POR_ETIQUETA):
            f[f"wa_textos.rascunho_{etiqueta}({rotulo})"] = (
                lambda e=etiqueta, s=sv: WATX.POR_ETIQUETA[e](s))
    for etiqueta in ("horario", "inventada", None):
        f[f"wa_balcao.rascunhar({etiqueta})"] = (
            lambda e=etiqueta: WAB.rascunhar("mensagem", e, SERVENTIA_DE_EXEMPLO))
    return f


# ================================================= as telas, com o banco

def _png() -> bytes:
    from PIL import Image
    saida = BytesIO()
    Image.new("RGB", (40, 60), "white").save(saida, format="PNG")
    return saida.getvalue()


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _con(casa):
    """A conexão do banco de teste (no PostgreSQL, a ponte do conftest); quem
    lê e grava é o `banco(con)`, que devolve as linhas como dict."""
    import sqlite3
    return sqlite3.connect(casa["banco"])


def _registro_rcpj(casa, *, situacao="ATIVO", teor="Teor de exemplo do registro.",
                   averbacoes=()) -> dict:
    """Um registro do RTD com o ato de registro e as averbações, gravado direto."""
    from bd_nativo import banco
    con = _con(casa)
    with con:
        bd = banco(con)
        rid = bd.escrever(
            """INSERT INTO rg_registros(atribuicao, serie, numero, volume,
                   natureza, requerente_nome, teor, situacao, origem, criado_em)
               VALUES (4, 'TD_B', 1508, '7', 'ESTATUTO DE ASSOCIAÇÃO',
                       'ASSOCIAÇÃO DE EXEMPLO', %s, %s, 'EOFICIO',
                       '2026-08-24T09:00:00') RETURNING id""",
            (teor, situacao))[0]["id"]
        registro_ato = bd.escrever(
            """INSERT INTO rg_atos(registro_id, tipo, folha, data_ato, teor,
                   origem, criado_em)
               VALUES (%s, 'REGISTRO', 79, '2022-12-15', %s, 'EOFICIO',
                       '2026-08-24T09:00:00') RETURNING id""",
            (rid, teor))[0]["id"]
        ids = []
        for ordem, texto, data in averbacoes:
            ids.append(bd.escrever(
                """INSERT INTO rg_atos(registro_id, tipo, numero_ordem, data_ato,
                       teor, origem, criado_em)
                   VALUES (%s, 'AVERBACAO', %s, %s, %s, 'MANUAL',
                           '2026-08-24T09:00:00') RETURNING id""",
                (rid, int(ordem), data, texto))[0]["id"])
    con.close()
    return {"registro": int(rid), "registro_ato": int(registro_ato),
            "averbacoes": [int(x) for x in ids]}


def _emitir(casa, rid: int, **kw) -> dict:
    import atrib_certidao as CE
    con = _con(casa)
    with con:
        r = CE.emitir(con, "RCPJ_RTD", rid, hoje="2026-09-08",
                      agora="2026-09-08T10:00:00", requerente="ASSOCIAÇÃO DE EXEMPLO",
                      usuario="mario", usuario_nome="MARIO EXEMPLO DOS SANTOS",
                      usuario_funcao="Escrevente", **kw)
    con.close()
    return r


def _odt_da_certidao(casa, cid: int, monkeypatch) -> str:
    """O papel por texto da certidão — o ODF que vai ao `gerar_odt`."""
    import atribuicoes_web as AW
    capturado: list = []
    real = AW.gerar_odt

    def captura(corpo, *a, **k):
        capturado.append(corpo)
        return real(corpo, *a, **k)

    monkeypatch.setattr(AW, "gerar_odt", captura)
    r = casa["cliente"].get(f"/atribuicoes/certidoes/{cid}/odt?formato=odt")
    monkeypatch.undo()
    assert r.status_code == 200, r.status_code
    return sem_o_dia_de_hoje(capturado[-1])


def _objeto_do_pdf(casa, cid: int, monkeypatch) -> dict:
    """O que a rota da certidão em PDF manda ao desenho: o objeto certificado."""
    import rg_certidao_pdf as RGCERT
    capturado: list = []
    monkeypatch.setattr(RGCERT, "gerar_pdf",
                        lambda **k: capturado.append(k) or b"%PDF-1.4\n%%EOF\n")
    r = casa["cliente"].get(f"/atribuicoes/certidoes/{cid}/imprimir")
    monkeypatch.undo()
    assert r.status_code == 200, r.status_code
    k = capturado[-1]
    return {c: str(k.get(c) or "") for c in (
        "objeto_certificado", "identificacao_curta", "identificacao_data",
        "natureza", "protocolo", "data_apresentacao")}


def _anexar_imagem(casa, ato_id: int, nome: str) -> None:
    from bd_nativo import banco
    pasta = Path(casa["dados"]) / "lf06f_ouro"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / nome
    caminho.write_bytes(_png())
    con = _con(casa)
    with con:
        banco(con).escrever(
            """INSERT INTO attachments(entity_type, entity_id, original_name,
                   stored_name, stored_path, sha256, size_bytes, description,
                   uploaded_by, uploaded_at)
               VALUES ('RG_ATO', %s, %s, %s, %s, 'abc', 100, 'folha de exemplo',
                       NULL, '2026-09-11T12:00:00')""",
            (ato_id, nome, nome, str(caminho)))
    con.close()


def _receber(casa, **campos) -> int:
    import rg_titulo as TIT
    from bd_nativo import banco
    c = casa["cliente"]
    html = c.get(f"/rcpj-rtd/titulos/novo?atribuicao={TIT.RTD}").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "data_apresentacao": "2026-09-03",
             "hora": "10:30", "apresentante": "ASSOCIAÇÃO DE EXEMPLO",
             "apresentante_documento": "00000010000127",
             "natureza": "Estatuto de associação", "forma": TIT.PAPEL}
    dados.update(campos)
    c.post(f"/rcpj-rtd/titulos/novo?atribuicao={TIT.RTD}", data=dados,
           follow_redirects=True)
    con = _con(casa)
    tid = banco(con).valor("SELECT id FROM rg_titulos ORDER BY id DESC LIMIT 1")
    con.close()
    return int(tid)


def _qualificar(casa, titulo_id: int, resultado: str, **campos) -> None:
    c = casa["cliente"]
    html = c.get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    c.post(f"/rcpj-rtd/titulo/{titulo_id}/qualificar",
           data={"csrf_token": _token(html), "resultado": resultado, **campos},
           follow_redirects=True)


def _nota(casa, **campos) -> str:
    import rg_titulo as TIT
    tid = _receber(casa)
    _qualificar(casa, tid, TIT.NEGATIVA, **campos)
    r = casa["cliente"].get(f"/rcpj-rtd/titulo/{tid}/nota")
    assert r.status_code == 200, r.status_code
    return sem_o_dia_de_hoje(r.get_data(as_text=True))


def _etiqueta(casa, *, selo: str = "") -> str:
    import rg_titulo as TIT
    from bd_nativo import banco
    tid = _receber(casa)
    _qualificar(casa, tid, TIT.POSITIVA)
    c = casa["cliente"]
    html = c.get(f"/rcpj-rtd/titulo/{tid}").get_data(as_text=True)
    c.post(f"/rcpj-rtd/titulo/{tid}/registrar",
           data={"csrf_token": _token(html), "serie": "TD_B",
                 "teor": "Registro integral de exemplo."}, follow_redirects=True)
    con = _con(casa)
    with con:
        bd = banco(con)
        ato_id = bd.valor(
            """SELECT a.id FROM rg_atos a JOIN rg_titulos t ON t.registro_id = a.registro_id
                WHERE t.id = %s ORDER BY a.id LIMIT 1""", (tid,))
        if selo:
            bd.escrever("UPDATE rg_atos SET selo = %s WHERE id = %s", (selo, ato_id))
    con.close()
    r = _imprimir(c, f"/rcpj-rtd/ato/{ato_id}/etiqueta")
    assert r.status_code == 200, r.status_code
    return sem_o_dia_de_hoje(r.get_data(as_text=True))


def _selos_externos(casa, **campos) -> str:
    c = casa["cliente"]
    tela = c.get("/rcpj-rtd/etiquetas/selos-externos").get_data(as_text=True)
    r = c.post("/rcpj-rtd/etiquetas/selos-externos",
               data={"csrf_token": _token(tela), **campos})
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def _selo_externo(casa, numero: str) -> None:
    from bd_nativo import banco
    con = _con(casa)
    with con:
        banco(con).escrever(
            """INSERT INTO sd_selos (numero, texto, caminho, atribuicao, obtido_em,
                   obtido_por)
               VALUES (%s, %s, '/selo/rtdpj/atos-em-geral', 'RTDPJ',
                       '2026-09-10 10:30:00', 'BEATRIZ DE EXEMPLO')""",
            (numero, f"Poder Judiciário - TJMA. Selo: {numero}, 10/09/2026 "
                     "10:30:00, Ato: 15.5.1, Parte(s): ASSOCIAÇÃO DE EXEMPLO, "
                     "Total R$ 20,00 Emol R$ 18,00 FERC R$ 0,50 FADEP R$ 0,75 "
                     "FEMP R$ 0,75"))
    con.close()


def _orcamento(casa, monkeypatch, *, tipo: str) -> str:
    import caixa_web as CW
    from bd_nativo import banco
    con = _con(casa)
    with con:
        bd = banco(con)
        pid = bd.escrever(
            """INSERT INTO cx_protocolos (numero, data_abertura, atribuicao,
                   interessado, assunto, situacao, origem, criado_em, tipo)
               VALUES ('2026.09.46', '2026-09-08', 'RI', 'FULANO DE EXEMPLO',
                       'orçamento de certidão', 'ABERTO', 'MANUAL',
                       '2026-09-08T09:00', %s) RETURNING id""", (tipo,))[0]["id"]
        bd.escrever(
            """INSERT INTO cx_protocolo_atos (protocolo_id, codigo_ato, descricao,
                   quantidade, quitado, origem)
               VALUES (%s, '16.24.4', 'um ato de exemplo', 1, 0, 'MANUAL')""",
            (pid,))
    con.close()
    capturado: list = []
    real = CW.gerar_odt
    monkeypatch.setattr(CW, "gerar_odt",
                        lambda corpo, *a, **k: capturado.append(corpo) or real(corpo, *a, **k))
    r = casa["cliente"].get(f"/caixa/protocolos/{pid}/orcamento")
    monkeypatch.undo()
    assert r.status_code == 200, r.status_code
    return sem_o_dia_de_hoje(capturado[-1])


def chamadas_com_casa() -> dict:
    """As telas, cada uma com o banco de teste zerado (`casa`) e o
    `monkeypatch` do pytest. Cada chamada recebe os dois."""
    t: dict = {}

    def certidao_cancelada(casa, mp):
        ids = _registro_rcpj(casa, situacao="CANCELADO",
                             averbacoes=[("2", "Averbação de exemplo.", "2026-09-01")])
        return _emitir(casa, ids["registro"])["teor"]
    t["atrib_certidao.emitir(registro cancelado)"] = certidao_cancelada

    def certidao_so_averbacoes(casa, mp):
        ids = _registro_rcpj(casa, averbacoes=[
            ("2", "Tipo do ato: ALTERAÇÃO DE ESTATUTO.\nAverbação de exemplo.",
             "2026-09-01")])
        return _emitir(casa, ids["registro"], ato_ids=ids["averbacoes"])["teor"]
    t["atrib_certidao.emitir(so averbacoes)"] = certidao_so_averbacoes

    def odt(casa, mp, *, cancelar=False, cabecalho=False):
        teor = ("REPÚBLICA FEDERATIVA DO BRASIL\nSERVENTIA EXTRAJUDICIAL DE EXEMPLO\n"
                "Teor de exemplo." if cabecalho else "Teor de exemplo do registro.")
        ids = _registro_rcpj(casa, teor=teor, averbacoes=[
            ("2", "Averbação de exemplo.", "2026-09-01")])
        cid = _emitir(casa, ids["registro"])["certidao_id"]
        if cancelar:
            from bd_nativo import banco
            con = _con(casa)
            with con:
                banco(con).escrever(
                    """UPDATE at_certidoes SET cancelada = 1,
                           motivo_cancelamento = 'Motivo de exemplo do cancelamento.'
                        WHERE id = %s""", (cid,))
            con.close()
        return _odt_da_certidao(casa, cid, mp)
    t["atribuicoes_certidao_odt(rcpj_rtd)"] = odt
    t["atribuicoes_certidao_odt(cancelada)"] = lambda casa, mp: odt(casa, mp, cancelar=True)
    t["atribuicoes_certidao_odt(teor com cabecalho)"] = lambda casa, mp: odt(
        casa, mp, cabecalho=True)

    def objeto(casa, mp, *, averbacoes, escolher):
        ids = _registro_rcpj(casa, averbacoes=averbacoes)
        for i, ato_id in enumerate([ids["registro_ato"], *ids["averbacoes"]]):
            _anexar_imagem(casa, ato_id, f"folha_{i}.png")
        escolhidos = (ids["averbacoes"] if escolher == "averbacoes"
                      else [ids["registro_ato"], *ids["averbacoes"]])
        cid = _emitir(casa, ids["registro"], ato_ids=escolhidos)["certidao_id"]
        return _objeto_do_pdf(casa, cid, mp)
    t["atribuicoes_certidao_imprimir(uma averbacao)"] = lambda casa, mp: objeto(
        casa, mp, escolher="averbacoes", averbacoes=[
            ("2", "Tipo do ato: ALTERAÇÃO DE ESTATUTO.\nAverbação de exemplo.",
             "2026-09-01")])
    t["atribuicoes_certidao_imprimir(duas averbacoes)"] = lambda casa, mp: objeto(
        casa, mp, escolher="averbacoes", averbacoes=[
            ("2", "Tipo do ato: ALTERAÇÃO DE ESTATUTO.\nAverbação de exemplo.",
             "2026-09-01"),
            ("3", "Averbação de exemplo sem a natureza escrita.", "2026-09-02")])
    t["atribuicoes_certidao_imprimir(registro)"] = lambda casa, mp: objeto(
        casa, mp, escolher="tudo", averbacoes=[
            ("2", "Averbação de exemplo.", "2026-09-01")])

    t["rcpj_rtd_titulo_nota(prazo e fundamento)"] = lambda casa, mp: _nota(
        casa, exigencias="Falta a ata de eleição da diretoria.\nFalta a lista.",
        fundamentacao="Lei 6.015/1973, art. 121.", prazo_ate="2026-09-20")
    t["rcpj_rtd_titulo_nota(sem prazo)"] = lambda casa, mp: _nota(
        casa, exigencias="Falta a ata de eleição da diretoria.")
    t["rcpj_rtd_etiqueta(sem selo)"] = lambda casa, mp: _etiqueta(casa)
    t["rcpj_rtd_etiqueta(com selo)"] = lambda casa, mp: _etiqueta(
        casa, selo="REGTER000000ABCDEFGHIJKL1234")
    t["rcpj_rtd_etiquetas_selos_externos(manual)"] = lambda casa, mp: _selos_externos(
        casa, selo_manual="REGTER000000ABCDEFGHIJKL1234",
        texto_registro="Averbação n. 2\nAlteração da diretoria.")

    def razao(casa, mp):
        numeros = ["REGTER000000EXTERNO00000001", "REGTER000000EXTERNO00000002"]
        for n in numeros:
            _selo_externo(casa, n)
        return _selos_externos(casa, selo=numeros)
    t["rcpj_rtd_etiquetas_selos_externos(razao)"] = razao
    t["caixa_orcamento(orcamento)"] = lambda casa, mp: _orcamento(casa, mp, tipo="ORCAMENTO")
    t["caixa_orcamento(protocolo)"] = lambda casa, mp: _orcamento(casa, mp, tipo="PROTOCOLO")
    return t


def gerar(raiz: Path, telas: dict) -> None:
    """Grava o ouro. SÓ NA ÁRVORE DE ANTES (commit 2c41e90) — ver o cabeçalho.

    `telas` é o que `chamadas_com_casa()` devolveu, já chamado com o banco de
    teste (quem chama é o pytest, que tem a `casa`)."""
    sys.path.insert(0, str(raiz))
    sujos = subprocess.run(
        ["git", "-C", str(raiz), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True, text=True).stdout.strip()
    assert not sujos, f"a árvore não é a de antes:\n{sujos}"
    commit = subprocess.run(["git", "-C", str(raiz), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    funcoes = {nome: normal(tenta(f)) for nome, f in chamadas().items()}
    ARQUIVO.write_text(json.dumps(
        {"_como": ("Gerado ANTES do LF06F, das f-strings, constantes e templates do "
                   f"commit {commit}, por tests/fixtures/modelos_ouro/ouro_lf06f.py. "
                   "Não regerar: depois da mudança as frases moram na base, e "
                   "regerar faria o teste comparar a base com ela mesma."),
         "commit": commit, "funcoes": funcoes, "telas": normal(telas)},
        ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def ouro() -> dict:
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))
