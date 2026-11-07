"""Semente da casa de ensaio: ri. Ver `layout_casa.py`.

O QUE ELA PÕE NO BANCO
    A matrícula nos estados que mudam a ficha (estruturada aberta, com ato, encerrada, com
    pendência; acervo aberta e com ato sem selo), a prenotação em cada situação (aberta sem
    selo, aberta, com documento, com ato, em exigência, cancelada), o usucapião do início ao fim
    do rito, o registro do Livro 3 em quatro estados, e o que as rotas de arquivo precisam: a
    certidão, a nota devolutiva, a ata do expurgo, a digitalização, a CTP e a DOI.

    Tudo pela própria tela, com a pessoa do ensaio. Só caem para a função de domínio ou para
    `casa.inserir` as linhas que nenhuma tela escreve sem rede ou sem a chave da IA: o selo da
    prenotação e da conferência (digitado à mão no razão), o pedido de qualificação da IA, o lote
    de transcrição, a imagem do E-Ofício e o pedido do ONR.

    Os selos digitados ficam na faixa 80 a 99 do sufixo (`...CRSVO80`), que é do RI: o razão recusa
    o mesmo selo em dois atos, e as sementes das outras áreas, todas na mesma casa, têm de ficar
    fora dela.

O QUE CADA FICHA GUARDA EM `casa.ids`, para `test_layout_fichas_ri.py`
    ri_mat_estruturada_aberta · ri_mat_estruturada_com_ato · ri_mat_encerrada · ri_mat_com_pendencias
    ri_mat_acervo_aberta · ri_mat_acervo_com_ato_sem_selo
    ri_pren_sem_selo · ri_pren_aberta · ri_pren_com_documento · ri_pren_com_ato · ri_pren_em_exigencia
    ri_pren_cancelada
    ri_us_autuado · ri_us_em_curso · ri_us_decidido · ri_us_registrado · ri_us_rejeitado
    ri_l3_sem_partes_sem_selo · ri_l3_completo · ri_l3_cancelado · ri_l3_com_minuta
"""
from __future__ import annotations

import io
import struct
import traceback
import zlib
from datetime import date, timedelta

import layout_ensaio as E

#: Rota com número que não tem como abrir aqui: endpoint -> o motivo.
SEM_SEMENTE: dict[str, str] = {
    "onr_saec_ficha": ("a ficha é montada com a resposta ao vivo da API do ONR (SAEC), que a trava barra e para a qual "
                       "esta casa nem tem credencial: não existe linha local que a sustente"),
    "ri_qualificacao_ia_nota": ("a nota devolutiva (#365) só abre com o pedido PRONTO, e pronto só fica com a "
                                "resposta da IA, que a trava barra; a semente gera o pedido e anota a ficha dele "
                                "(`ri_qualificacao_ia_ver`)"),
    "onr_cobranca_ficha": ("a ficha é montada com a resposta ao vivo da API do ONR, pelo hash que ele devolve ao gerar a "
                           "cobrança: sem rede e sem credencial não há hash nem linha local que a sustente"),
}

CPF = "00000000191"
TELEFONE = "(00) 00000-0000"
PREFIXO_DO_SELO = "AVESVD000000NARRKWVNJCRSVO"
PRIMEIRO_SUFIXO_DO_SELO = 80
DONO = {"proprietario_nome": "Mario Exemplo", "proprietario_documento": CPF,
        "proprietario_qualificacao": "brasileiro, casado, empresário"}
PARTES_DA_COMPRA = {"parte_nome": ["Mario Exemplo", "Beatriz Exemplo"], "parte_documento": [CPF, ""],
                    "parte_papel": ["transmitente", "adquirente"], "parte_qualificacao": ["", ""],
                    "parte_documento_tipo": ["", ""]}


# ------------------------------------------------------------------ o que os passos usam

def _recados(c) -> str:
    with c.session_transaction() as sessao:
        return " | ".join(f"{cat}: {txt}" for cat, txt in (sessao.get("_flashes") or []))


def _mandar(casa, destino, /, *, esperar=(302,), **campos):
    """Manda o formulário como a tela manda. Devolve (resposta, o recado que a tela deu)."""
    c = casa.cliente()
    r = c.post(destino, data={"csrf_token": casa.token(c), **campos})
    recado = _recados(c)
    if r.status_code not in esperar:
        # A tela que responde 200 já gastou o recado ao desenhar a página: ele está no HTML.
        na_tela = " | ".join(f"{cat}: {txt}" for cat, txt in E.ler_pagina(r.get_data(as_text=True)).flashes)
        raise AssertionError(f"POST {destino}: HTTP {r.status_code}. {recado or na_tela}")
    return r, recado


def _linha(casa, comando: str, parametros=()):
    achada = casa.um(comando, parametros)
    assert achada, f"não achei a linha: {comando} {parametros}"
    return achada


def _id(casa, chave: str) -> int:
    assert chave in casa.ids, f"falta `{chave}`: o passo que o cria falhou antes"
    return casa.ids[chave]


def _selo(casa) -> str:
    casa.ids["_ri_selo"] = casa.ids.get("_ri_selo", PRIMEIRO_SUFIXO_DO_SELO - 1) + 1
    assert casa.ids["_ri_selo"] <= 99, "acabou a faixa de selos do RI"
    return f"{PREFIXO_DO_SELO}{casa.ids['_ri_selo']:02d}"


def _quem(casa) -> str:
    return _linha(casa, "SELECT full_name FROM users WHERE id=%s", (casa.ids["admin"],))["full_name"]


def _selar_a_mao(casa, tabela: str, ato_id: int) -> str:
    """O selo que o escrevente tirou no portal, digitado no razão, para a tabela que a tela não deixa digitar."""
    import ato_selado as AS
    numero, quem = _selo(casa), _quem(casa)
    with casa.transacao() as con:
        AS.registrar_selo_obtido_a_mao(con, numero, tabela=tabela, ato_id=int(ato_id), atribuicao="RI",
                                       agora=casa.db.now(), cns=casa.db.get_setting("ri_cns", ""), usuario=quem)
    return numero


def _png(largura: int = 64, altura: int = 64) -> bytes:
    def pedaco(tipo: bytes, dados: bytes) -> bytes:
        corpo = tipo + dados
        return struct.pack(">I", len(dados)) + corpo + struct.pack(">I", zlib.crc32(corpo) & 0xFFFFFFFF)
    cabeca = struct.pack(">IIBBBBB", largura, altura, 8, 0, 0, 0, 0)
    linhas = (b"\x00" + b"\xf0" * largura) * altura
    return (b"\x89PNG\r\n\x1a\n" + pedaco(b"IHDR", cabeca) + pedaco(b"IDAT", zlib.compress(linhas))
            + pedaco(b"IEND", b""))


def _arquivo(conteudo: bytes, nome: str):
    return (io.BytesIO(conteudo), nome)


PDF_MINIMO = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


# ------------------------------------------------------------------ as matrículas

def _abrir(casa, **campos) -> dict:
    """Abre a matrícula pela tela «Matrícula nova» e devolve a linha."""
    antes = casa.um("SELECT COALESCE(MAX(id), 0) AS n FROM ri_matriculas")["n"]
    dados = {"livro": "2", "cidade": "Cidade Exemplo", "uf": "MA", "rural_urbano": "URBANO", "bairro": "Centro",
             "cep": "00000-000", "area_valor": "360", "area_unidade": "m2",
             "descricao_perimetro": "Lote urbano fictício, só para o ensaio do layout.",
             "confrontacoes": "Ao norte, a Rua Exemplo; ao sul, o lote vizinho."} | campos
    _, recado = _mandar(casa, "/registro-imoveis/nova", **dados)
    nova = casa.um("SELECT * FROM ri_matriculas WHERE id > %s ORDER BY id LIMIT 1", (antes,))
    assert nova, f"a tela não abriu a matrícula: {recado}"
    casa.pagina("ri_ficha", matricula_id=int(nova["id"]))
    return nova


def _acervo(casa) -> None:
    # Enquanto o contador está abaixo de 4.015, toda matrícula nasce de acervo.
    a1 = _abrir(casa, logradouro="Rua do Acervo", numero_predial="20", registro_anterior="Transcrição n.º 100, Livro 3-A",
                teor=("MATRÍCULA. Um lote urbano fictício, com 360 m², na Rua do Acervo, Cidade Exemplo/MA, "
                      "pertencente a Mario Exemplo, brasileiro, casado, conforme a transcrição anterior. "
                      "Texto corrido do acervo, só para o ensaio do layout."))
    assert a1["tipo_ficha"] == "ACERVO", f"esperava ficha de acervo, veio {a1['tipo_ficha']} (n.º {a1['numero']})"
    casa.ids["ri_mat_acervo_aberta"] = int(a1["id"])
    a2 = _abrir(casa, logradouro="Rua do Acervo Averbado", numero_predial="30",
                teor=("MATRÍCULA. Um lote urbano fictício, com 360 m², na Rua do Acervo Averbado, Cidade "
                      "Exemplo/MA, pertencente a Ana Exemplo. Texto corrido do acervo, só para o ensaio."))
    assert a2["tipo_ficha"] == "ACERVO"
    casa.ids["ri_mat_acervo_com_ato_sem_selo"] = int(a2["id"])


def _numeracao(casa) -> None:
    _mandar(casa, "/registro-imoveis/numeracao", livro="2", proximo_numero="4100", observacao="Numeração do ensaio")
    fixada = _linha(casa, "SELECT proximo_numero FROM ri_numeracao WHERE livro=%s", ("2",))["proximo_numero"]
    assert int(fixada) == 4100, f"a numeração não ficou em 4100: {fixada}"


def _estruturadas(casa) -> None:
    e1 = _abrir(casa, logradouro="Avenida da Casa Aberta", numero_predial="100", folha="1", **DONO)
    assert e1["tipo_ficha"] == "ESTRUTURADA", f"esperava ficha estruturada, veio {e1['tipo_ficha']} (n.º {e1['numero']})"
    casa.ids["ri_mat_estruturada_aberta"] = int(e1["id"])
    e2 = _abrir(casa, logradouro="Rua dos Atos Lavrados", numero_predial="200", folha="2",
                selo_abertura_texto=_selo(casa), **DONO)
    casa.ids["ri_mat_estruturada_com_ato"] = int(e2["id"])
    e3 = _abrir(casa, logradouro="Travessa do Encerramento", numero_predial="300", folha="3", **DONO)
    _mandar(casa, f"/registro-imoveis/{e3['id']}/encerrar", motivo="Imóvel transportado para ficha nova, só para o ensaio.",
            destino="4999")
    assert _linha(casa, "SELECT encerrada FROM ri_matriculas WHERE id=%s", (e3["id"],))["encerrada"], "não encerrou"
    casa.ids["ri_mat_encerrada"] = int(e3["id"])
    e4 = _abrir(casa, logradouro="Alameda das Pendências", numero_predial="400", folha="4", **DONO)
    casa.ids["ri_mat_com_pendencias"] = int(e4["id"])
    e5 = _abrir(casa, logradouro="Praça do Expurgo", numero_predial="500", folha="5", **DONO)
    casa.ids["_ri_mat_do_expurgo"] = int(e5["id"])


# ------------------------------------------------------------------ as prenotações

def _prenotar(casa, matricula_id: int | None = None, **campos) -> dict:
    antes = casa.um("SELECT COALESCE(MAX(id), 0) AS n FROM ri_protocolos")["n"]
    dados = {"livro_destino": "2", "telefone": TELEFONE, "apresentante": "Beatriz Exemplo",
             "natureza_titulo": "Compra e venda", "objeto": "Compra e venda de lote urbano fictício",
             "documento_descricao": "Escritura de compra e venda (ensaio)"} | campos
    if matricula_id is not None:
        dados["matricula_numero"] = _linha(casa, "SELECT numero FROM ri_matriculas WHERE id=%s", (matricula_id,))["numero"]
    _, recado = _mandar(casa, "/registro-imoveis/protocolo", **dados)
    nova = casa.um("SELECT * FROM ri_protocolos WHERE id > %s ORDER BY id LIMIT 1", (antes,))
    assert nova, f"a tela não prenotou: {recado}"
    casa.pagina("ri_protocolo_ver", protocolo_id=int(nova["id"]))
    return nova


def _prenotacoes(casa) -> None:
    e1, e2 = _id(casa, "ri_mat_estruturada_aberta"), _id(casa, "ri_mat_estruturada_com_ato")
    sem_selo = _prenotar(casa)
    assert not (sem_selo["selo_prenotacao"] or "").strip(), "sem selador, a prenotação não devia ter selo"
    casa.ids["ri_pren_sem_selo"] = int(sem_selo["id"])

    for chave, matricula in (("ri_pren_aberta", e1), ("ri_pren_com_documento", e1), ("ri_pren_com_ato", e2),
                             ("ri_pren_em_exigencia", e1), ("ri_pren_cancelada", None)):
        p = _prenotar(casa, matricula)
        _selar_a_mao(casa, "ri_protocolos", int(p["id"]))
        casa.ids[chave] = int(p["id"])

    com_documento = _id(casa, "ri_pren_com_documento")
    _mandar(casa, f"/registro-imoveis/prenotacao/{com_documento}/documento",
            documento=_arquivo(PDF_MINIMO, "titulo-exemplo.pdf"), tipo="TITULO",
            descricao="Título apresentado (ensaio)")
    anexo = casa.um("SELECT id FROM attachments WHERE entity_type='RI_PROTOCOLO' AND entity_id=%s ORDER BY id LIMIT 1",
                    (com_documento,))
    assert anexo, "o documento não ficou anexado à prenotação"
    casa.ids["_ri_anexo_do_titulo"] = int(anexo["id"])

    em_exigencia = _id(casa, "ri_pren_em_exigencia")
    _mandar(casa, f"/registro-imoveis/protocolo/{em_exigencia}/nota",
            exigencias="Apresentar a certidão de ônus reais atualizada.\nApresentar a guia do ITBI quitada.",
            fundamentacao="Qualificação negativa de ensaio.")
    nota = casa.um("SELECT id FROM ri_notas_devolutivas WHERE protocolo_id=%s ORDER BY id LIMIT 1", (em_exigencia,))
    assert nota, "a nota devolutiva não nasceu"
    assert _linha(casa, "SELECT situacao FROM ri_protocolos WHERE id=%s", (em_exigencia,))["situacao"] == "DEVOLVIDO"
    casa.ids["_ri_nota"] = int(nota["id"])
    casa.pagina("ri_nota_odt", {"formato": "odt"}, nota_id=int(nota["id"]))
    casa.pagina("ri_nota_devolutiva", protocolo_id=em_exigencia)
    casa.pagina("ri_nota_excluir", protocolo_id=em_exigencia, nota_id=int(nota["id"]))

    cancelada = _id(casa, "ri_pren_cancelada")
    _mandar(casa, f"/registro-imoveis/protocolo/{cancelada}", acao="encerrar", motivo="DESISTENCIA", confirmar="1",
            observacao="Desistência de ensaio.")
    assert _linha(casa, "SELECT situacao FROM ri_protocolos WHERE id=%s", (cancelada,))["situacao"] == "CANCELADO"

    casa.pagina("ri_prenotacao_comprovante", protocolo_id=com_documento)
    casa.pagina("andamento_prenotacao", protocolo_id=em_exigencia)


# ------------------------------------------------------------------ os atos

def _lavrar(casa, matricula_id: int, **campos) -> dict:
    antes = casa.um("SELECT COALESCE(MAX(id), 0) AS n FROM ri_atos")["n"]
    dados = {"tipo": "AV", "data_ato": casa.hoje, "natureza_titulo": "Averbação de ensaio",
             "teor": "AVERBAÇÃO de ensaio do layout, lavrada pela própria tela."} | campos
    _, recado = _mandar(casa, f"/registro-imoveis/{matricula_id}/atos", **dados)
    ato = casa.um("SELECT * FROM ri_atos WHERE matricula_id=%s AND id > %s ORDER BY id LIMIT 1", (matricula_id, antes))
    assert ato, f"o ato não foi lavrado: {recado}"
    return ato


def _atos(casa) -> None:
    e2 = _id(casa, "ri_mat_estruturada_com_ato")
    numero_da_prenotacao = _linha(casa, "SELECT numero FROM ri_protocolos WHERE id=%s",
                                  (_id(casa, "ri_pren_com_ato"),))["numero"]
    r1 = _lavrar(casa, e2, tipo="R", natureza_titulo="Compra e venda", selo_texto=_selo(casa),
                 protocolo=str(numero_da_prenotacao),
                 teor="COMPRA E VENDA. Mario Exemplo vende o imóvel a Beatriz Exemplo, pelo valor declarado de R$ 100.000,00.",
                 **PARTES_DA_COMPRA)
    casa.ids["_ri_ato_r1_da_com_ato"] = int(r1["id"])
    amarrado = _linha(casa, "SELECT ato_id FROM ri_protocolos WHERE id=%s", (_id(casa, "ri_pren_com_ato"),))["ato_id"]
    assert amarrado and int(amarrado) == int(r1["id"]), "a prenotação não ficou amarrada ao ato"
    av2 = _lavrar(casa, e2, tipo="AV", selo_texto=_selo(casa),
                  teor="AVERBAÇÃO DE CONSTRUÇÃO. Sobre o lote foi edificada uma casa residencial, de 80 m².")
    casa.ids["_ri_ato_av2_da_com_ato"] = int(av2["id"])

    a2 = _id(casa, "ri_mat_acervo_com_ato_sem_selo")
    ato_a2 = _lavrar(casa, a2, tipo="AV", numero="9", natureza_titulo="Averbação de estado civil",
                     teor="AVERBAÇÃO. Fica averbado o casamento da proprietária, conforme a certidão apresentada.")
    assert not (ato_a2["selo_texto"] or "").strip(), "o ato de acervo sem selo nasceu com selo"
    casa.ids["_ri_ato_sem_selo"] = int(ato_a2["id"])

    e5 = _id(casa, "_ri_mat_do_expurgo")
    selo_do_expurgo = _selo(casa)
    do_expurgo = _lavrar(casa, e5, tipo="R", natureza_titulo="Compra e venda", selo_texto=selo_do_expurgo,
                         teor="COMPRA E VENDA lavrada só para ser expurgada no ensaio.", **PARTES_DA_COMPRA)
    _mandar(casa, f"/registro-imoveis/atos/{do_expurgo['id']}/expurgar", confirmacao="EXPURGAR",
            motivo="Ato lavrado só para o ensaio do layout, e expurgado em seguida.", selo_cancelado=selo_do_expurgo)
    expurgo = casa.um("SELECT id FROM ri_expurgos WHERE matricula_id=%s ORDER BY id LIMIT 1", (e5,))
    assert expurgo, "o expurgo não gravou a ata"
    casa.pagina("ri_expurgo_ata", expurgo_id=int(expurgo["id"]))
    casa.pagina("ri_expurgar_ato", ato_id=int(av2["id"]))


def _pendencias_da_ficha(casa) -> None:
    e4 = _id(casa, "ri_mat_com_pendencias")
    _mandar(casa, f"/registro-imoveis/{e4}/minuta", tipo="AV", natureza_titulo="Averbação de ensaio",
            teor="AVERBAÇÃO de ensaio, guardada como minuta para revisar e lavrar.")
    minuta = _linha(casa, "SELECT id FROM ri_minutas WHERE matricula_id=%s ORDER BY id LIMIT 1", (e4,))
    _mandar(casa, f"/registro-imoveis/{e4}/rascunho", tipo="AV", natureza_titulo="Averbação de ensaio",
            teor="Rascunho de averbação, guardado sem lavrar e sem tomar número.")
    _mandar(casa, f"/registro-imoveis/{e4}/revisoes", assunto="Conferir o memorial",
            nota="Conferir o memorial descritivo com o confrontante, antes de selar.")
    assert casa.um("SELECT 1 AS n FROM ri_rascunhos WHERE matricula_id=%s", (e4,)), "o rascunho não ficou"
    assert casa.um("SELECT 1 AS n FROM ri_revisoes WHERE matricula_id=%s", (e4,)), "a nota de revisão não ficou"
    casa.pagina("ri_ficha", {"minuta": int(minuta["id"])}, matricula_id=e4)
    casa.pagina("ri_rascunho_ver", matricula_id=e4)


# ------------------------------------------------------------------ as rotas de papel e de arquivo

def _certidao(casa) -> None:
    e2 = _id(casa, "ri_mat_estruturada_com_ato")
    _mandar(casa, f"/registro-imoveis/{e2}/certidao", tipo="INTEIRO_TEOR", fonte_corpo="TEXTO", requerente="Carla Exemplo",
            finalidade="Ensaio do layout", selo_texto=_selo(casa))
    certidao = casa.um("SELECT id FROM ri_certidoes WHERE matricula_id=%s ORDER BY id DESC LIMIT 1", (e2,))
    assert certidao, "a certidão não nasceu"
    casa.ids["_ri_certidao"] = int(certidao["id"])
    casa.pagina("ri_certidao_odt", {"formato": "odt"}, certidao_id=int(certidao["id"]))


def _digitalizacoes(casa) -> None:
    e2, a1 = _id(casa, "ri_mat_estruturada_com_ato"), _id(casa, "ri_mat_acervo_aberta")
    for matricula in (e2, a1):
        _mandar(casa, f"/registro-imoveis/{matricula}/digitalizacao", arquivo=_arquivo(_png(), "ficha-exemplo.png"))
        assert _linha(casa, "SELECT digi_path FROM ri_matriculas WHERE id=%s", (matricula,))["digi_path"]
    casa.pagina("ri_baixar_digitalizacao", matricula_id=e2)
    casa.pagina("ri_miniatura_digitalizacao", matricula_id=e2)
    casa.pagina("ri_conferir_ficha", matricula_id=e2)

    pasta = casa.pasta_temporaria / "ri_ensaio"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / "00004101.0001.png"
    caminho.write_bytes(_png())
    imagem = casa.inserir("ri_imagens", matricula_id=e2, nome_arquivo=caminho.name, caminho=str(caminho), ordem=1)
    casa.pagina("ri_imagem", imagem_id=int(imagem))

    casa.pagina("ri_transcricao_andamento", matricula_id=a1)
    import revisao_transcricao_lote as RTL
    quem = _quem(casa)
    with casa.transacao() as con:
        lote = RTL.criar(con, {"livro": "", "de": "", "ate": "", "so_sem_revisao": False}, usuario=quem)
    casa.pagina("ri_transcricoes_lote_ver", lote_id=int(lote))


def _paginas_da_matricula(casa) -> None:
    e1, e2 = _id(casa, "ri_mat_estruturada_aberta"), _id(casa, "ri_mat_estruturada_com_ato")
    casa.pagina("ri_editar_matricula", matricula_id=e1)
    casa.pagina("ri_ficha_odt", matricula_id=e2)
    casa.pagina("ri_aplicar_modelo", matricula_id=e1, codigo="AV-CONSTRUCAO")
    casa.pagina("ri_preencher_modelo", matricula_id=e1, codigo="R-COMPRA-VENDA")
    casa.pagina("ri_onus_sugestao", matricula_id=e2)
    casa.pagina("ri_situacao_juridica", matricula_id=e2)
    casa.pagina("revisao_previa_ri_ultima", matricula_id=e2)
    casa.pagina("ri_onr_indicador", matricula_id=e2)
    casa.pagina("ri_importacao_manual", especie="RI_MATRICULA")
    casa.pagina("ri_importacao_manual", especie="LIVRO3_REGISTRO")


def _ctp_e_doi(casa) -> None:
    """A CTP e a DOI nascem do mesmo dado digitado: a escritura da compra e venda do ato R-1."""
    ato = _id(casa, "_ri_ato_r1_da_com_ato")
    competencia = casa.hoje[:7]
    dados = {"operacao": "11", "data_negocio": casa.hoje, "valor_operacao": "100000,00", "valor_base_itbi": "100000,00",
             "forma_pagamento": "5", "motivo_sem_ni": "2", "folha_ato": "2-1", "natureza_titulo": "2"}
    for parte in casa.ler("SELECT id FROM ri_partes WHERE ato_id=%s ORDER BY id", (ato,)):
        dados[f"participacao_{parte['id']}"] = "100"
    campos = {f"i{ato}_{k}": v for k, v in dados.items()} | {f"incluir_{ato}": "1", "competencia": competencia}
    _mandar(casa, "/registro-imoveis/ctp", acao="salvar", **campos)
    _mandar(casa, "/registro-imoveis/ctp", acao="gerar", esperar=(200,), **campos)
    assert casa.um("SELECT 1 AS n FROM ri_ctp_remessas WHERE competencia=%s AND conteudo IS NOT NULL", (competencia,)), \
        "a CTP não gerou o arquivo"
    casa.pagina("ri_ctp_arquivo", competencia=competencia)
    _mandar(casa, "/registro-imoveis/doi", acao="gerar", competencia=competencia, esperar=(200,))
    assert casa.um("SELECT 1 AS n FROM ri_doi_remessas WHERE competencia=%s AND conteudo IS NOT NULL", (competencia,)), \
        "a DOI não gerou o arquivo"
    casa.pagina("ri_doi_arquivo", competencia=competencia)


def _conferencia(casa) -> None:
    import ri_conferencia as RC
    protocolo = _linha(casa, "SELECT id FROM cx_protocolos WHERE ri_protocolo_id=%s ORDER BY id DESC LIMIT 1",
                       (_id(casa, "ri_pren_com_documento"),))["id"]
    casa.inserir("cx_protocolo_atos", protocolo_id=int(protocolo), codigo_ato=RC.CODIGO_ATO, quantidade=2,
                 descricao="Conferência de documento eletrônico (ensaio)")
    quem = _quem(casa)
    with casa.transacao() as con:
        conferido = RC.conferir(con, protocolo, {"documentos": "CND federal de ensaio\nCND estadual de ensaio"})
        conferencia = RC.registrar(con, conferido, agora=casa.db.now(), usuario=quem)
    _selar_a_mao(casa, "ri_conferencias", int(conferencia))
    casa.pagina("ri_conferencia_comprovante", conferencia_id=int(conferencia))


def _qualificacao_ia(casa) -> None:
    import ri_qualificacao_ia as QIA
    quem = _quem(casa)
    from unittest.mock import patch
    # Gera apenas o historico ficticio; a pagina continua com a suspensao atual.
    with patch.object(QIA, "SUSPENSA_POR_BASE_NORMATIVA", False), casa.transacao() as con:
        pedido = QIA.pedir(con, _id(casa, "ri_pren_com_documento"), anexos_ids=[_id(casa, "_ri_anexo_do_titulo")],
                           usuario=quem)
    casa.pagina("ri_qualificacao_ia_ver", pedido_id=int(pedido))


def _retificacao(casa) -> None:
    e1 = _id(casa, "ri_mat_estruturada_aberta")
    _mandar(casa, "/registro-imoveis/retificacoes/nova", numero="RT-ENS-1/2026", matricula_id=str(e1),
            especie="GEORREFERENCIADA", fundamento="213_II", rural="0", requerente_nome="Ana Exemplo")
    processo = _linha(casa, "SELECT id FROM rt_processos WHERE numero=%s", ("RT-ENS-1/2026",))["id"]
    _mandar(casa, f"/registro-imoveis/retificacoes/{processo}/confrontante", nome="João Modelo", papel="CONFRONTANTE",
            endereco="Rua Exemplo, 10, Cidade Exemplo/MA", divisa_afetada="1")
    confrontante = _linha(casa, "SELECT id FROM rt_confrontantes WHERE processo_id=%s ORDER BY id LIMIT 1", (processo,))["id"]
    _mandar(casa, f"/registro-imoveis/retificacoes/{processo}/notificar", confrontante_id=str(confrontante),
            forma="PESSOAL", quando=casa.hoje, prazo_ate=(date.today() + timedelta(days=21)).isoformat())
    assert (_linha(casa, "SELECT teor_expedido FROM rt_confrontantes WHERE id=%s", (confrontante,))["teor_expedido"]
            or "").strip(), "a notificação não guardou o teor"
    casa.pagina("ri_retificacao", processo_id=int(processo))
    casa.pagina("ri_retificacao_notificacao_papel", {"formato": "odt"}, processo_id=int(processo),
                confrontante_id=int(confrontante))


def _onr(casa) -> None:
    import onr_certidoes as OC
    import onr_certidoes_auto as AUTO
    numero = _linha(casa, "SELECT numero FROM ri_matriculas WHERE id=%s", (_id(casa, "ri_mat_estruturada_com_ato"),))["numero"]
    xml = ('<?xml version="1.0" encoding="UTF-16"?><ROOT><PEDIDO><PROTOCOLO>C2026ENS01</PROTOCOLO>'
           '<TIPOCERTIDAO>3</TIPOCERTIDAO><STATUS>1</STATUS><NOMESOLICITANTE>CARLA EXEMPLO</NOMESOLICITANTE>'
           f'<MATRICULA>{numero}</MATRICULA></PEDIDO></ROOT>')
    with casa.transacao() as con:
        OC.guardar_pedidos(con, "PRODUCAO", xml, casa.db.now())
        AUTO.sincronizar(con, "PRODUCAO", casa.db.now())
    pedido = _linha(casa, "SELECT id FROM onr_cert_pedidos WHERE protocolo=%s", ("C2026ENS01",))["id"]
    casa.pagina("onr_certidao_ficha", pedido_id=int(pedido))
    casa.pagina("onr_auto_pedido", pedido_id=int(pedido))

    a1 = _id(casa, "ri_mat_acervo_aberta")
    r, recado = _mandar(casa, f"/ri/onr/endereco/da-matricula/{a1}")
    proposta = casa.um("SELECT id FROM ri_onr_enderecos WHERE matricula_id=%s", (a1,))
    assert proposta, f"a proposta de endereço não nasceu: {recado}"
    casa.pagina("ri_onr_endereco", proposta_id=int(proposta["id"]))


# ------------------------------------------------------------------ o usucapião

def _autuar_usucapiao(casa, numero: str, **campos) -> int:
    dados = {"numero": numero, "modalidade": "ORDINARIA", "requerente_nome": "Ana Exemplo",
             "requerente_documento": CPF, "imovel_descricao": "Lote urbano fictício, com 360 m², na Rua do Ensaio.",
             "imovel_municipio": "Cidade Exemplo", "imovel_area": "360 m²"} | campos
    _, recado = _mandar(casa, "/usucapiao/novo", **dados)
    achado = casa.um("SELECT id FROM us_processos WHERE numero=%s", (numero,))
    assert achado, f"o processo não foi autuado: {recado}"
    return int(achado["id"])


def _cumprir_o_checklist(casa, processo: int) -> None:
    import usucapiao as US
    with casa.con() as con:
        itens = [x["item"] for x in US.conferir(con, processo)["pendentes"]]
    for item in itens:
        _mandar(casa, f"/usucapiao/{processo}/conferencia", item=item, estado="DISPENSADO",
                motivo="Dispensado no ensaio do layout, com motivo escrito.")


def _decidir_procedente(casa, processo: int) -> None:
    _cumprir_o_checklist(casa, processo)
    _mandar(casa, f"/usucapiao/{processo}/decidir", sentido="PROCEDENTE",
            fundamento="Preenchidos os requisitos do rito, conforme o checklist do ensaio.",
            teor="DECISÃO. Reconhece-se a usucapião do imóvel, nos termos do requerimento, para os fins de registro.")
    assert casa.um("SELECT 1 AS n FROM us_decisoes WHERE processo_id=%s", (processo,)), "a decisão não foi lavrada"


def _usucapiao(casa) -> None:
    ano = casa.hoje[:4]
    autuado = _autuar_usucapiao(casa, f"US-ENS-1/{ano}")
    casa.ids["ri_us_autuado"] = autuado

    em_curso = _autuar_usucapiao(casa, f"US-ENS-2/{ano}")
    _mandar(casa, f"/usucapiao/{em_curso}/peca", tipo="REQUERIMENTO", descricao="Requerimento do interessado (ensaio)")
    assert casa.um("SELECT 1 AS n FROM us_pecas WHERE processo_id=%s", (em_curso,)), "a peça não foi juntada"
    _mandar(casa, f"/usucapiao/{em_curso}/etapa", etapa="CONFERENCIA")
    _mandar(casa, f"/usucapiao/{em_curso}/etapa", etapa="NOTIFICACAO")
    assert _linha(casa, "SELECT etapa FROM us_processos WHERE id=%s", (em_curso,))["etapa"] == "NOTIFICACAO"
    _mandar(casa, f"/usucapiao/{em_curso}/notificar", destinatario="João Modelo", destinatario_papel="Confrontante ao norte",
            endereco="Rua do Comércio, 45, Cidade Exemplo/MA", forma="PESSOAL", prazo_chave="CONFRONTANTE")
    notificacao = _linha(casa, "SELECT id FROM us_movimentos WHERE processo_id=%s AND tipo='NOTIFICACAO' ORDER BY id LIMIT 1",
                         (em_curso,))["id"]
    _mandar(casa, f"/usucapiao/{em_curso}/movimento", tipo="DILIGENCIA", descricao="Diligência de ensaio: aguardar a planta.",
            destinatario="Beatriz Exemplo", destinatario_papel="Requerente", prazo_dias="15",
            prazo_inicio=(date.today() - timedelta(days=45)).isoformat(),
            prazo_fim=(date.today() - timedelta(days=30)).isoformat())
    assert casa.um("SELECT 1 AS n FROM us_movimentos WHERE processo_id=%s AND tipo='DILIGENCIA'", (em_curso,)), \
        "a diligência com prazo vencido não foi lançada"
    _mandar(casa, f"/usucapiao/{em_curso}/analise", parecer="Parecer de ensaio: a posse parece mansa e pacífica.",
            ferramenta="ensaio do layout")
    assert casa.um("SELECT 1 AS n FROM us_analises WHERE processo_id=%s", (em_curso,)), "a análise não foi juntada"
    casa.ids["ri_us_em_curso"] = em_curso
    casa.pagina("usucapiao_dossie", processo_id=em_curso)
    casa.pagina("usucapiao_notificacao_papel", processo_id=em_curso, movimento_id=int(notificacao))
    casa.pagina("usucapiao_notificacao_arquivo", {"formato": "odt"}, processo_id=em_curso, movimento_id=int(notificacao))
    casa.pagina("ri_onr_edital", processo_id=em_curso)

    decidido = _autuar_usucapiao(casa, f"US-ENS-3/{ano}")
    _decidir_procedente(casa, decidido)
    assert _linha(casa, "SELECT situacao FROM us_processos WHERE id=%s", (decidido,))["situacao"] == "EM_ANDAMENTO"
    casa.ids["ri_us_decidido"] = decidido

    registrado = _autuar_usucapiao(casa, f"US-ENS-4/{ano}")
    _decidir_procedente(casa, registrado)
    _mandar(casa, f"/usucapiao/{registrado}/registrar", ato_id=str(_id(casa, "_ri_ato_r1_da_com_ato")))
    assert _linha(casa, "SELECT situacao FROM us_processos WHERE id=%s", (registrado,))["situacao"] == "REGISTRADO"
    casa.ids["ri_us_registrado"] = registrado

    rejeitado = _autuar_usucapiao(casa, f"US-ENS-5/{ano}")
    _mandar(casa, f"/usucapiao/{rejeitado}/decidir", sentido="IMPROCEDENTE",
            fundamento="Não há prova do tempo de posse exigido, conforme a conferência do ensaio.",
            teor="DECISÃO. Rejeita-se o pedido, por falta de prova do tempo de posse.")
    assert _linha(casa, "SELECT situacao FROM us_processos WHERE id=%s", (rejeitado,))["situacao"] == "REJEITADO"
    casa.ids["ri_us_rejeitado"] = rejeitado
    for chave in ("ri_us_autuado", "ri_us_em_curso", "ri_us_decidido", "ri_us_registrado", "ri_us_rejeitado"):
        casa.pagina("usucapiao_processo", processo_id=casa.ids[chave])


# ------------------------------------------------------------------ o Livro 3

def _registro_do_livro3(casa, **campos) -> int:
    antes = casa.um("SELECT COALESCE(MAX(id), 0) AS n FROM ra_registros")["n"]
    dados = {"natureza": "CEDULA_CREDITO_RURAL", "titulo_tipo": "Cédula rural pignoratícia",
             "titulo_numero": "CED-ENS-1", "data_titulo": casa.hoje, "valor": "150.000,00", "parcelas": "1",
             "vencimento_inicial": casa.hoje, "vencimento_final": (date.today() + timedelta(days=365)).isoformat(),
             "juros": "6% a.a.", "garantia": "Penhor de safra",
             "teor": "Cédula de crédito rural, registrada só para o ensaio do layout."} | campos
    _, recado = _mandar(casa, "/livro3/novo", **dados)
    novo = casa.um("SELECT id FROM ra_registros WHERE id > %s ORDER BY id LIMIT 1", (antes,))
    assert novo, f"o registro do Livro 3 não nasceu: {recado}"
    casa.pagina("livro3_registro", registro_id=int(novo["id"]))
    return int(novo["id"])


PARTES_DO_LIVRO3 = {"parte_nome": ["Mario Exemplo", "Carla Exemplo"], "parte_documento_tipo": ["CPF", ""],
                    "parte_documento": [CPF, ""], "parte_papel": ["EMITENTE", "CREDOR"]}


def _livro3(casa) -> None:
    sem_partes = _registro_do_livro3(casa, titulo_numero="CED-ENS-1")
    casa.ids["ri_l3_sem_partes_sem_selo"] = sem_partes

    completo = _registro_do_livro3(casa, titulo_numero="CED-ENS-2", selo=_selo(casa), **PARTES_DO_LIVRO3)
    _mandar(casa, f"/livro3/{completo}/lancar", tipo="AVERBACAO", teor="Averbação de aditivo ao prazo, só para o ensaio.",
            selo=_selo(casa))
    assert casa.um("SELECT 1 AS n FROM ra_atos WHERE registro_id=%s AND tipo='AV'", (completo,)), "a averbação não foi lançada"
    casa.ids["ri_l3_completo"] = completo
    termo = _linha(casa, "SELECT id FROM ra_atos WHERE registro_id=%s ORDER BY numero LIMIT 1", (completo,))["id"]
    _mandar(casa, f"/livro3/{completo}/digitalizacao", arquivo=_arquivo(_png(), "ficha-livro3.png"))
    _mandar(casa, f"/livro3/ato/{termo}/digitalizacao", arquivo=_arquivo(_png(), "termo-livro3.png"))
    assert _linha(casa, "SELECT digi_path FROM ra_registros WHERE id=%s", (completo,))["digi_path"]
    casa.pagina("livro3_baixar_digitalizacao", registro_id=completo)
    casa.pagina("livro3_miniatura_digitalizacao", registro_id=completo)
    casa.pagina("livro3_baixar_digitalizacao_do_ato", ato_id=int(termo))
    casa.pagina("livro3_conferir", registro_id=completo)
    casa.pagina("livro3_ficha_odt", registro_id=completo)

    cancelado = _registro_do_livro3(casa, titulo_numero="CED-ENS-3", selo=_selo(casa), **PARTES_DO_LIVRO3)
    _mandar(casa, f"/livro3/{cancelado}/lancar", tipo="CANCELAMENTO", motivo="Cédula quitada, só para o ensaio.",
            selo=_selo(casa))
    assert _linha(casa, "SELECT situacao FROM ra_registros WHERE id=%s", (cancelado,))["situacao"] == "CANCELADO"
    casa.ids["ri_l3_cancelado"] = cancelado

    com_minuta = _registro_do_livro3(casa, titulo_numero="CED-ENS-4", selo=_selo(casa), **PARTES_DO_LIVRO3)
    _mandar(casa, f"/livro3/{com_minuta}/lancar", tipo="AVERBACAO", teor="Averbação lavrada sem selo, para voltar à minuta.")
    sem_selo = _linha(casa, "SELECT id FROM ra_atos WHERE registro_id=%s ORDER BY numero DESC LIMIT 1", (com_minuta,))["id"]
    _mandar(casa, f"/livro3/ato/{sem_selo}/devolver-a-minuta", motivo="Devolvida à minuta, para o ensaio do layout.")
    expurgo = casa.um("SELECT id FROM ra_expurgos WHERE registro_id=%s ORDER BY id LIMIT 1", (com_minuta,))
    assert expurgo, "a devolução à minuta não gravou a ata de ocorrência"
    minuta = _linha(casa, "SELECT id FROM ra_minutas WHERE registro_id=%s ORDER BY id LIMIT 1", (com_minuta,))["id"]
    _mandar(casa, f"/livro3/{com_minuta}/revisoes", assunto="Conferir a cédula", nota="Conferir a cédula contra o papel, antes de selar.")
    casa.ids["ri_l3_com_minuta"] = com_minuta
    casa.pagina("livro3_como_ficara", registro_id=com_minuta, minuta_id=int(minuta))
    casa.pagina("livro3_expurgo_ata", expurgo_id=int(expurgo["id"]))


# ------------------------------------------------------------------ a semente

PASSOS = (_acervo, _numeracao, _estruturadas, _prenotacoes, _atos, _pendencias_da_ficha, _certidao, _digitalizacoes,
          _paginas_da_matricula, _ctp_e_doi, _conferencia, _qualificacao_ia, _retificacao, _onr, _usucapiao, _livro3)


def semear(casa) -> None:
    """Cada passo conta o que não conseguiu, e o fim junta tudo: uma rodada diz o que falta em todos."""
    falhas = []
    for passo in PASSOS:
        try:
            passo(casa)
        except Exception as erro:  # noqa: BLE001 - o fim diz qual passo e onde
            onde = [f"{q.filename.rsplit(chr(92), 1)[-1].rsplit('/', 1)[-1]}:{q.lineno}"
                    for q in traceback.extract_tb(erro.__traceback__)[-2:]]
            falhas.append(f"{passo.__name__}: {type(erro).__name__}: {str(erro)[:600]} [{' > '.join(onde)}]")
    assert not falhas, "a semente do ri não fechou:\n  " + "\n  ".join(falhas)
