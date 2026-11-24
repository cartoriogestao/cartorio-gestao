"""A conferência do georreferenciamento no ato — `ri_georref.py` (RI011, art. 343-F, II do CNN).

O QUE ESTES TESTES PROTEGEM

    avisa, não bloqueia     o ato sai com a conferência em branco, «depois» ou de robô; o que fica é a linha
                            PENDENTE, e o aviso na tela

    quem e quando           a linha tem o nome de quem declarou e a hora; a pendente não se reescreve — quem
                            volta a ela grava uma linha nova que aponta para a antiga

    quais atos pedem        a abertura de matrícula sempre; a natureza que mexe no perímetro; nunca o
                            cancelamento

    a tela                  o formulário de lavrar e o de abrir matrícula trazem o passo, e os rótulos da macro
                            são os de `ri_georref.ROTULOS`

Dados fictícios. Nada aqui fala com o ONR nem com o SIG-RI.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_georref as GEO
from bd_nativo import banco

AGORA = "2026-11-23T10:00:00"


# ------------------------------------------------------------ o que a lei pede (puro)

@pytest.mark.parametrize("natureza", [
    "Loteamento Urbano", "Loteamento Rural", "Sentenças Declaratórias de Usucapião", "Usucapião Extrajudicial",
    "Averbação de Desmembramento", "Averbação de Unificação", "Averbação de Remembramento",
    "Averbação de Indicação ou Atualização de Confrontação", "Averbação de Retificação de Área",
    "Averbação de Alteração de Novas Divisas",
    # fora da tabela do SAUIN, a palavra decide
    "Georreferenciamento do imóvel rural", "retificação de area",
])
def test_a_natureza_que_mexe_no_perimetro_pede_o_passo(natureza):
    assert GEO.exige_conferencia(natureza) is True


@pytest.mark.parametrize("natureza", [
    None, "", "Compra e Venda", "Hipoteca", "Averbação de Construção", "Cancelamento de Hipoteca",
    # o cancelamento nunca muda o perímetro, ainda que o nome cite a palavra
    "Cancelamento de Matrícula", "Cancelamento de desmembramento",
])
def test_o_que_nao_mexe_no_perimetro_nao_pede(natureza):
    assert GEO.exige_conferencia(natureza) is False


def test_o_modelo_de_georreferenciamento_e_o_de_unificacao_pedem_mesmo_sem_natureza():
    assert GEO.exige_conferencia(None, "av-georreferenciamento") is True
    assert GEO.exige_conferencia("", "AV-UNIFICACAO") is True
    assert GEO.exige_conferencia("", "R-COMPRA-VENDA") is False


def test_todos_os_codigos_da_lista_existem_na_tabela_do_sauin():
    import ri_naturezas as NAT
    assert GEO.CODIGOS_QUE_PEDEM <= set(NAT.POR_CODIGO), "código que não existe na tabela do SAUIN"


def test_em_branco_robo_e_desconhecida_viram_pendente_sem_recusar():
    assert GEO.interpretar("", "")[0] == GEO.PENDENTE
    assert GEO.interpretar("TALVEZ", "")[0] == GEO.PENDENTE
    situacao, _, avisos = GEO.interpretar(GEO.SEM_OCORRENCIA, "", robo=True)
    assert situacao == GEO.PENDENTE and "robô" in avisos[0]


def test_ocorrencia_sem_descricao_grava_e_avisa():
    situacao, obs, avisos = GEO.interpretar(GEO.COM_OCORRENCIA, " ..  ")
    assert situacao == GEO.COM_OCORRENCIA and obs == ".."
    assert avisos and "descrição" in avisos[0]
    assert GEO.interpretar(GEO.COM_OCORRENCIA, "Sobreposição com a matrícula vizinha")[2] == []


def test_os_rotulos_da_macro_sao_os_do_modulo():
    """A macro repete os rótulos para não depender de contexto (ver o cabeçalho dela)."""
    macro = (RAIZ / "templates" / "_georref_passo.html").read_text(encoding="utf-8")
    opcoes = re.findall(r'<option value="([A-Z_]+)"[^>]*>([^<]+)</option>', macro)
    assert dict(opcoes) == {v: GEO.ROTULOS[v] for v in GEO.SITUACOES}


# ------------------------------------------------------------ no banco

@pytest.fixture()
def db(cg_casa):
    return cg_casa["db"]


def _matricula(db, numero="5001", **campos) -> int:
    base = {"numero": numero, "livro": "2", "livro_norm": "2", "tipo_ficha": "ESTRUTURADA",
            "criado_em": AGORA}
    base.update(campos)
    with db.transaction() as con:
        return banco(con).escrever(
            f"INSERT INTO ri_matriculas ({', '.join(base)}) VALUES ({', '.join(['%s'] * len(base))}) RETURNING id",
            tuple(base.values()))[0]["id"]


def _registrar(db, mid, situacao, **extra):
    with db.transaction() as con:
        return GEO.registrar(con, matricula_id=mid, ocasiao=extra.pop("ocasiao", GEO.OCASIAO_ATO),
                             situacao=situacao, quem=extra.pop("quem", "Maria Exemplo"),
                             quem_id=extra.pop("quem_id", 7), agora=extra.pop("agora", AGORA), **extra)


def test_grava_quem_conferiu_quando_e_o_que_declarou(db):
    mid = _matricula(db)
    linha = _registrar(db, mid, GEO.SEM_OCORRENCIA, ato_rotulo="AV-2", natureza_titulo="Averbação de Retificação de Área")
    assert linha["pendente"] is False and linha["avisos"] == []
    with db.connect() as con:
        gravada = banco(con).um("SELECT * FROM ri_georref_conferencias WHERE id = %s", (linha["id"],))
    assert gravada["conferido_por"] == "Maria Exemplo" and gravada["conferido_por_id"] == 7
    assert gravada["conferido_em"] == AGORA and gravada["situacao"] == GEO.SEM_OCORRENCIA
    assert "Maria Exemplo" in GEO.frase(gravada) and "2026-11-23 10:00" in GEO.frase(gravada)


def test_robo_nao_deixa_nome_de_maquina_na_conferencia(db):
    mid = _matricula(db)
    linha = _registrar(db, mid, GEO.SEM_OCORRENCIA, quem="Robô de Teste", quem_id=99, robo=True)
    assert linha["pendente"] is True and linha["conferido_por"] is None
    with db.connect() as con:
        gravada = banco(con).um("SELECT conferido_por, conferido_por_id FROM ri_georref_conferencias WHERE id=%s",
                                (linha["id"],))
    assert gravada["conferido_por"] is None and gravada["conferido_por_id"] is None


def test_a_pendente_se_resolve_por_linha_nova_e_a_antiga_fica(db):
    mid = _matricula(db)
    pendente = _registrar(db, mid, GEO.PENDENTE, ato_rotulo="AV-2")
    with db.connect() as con:
        assert [p["id"] for p in GEO.da_matricula(con, mid)["pendentes"]] == [pendente["id"]]
        assert [p["id"] for p in GEO.pendentes(con)] == [pendente["id"]]
    _registrar(db, mid, GEO.SEM_OCORRENCIA, ocasiao=GEO.OCASIAO_AVULSA, refere_id=pendente["id"],
               agora="2026-11-24T09:00:00")
    with db.connect() as con:
        ficha = GEO.da_matricula(con, mid)
        assert ficha["pendentes"] == [] and GEO.pendentes(con) == []
        assert len(ficha["avulsas"]) == 1
        antiga = banco(con).um("SELECT situacao, conferido_em FROM ri_georref_conferencias WHERE id=%s",
                               (pendente["id"],))
    assert antiga["situacao"] == GEO.PENDENTE and antiga["conferido_em"] == AGORA, "a pendente não se reescreve"


def test_resolver_pendente_de_outra_matricula_e_recusado(db):
    a, b = _matricula(db, "5001"), _matricula(db, "5002")
    pendente = _registrar(db, a, GEO.PENDENTE)
    with pytest.raises(GEO.GeorrefError):
        _registrar(db, b, GEO.SEM_OCORRENCIA, ocasiao=GEO.OCASIAO_AVULSA, refere_id=pendente["id"])


def test_ocasiao_desconhecida_e_recusada(db):
    mid = _matricula(db)
    with pytest.raises(GEO.GeorrefError):
        _registrar(db, mid, GEO.PENDENTE, ocasiao="QUALQUER")


def test_matricula_encerrada_nao_entra_na_lista_de_pendentes(db):
    viva, morta = _matricula(db, "5001"), _matricula(db, "5002", encerrada=1)
    _registrar(db, viva, GEO.PENDENTE)
    _registrar(db, morta, GEO.PENDENTE)
    with db.connect() as con:
        assert [p["matricula_id"] for p in GEO.pendentes(con)] == [viva]


def test_o_ato_que_sai_do_livro_larga_a_conferencia_e_ela_fica_na_ficha(db):
    mid = _matricula(db)
    _registrar(db, mid, GEO.PENDENTE, ato_id=123, ato_rotulo="AV-2")
    with db.transaction() as con:
        GEO.soltar_do_ato(con, 123)
    with db.connect() as con:
        ficha = GEO.da_matricula(con, mid)
    assert ficha["por_ato"] == {} and len(ficha["pendentes"]) == 1


def test_o_aviso_depois_de_lavrar_so_sai_quando_ha_o_que_avisar():
    assert GEO.aviso_do_ato("x", None) is None
    assert GEO.aviso_do_ato("x", {"situacao": GEO.SEM_OCORRENCIA}) is None
    assert GEO.aviso_do_ato("x", {"situacao": GEO.NAO_GEORREFERENCIADO}) is None
    assert "PENDENTE" in GEO.aviso_do_ato("x", {"situacao": GEO.PENDENTE})
    assert "ocorrência" in GEO.aviso_do_ato("x", {"situacao": GEO.COM_OCORRENCIA})


# ------------------------------------------------------------ nas telas

def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _linhas(db, mid):
    with db.connect() as con:
        return banco(con).ler("SELECT * FROM ri_georref_conferencias WHERE matricula_id=%s ORDER BY id", (mid,))


def _abrir_matricula(s, **extra):
    """Abre uma matrícula pela tela, no intervalo do sistema (não-acervo)."""
    from ri_schema import PRIMEIRA_MATRICULA_DO_SISTEMA as PRIMEIRA
    db = s["db"]
    with db.transaction() as con:
        bd = banco(con)
        if not bd.um("SELECT 1 FROM ri_numeracao WHERE livro=%s", ("2",)):
            bd.escrever("""INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso, fixado_em)
                           VALUES (%s,%s,%s,'2026-11-23')""", ("2", PRIMEIRA, PRIMEIRA - 1))
    html = s["c"].get("/registro-imoveis/nova").get_data(as_text=True)
    assert 'name="georref_situacao"' in html, "a abertura de matrícula tem de trazer o passo"
    r = s["c"].post("/registro-imoveis/nova", data={
        "livro": "2", "cidade": "Cidade Exemplo", "uf": "MA", "area_unidade": "ha",
        "proprietario_nome": "Fulano Exemplo", "csrf_token": _token(html), **extra},
        follow_redirects=True)
    with db.connect() as con:
        mid = int(banco(con).um("SELECT MAX(id) AS i FROM ri_matriculas")["i"])
    return mid, r.get_data(as_text=True)


def test_abrir_matricula_grava_a_conferencia_com_o_nome_de_quem_abriu(cg_casa_logada):
    s = cg_casa_logada
    mid, _ = _abrir_matricula(s, georref_situacao="SEM_OCORRENCIA", georref_obs="")
    (linha,) = _linhas(s["db"], mid)
    assert linha["ocasiao"] == GEO.OCASIAO_ABERTURA and linha["situacao"] == GEO.SEM_OCORRENCIA
    assert linha["conferido_por"] and linha["conferido_em"]
    ficha = s["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Georreferenciamento — mosaico no SIG-RI" in ficha and "conferida" in ficha


def test_abrir_matricula_sem_responder_nao_bloqueia_e_fica_pendente(cg_casa_logada):
    s = cg_casa_logada
    mid, pagina = _abrir_matricula(s)
    (linha,) = _linhas(s["db"], mid)
    assert linha["situacao"] == GEO.PENDENTE, "abriu a matrícula: o passo avisa e não trava"
    assert "ficou PENDENTE" in " ".join(pagina.split())
    assert f"/registro-imoveis/{mid}#georreferenciamento" in s["c"].get(
        "/registro-imoveis/georreferenciamento").get_data(as_text=True)


def test_a_pendente_se_resolve_pela_ficha(cg_casa_logada):
    s = cg_casa_logada
    mid, _ = _abrir_matricula(s)
    (pendente,) = _linhas(s["db"], mid)
    ficha = s["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "pendente(s)" in ficha
    s["c"].post(f"/registro-imoveis/{mid}/georreferenciamento", follow_redirects=True, data={
        "csrf_token": _token(ficha), "refere_id": str(pendente["id"]),
        "georref_situacao": "COM_OCORRENCIA", "georref_obs": "Sobreposição com a matrícula vizinha"})
    linhas = _linhas(s["db"], mid)
    assert [x["situacao"] for x in linhas] == [GEO.PENDENTE, GEO.COM_OCORRENCIA]
    assert linhas[1]["refere_id"] == pendente["id"] and linhas[1]["ocasiao"] == GEO.OCASIAO_AVULSA
    with s["db"].connect() as con:
        assert GEO.da_matricula(con, mid)["pendentes"] == []


def test_lavrar_ato_que_mexe_no_perimetro_grava_a_conferencia_e_nao_trava(cg_casa_logada):
    from selador_de_bancada import ligar_o_selador
    s = cg_casa_logada
    mid, _ = _abrir_matricula(s)
    with ligar_o_selador(s):
        html = s["c"].get(f"/registro-imoveis/{mid}?lavrar=1").get_data(as_text=True)
        assert 'name="georref_situacao"' in html, "o formulário de lavrar tem de trazer o passo"
        base = {"tipo": "AV", "teor": "AV-01 Retificação da área do imóvel", "data_ato": "2026-11-23",
                "natureza_titulo": "Averbação de Retificação de Área", "codigo_tj": "16.22.2",
                "csrf_token": _token(html)}
        # sem responder: lavra e fica pendente
        s["c"].post(f"/registro-imoveis/{mid}/atos", data=base, follow_redirects=True)
    with s["db"].connect() as con:
        atos = banco(con).ler("SELECT id, tipo, numero FROM ri_atos WHERE matricula_id=%s", (mid,))
    assert len(atos) == 1, "o passo avisa e não bloqueia: o ato tem de ter sido lavrado"
    por_ato = [x for x in _linhas(s["db"], mid) if x["ato_id"] == atos[0]["id"]]
    assert len(por_ato) == 1 and por_ato[0]["situacao"] == GEO.PENDENTE
    assert por_ato[0]["ocasiao"] == GEO.OCASIAO_ATO and por_ato[0]["ato_rotulo"].startswith("AV-")

    # respondendo: conferido, com o nome e a hora
    with ligar_o_selador(s):
        html = s["c"].get(f"/registro-imoveis/{mid}?lavrar=1").get_data(as_text=True)
        s["c"].post(f"/registro-imoveis/{mid}/atos", follow_redirects=True, data={
            **base, "csrf_token": _token(html), "teor": "AV-02 Nova retificação",
            "georref_situacao": "SEM_OCORRENCIA", "georref_obs": "Mosaico sem sobreposição"})
    segunda = [x for x in _linhas(s["db"], mid) if x["situacao"] == GEO.SEM_OCORRENCIA]
    assert len(segunda) == 1 and segunda[0]["conferido_por"] and segunda[0]["observacao"] == "Mosaico sem sobreposição"
    ficha = s["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Georreferenciamento (art. 343-F, II):" in ficha


def test_ato_que_nao_mexe_no_perimetro_nao_cria_linha_nenhuma(cg_casa_logada):
    from selador_de_bancada import ligar_o_selador
    s = cg_casa_logada
    mid, _ = _abrir_matricula(s)
    antes = len(_linhas(s["db"], mid))
    with ligar_o_selador(s):
        html = s["c"].get(f"/registro-imoveis/{mid}?lavrar=1").get_data(as_text=True)
        s["c"].post(f"/registro-imoveis/{mid}/atos", follow_redirects=True, data={
            "tipo": "AV", "teor": "AV-01 Averbação de construção", "data_ato": "2026-11-23",
            "natureza_titulo": "Averbação de Construção", "codigo_tj": "16.22.2",
            "csrf_token": _token(html)})
    with s["db"].connect() as con:
        assert banco(con).um("SELECT count(*) AS n FROM ri_atos WHERE matricula_id=%s", (mid,))["n"] == 1
    assert len(_linhas(s["db"], mid)) == antes, "só o ato que pede (ou a pessoa que responde) grava conferência"


def test_a_lista_abre_sem_pendencia(cg_casa_logada):
    s = cg_casa_logada
    assert "Nada pendente" in s["c"].get("/registro-imoveis/georreferenciamento").get_data(as_text=True)
