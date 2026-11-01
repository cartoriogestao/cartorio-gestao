"""Semente da casa de ensaio: notas. Ver `layout_casa.py`.

O QUE SEMEIA
    Os atos de livro em cada estado do rito (procuração, substabelecimento, revogação,
    escritura com e sem imóvel, ata notarial: aberto, com partes, pronto para lançar,
    lançado, selado, lavrado), o cartão de autógrafo com ficha, foto e digital, o
    reconhecimento, a autenticação, o sinal público, a comunicação de venda de veículo, o
    lote e a consulta do CCN, a certidão, a pública forma, a leitura por IA, a revisão antes
    da lavratura, o pedido do agente de minutas e os livros. Cada estado do ato é um ato à
    parte, porque o estado é o que muda as fases da ficha. Três telas só mostram o
    formulário depois de uma busca (reconhecimento, reconhecimento de sinal, certidão): o
    endereço com a busca também é anotado.

O CAMINHO É O DA TELA, E SÓ CAI PARA A FUNÇÃO DE DOMÍNIO ONDE A TELA NÃO FECHA AQUI
    O ato nasce, ganha partes, teor, anexo e lançamento pelas rotas de verdade. A casa de
    ensaio não tem selador nem rede: o lançamento termina em «selo não saiu» (o ato fica
    SUSPENSO_SELO, com livro e folha reservados), e o selo entra digitado pelo quadro do
    selo, que é o caminho do balcão quando o aparelho cai. O cartão de autógrafo, o
    reconhecimento e o sinal selam sozinhos e desfazem o ato quando o selo falha, e por isso
    nascem pela função de domínio e pelo `inserir`. A IA é a de mentira que os testes do
    domínio já usam: responde pelo molde, sem rede.

OS SELOS DIGITADOS SÃO DESTA ÁREA E SÓ DELA: `<tipo>000000NTLAYOUT<seis dígitos>`. Outra
    área que digite o seu não esbarra neste, e o `UNIQUE` do razão não derruba a casa.

O MAPA DOS ATOS PARA O TESTE DAS FICHAS: `casa.ids["notas_ato_<chave>"]`, com as chaves de
    `CHAVES_DO_ATO`.
"""
from __future__ import annotations

import base64
import json
import re
from io import BytesIO

#: Rota com número que não tem como abrir aqui: endpoint -> o motivo.
SEM_SEMENTE: dict[str, str] = {}

# --------------------------------------------------------------------------- as pessoas

#: nome, CPF só com dígitos. Todos são documentos fictícios da lista do detector anti-vazamento.
PESSOAS = {
    "mario": ("Mario Exemplo", "00000000191"),
    "beatriz": ("Beatriz Exemplo", "00000000272"),
    "carla": ("Carla Exemplo", "00000000353"),
    "ana": ("Ana Exemplo", "00000001082"),
    "joao": ("João Modelo", "00000001163"),
}
QUALIFICACAO_DA_PESSOA = {
    "nacionalidade": "brasileira", "estado_civil": "solteira", "profissao": "comerciante",
    "tipo_pessoa": "F", "endereco": "Rua Exemplo, 10, Centro, Cidade Exemplo/MA",
    "identidade": "1234567 SSP/MA", "uniao_estavel": "NAO",
}

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"

_contador_de_selos = [0]


def _selo(prefixo: str) -> str:
    """Um selo digitado desta área, que nunca se repete: `PROCUR000000NTLAYOUT000001`."""
    _contador_de_selos[0] += 1
    return f"{prefixo}000000NTLAYOUT{_contador_de_selos[0]:06d}"


# --------------------------------------------------------------------------- o que cada rito tem

#: rito -> o que ele pede. `arquivamento`: o 13.30 é obrigatório (procuração e afins).
RITOS = {
    "PROC": {
        "modelo": "NT-PROC-PUBLICA", "tipo": "PROCURACAO", "item": "13.9.3", "selo": "PROCUR",
        "partes": (("mario", "OUTORGANTE"), ("beatriz", "OUTORGADO")), "arquivamento": True,
        "teor": ("<p>PROCURAÇÃO PÚBLICA. Saibam quantos esta virem que compareceu como outorgante "
                 "Mario Exemplo, brasileiro, solteiro, comerciante, CPF 000.000.001-91, que nomeia e "
                 "constitui sua bastante procuradora Beatriz Exemplo, brasileira, solteira, "
                 "comerciante, CPF 000.000.002-72, para representá-lo perante as repartições "
                 "públicas de Cidade Exemplo/MA. Lida esta procuração, a aceitaram e assinam. "
                 "Dou fé.</p>"),
    },
    "SUBST": {
        "modelo": "NT-SUBSTABELECIMENTO", "tipo": "SUBSTABELECIMENTO", "item": "13.9.5",
        "selo": "PROCUR",
        "partes": (("beatriz", "OUTORGANTE"), ("carla", "OUTORGADO")), "arquivamento": True,
        "teor": ("<p>SUBSTABELECIMENTO. Compareceu Beatriz Exemplo, brasileira, solteira, "
                 "comerciante, CPF 000.000.002-72, que substabelece, sem reserva de poderes, em "
                 "Carla Exemplo, brasileira, solteira, comerciante, CPF 000.000.003-53, os "
                 "poderes que lhe foram conferidos por Mario Exemplo. Lido este "
                 "substabelecimento, aceitaram e assinam. Dou fé.</p>"),
    },
    "REVOG": {
        "modelo": "NT-REVOGACAO-MANDATO", "tipo": "REVOGACAO", "item": "13.9.6", "selo": "PROCUR",
        "partes": (("mario", "OUTORGANTE"), ("beatriz", "OUTORGADO")), "arquivamento": True,
        "teor": ("<p>REVOGAÇÃO DE PROCURAÇÃO. Compareceu Mario Exemplo, brasileiro, solteiro, "
                 "comerciante, CPF 000.000.001-91, que revoga os poderes outorgados a Beatriz "
                 "Exemplo, brasileira, solteira, comerciante, CPF 000.000.002-72, devendo ela ser "
                 "notificada. Lida esta revogação, aceitou e assina. Dou fé.</p>"),
    },
    "ESC": {
        "modelo": "NT-ESC-COMPRA-VENDA", "tipo": "ESCRITURA", "item": "13.1", "selo": "ESCPUB",
        "partes": (("mario", "VENDEDOR"), ("ana", "COMPRADOR")), "arquivamento": False,
        "teor": ("<p>ESCRITURA PÚBLICA DE COMPRA E VENDA. Compareceram, como vendedor, Mario "
                 "Exemplo, brasileiro, solteiro, comerciante, CPF 000.000.001-91, e, como "
                 "compradora, Ana Exemplo, brasileira, solteira, comerciante, CPF "
                 "000.000.010-82, que ajustam a venda do lote 10 da quadra 3, em Cidade "
                 "Exemplo/MA, livre de ônus. Lida esta escritura, aceitaram e assinam. "
                 "Dou fé.</p>"),
    },
    "ESCSI": {
        "modelo": "NT-ESC-PACTO-ANTENUPCIAL", "tipo": "ESCRITURA", "item": "13.1", "selo": "ESCPUB",
        "partes": (("joao", "OUTORGANTE"), ("ana", "OUTORGANTE")), "arquivamento": False,
        "teor": ("<p>ESCRITURA PÚBLICA DE PACTO ANTENUPCIAL. Compareceram João Modelo, brasileiro, "
                 "solteiro, comerciante, CPF 000.000.011-63, e Ana Exemplo, brasileira, solteira, "
                 "comerciante, CPF 000.000.010-82, que pactuam o regime da separação total de "
                 "bens. Lida esta escritura, aceitaram e assinam. Dou fé.</p>"),
    },
    "ATA": {
        "modelo": "NT-ATA-NOTARIAL", "tipo": "ATA", "item": "13.14.1", "selo": "ATANOT",
        "partes": (("carla", "SOLICITANTE"),), "arquivamento": False,
        "teor": ("<p>ATA NOTARIAL. A pedido de Carla Exemplo, brasileira, solteira, comerciante, "
                 "CPF 000.000.003-53, constatei que o muro da frente do imóvel da Rua Exemplo, "
                 "10, em Cidade Exemplo/MA, está pintado de branco e sem rachaduras, como mostram "
                 "as fotografias anexas. Lida esta ata, a solicitante aceitou e assina. "
                 "Dou fé.</p>"),
    },
}

#: Os estados de cada ato, na ordem do rito. Cada um é um ato à parte.
DEGRAUS = ("aberta", "partes", "pronta", "lancada", "selada", "lavrada")

#: chave -> (rito, degrau). A chave é o que o teste das fichas procura em `casa.ids`.
#: Onde o degrau não diz tudo, o nome diz (a variação está em `_construir`):
#:   proc_partes_incompletas / proc_teor_incompleto: prontos, menos uma qualificação ou um claro
#:   esc_com_doi / esc_lavrada_doi_pendente: a DOI preenchida, ou preenchida pela metade
#:   subst_com_origem / subst_com_oficio: a procuração é de outra serventia (art. 831, § 1º)
#:   proc_sem_modelo: aberta sem modelo do sistema, e por isso com o quadro «Montar com as partes»
ATOS_DO_RITO = {
    "proc_aberta": ("PROC", "aberta"),
    "proc_partes": ("PROC", "partes"),
    "proc_sem_modelo": ("PROC", "partes"),
    "proc_partes_incompletas": ("PROC", "pronta"),
    "proc_teor_incompleto": ("PROC", "pronta"),
    "proc_pronta": ("PROC", "pronta"),
    "proc_lancada": ("PROC", "lancada"),
    "proc_selada": ("PROC", "selada"),
    "proc_lavrada": ("PROC", "lavrada"),
    "subst_aberta": ("SUBST", "aberta"),
    "subst_pronta": ("SUBST", "pronta"),
    "subst_com_origem": ("SUBST", "lancada"),
    "subst_com_oficio": ("SUBST", "lancada"),
    "subst_lavrada": ("SUBST", "lavrada"),
    "revog_aberta": ("REVOG", "aberta"),
    "revog_pronta": ("REVOG", "pronta"),
    "revog_lavrada": ("REVOG", "lavrada"),
    "esc_aberta": ("ESC", "aberta"),
    "esc_pronta": ("ESC", "pronta"),
    "esc_com_doi": ("ESC", "pronta"),
    "esc_lancada": ("ESC", "lancada"),
    "esc_lavrada_doi_pendente": ("ESC", "lavrada"),
    "esc_lavrada": ("ESC", "lavrada"),
    "escsi_aberta": ("ESCSI", "aberta"),
    "escsi_pronta": ("ESCSI", "pronta"),
    "ata_aberta": ("ATA", "aberta"),
    "ata_pronta": ("ATA", "pronta"),
    "ata_lavrada": ("ATA", "lavrada"),
}
CHAVES_DO_ATO = tuple(ATOS_DO_RITO) + ("proc_da_base", "proc_do_agente")

#: A serventia de onde vem a procuração substabelecida: outra, com outro CNS (999999 é fictício).
ORIGEM_DA_PROCURACAO = {
    "cartorio": "2º Tabelionato de Notas de Cidade Exemplo/MA", "cns": "999999",
    "cidade": "Cidade Exemplo", "uf": "MA", "livro": "12", "folha": "30", "data": "2025-03-10",
}


# --------------------------------------------------------------------------- o envio pela tela

def _recados(casa, c, r) -> str:
    """O que a tela disse depois do envio: serve para a recusa explicar por que não andou."""
    import layout_ensaio as E
    destino = r.headers.get("Location") or ""
    if not destino:
        return f"HTTP {r.status_code}"
    pagina = E.ler_pagina(c.get(destino).get_data(as_text=True))
    return " | ".join(f"{classe}: {texto}" for classe, texto in pagina.flashes) or "sem recado"


def _enviar(casa, c, destino: str, o_que: str, /, **campos):
    """Manda o formulário como a tela manda. `casa.postar` tem um parâmetro `endereco`, e o
    formulário da parte tem um campo `endereco`: por isso o envio é feito aqui."""
    r = c.post(destino, data={"csrf_token": casa.token(c), **campos})
    assert r.status_code in (302, 303), f"{o_que}: HTTP {r.status_code} em {destino}"
    return r


def _admin(casa) -> dict:
    return casa.um("SELECT id, full_name FROM users WHERE id=%s", (casa.ids["admin"],))


def _ato(casa, ato_id: int) -> dict:
    return casa.um("SELECT * FROM nt_atos WHERE id=%s", (ato_id,))


def _abrir(casa, c, modelo: str, tipo: str = "") -> int:
    """Sem modelo, o tipo do ato vem do formulário; com modelo, é o modelo que o manda."""
    r = _enviar(casa, c, "/notas/atos/novo", f"abrir {modelo or tipo}", tipo=tipo, modelo_codigo=modelo,
                interessado="Mario Exemplo")
    achado = re.search(r"/notas/atos/(\d+)$", r.headers.get("Location", ""))
    assert achado, f"abrir {modelo or tipo} levou a {r.headers.get('Location')}: {_recados(casa, c, r)}"
    return int(achado.group(1))


def _incluir_parte(casa, c, ato_id: int, pessoa: str, qualificacao: str,
                   cartao_id: int | None = None) -> None:
    nome, cpf = PESSOAS[pessoa]
    if cartao_id is None:
        r = _enviar(casa, c, f"/notas/atos/{ato_id}", f"parte {nome}", acao="parte_nova", nome=nome,
                    documento=cpf, qualificacao=qualificacao, **QUALIFICACAO_DA_PESSOA)
    else:
        # a parte que já tem cartão de autógrafo se aproveita da ficha de firma
        r = _enviar(casa, c, f"/notas/atos/{ato_id}", f"parte {nome} pelo cartão",
                    acao="parte_cartao", cartao_id=str(cartao_id), qualificacao=qualificacao,
                    uniao_estavel="NAO")
    assert casa.um("SELECT 1 AS n FROM nt_ato_partes WHERE ato_id=%s AND nome=%s", (ato_id, nome)), (
        f"a parte {nome} não entrou: {_recados(casa, c, r)}")


def _escrever_o_teor(casa, c, ato_id: int, html: str) -> None:
    r = _enviar(casa, c, f"/notas/atos/{ato_id}", "teor", acao="teor", teor=html)
    assert (_ato(casa, ato_id)["teor"] or "").strip(), f"o teor não ficou: {_recados(casa, c, r)}"


def _anexar(casa, c, ato_id: int, descricao: str = "Documento de identificação do outorgante",
            nome: str = "identidade.png", conteudo: bytes = PNG) -> int:
    r = _enviar(casa, c, f"/notas/atos/{ato_id}/anexos", "anexo", descricao=descricao,
                arquivo=(BytesIO(conteudo), nome))
    anexo = casa.um("SELECT id FROM attachments WHERE entity_type='NT_ATO' AND entity_id=%s "
                    "AND original_name=%s ORDER BY id DESC LIMIT 1", (ato_id, nome))
    assert anexo, f"o anexo não entrou: {_recados(casa, c, r)}"
    return int(anexo["id"])


def _confirmar_as_folhas(casa, c, ato_id: int) -> None:
    r = _enviar(casa, c, f"/notas/atos/{ato_id}", "folhas do arquivamento",
                acao="confirmar_arquivamento", folhas_arquivamento="1")
    assert _ato(casa, ato_id)["arquivamento_confirmado_em"], (
        f"as folhas não foram confirmadas: {_recados(casa, c, r)}")


def _valor(casa, c, ato_id: int, centavos: int) -> None:
    r = _enviar(casa, c, f"/notas/escrituras/{ato_id}/valor", "valor", valor=str(centavos),
                voltar="ato")
    assert _ato(casa, ato_id)["valor_transacao"] == centavos, (
        f"o valor não ficou: {_recados(casa, c, r)}")


def _doi(casa, c, ato_id: int) -> None:
    """O quadro da DOI, completo: operação, matrícula, endereço, área e a participação de cada lado."""
    campos = {"acao": "imovel", "com_imovel": "1", "doi_transacao": "11",
              "doi_matricula": "1234", "doi_endereco": "Rua Exemplo, 10, Centro, Cidade Exemplo/MA",
              "doi_area": "360"}
    for parte in casa.ler("SELECT id FROM nt_ato_partes WHERE ato_id=%s ORDER BY id", (ato_id,)):
        campos[f"participacao_{parte['id']}"] = "100"
    r = _enviar(casa, c, f"/notas/atos/{ato_id}", "DOI", **campos)
    assert _ato(casa, ato_id)["com_imovel"] == 1, f"a DOI não ficou: {_recados(casa, c, r)}"


def _lancar(casa, c, ato_id: int, item: str, paginas: int) -> None:
    r = _enviar(casa, c, f"/notas/atos/{ato_id}", "lançamento", acao="lancar", codigo_tj=item,
                paginas=str(paginas))
    a = _ato(casa, ato_id)
    assert a["termo"] is not None and a["livro"], f"o ato não foi lançado: {_recados(casa, c, r)}"


def _selar(casa, c, ato_id: int, prefixo: str) -> None:
    r = _enviar(casa, c, f"/notas/atos/{ato_id}", "selo do ato", acao="selo", selo=_selo(prefixo))
    assert (_ato(casa, ato_id)["selo"] or "").strip(), f"o selo não entrou: {_recados(casa, c, r)}"


def _selar_o_arquivamento(casa, c, ato_id: int) -> None:
    r = _enviar(casa, c, f"/notas/atos/{ato_id}", "selo de arquivamento",
                acao="selo_arquivamento", selo_arquivamento=_selo("ARQUIV"))
    assert (_ato(casa, ato_id)["selo_arquivamento"] or "").strip(), (
        f"o selo de arquivamento não entrou: {_recados(casa, c, r)}")


def _incluir_parte_sem_qualificacao(casa, c, ato_id: int, pessoa: str, qualificacao: str) -> None:
    """A parte que o balcão incluiu só com o nome e o CPF: falta a qualificação do CC, art. 215."""
    nome, cpf = PESSOAS[pessoa]
    _enviar(casa, c, f"/notas/atos/{ato_id}", f"parte {nome} sem qualificação", acao="parte_nova",
            nome=nome, documento=cpf, qualificacao=qualificacao, tipo_pessoa="F")


def _informar_a_origem(casa, c, ato_id: int) -> None:
    r = _enviar(casa, c, f"/notas/atos/{ato_id}/comunicacao-origem", "origem da procuração",
                acao="origem", **ORIGEM_DA_PROCURACAO)
    assert _ato(casa, ato_id)["anterior_cartorio"], f"a origem não ficou: {_recados(casa, c, r)}"


def _anotar_o_oficio(casa, c, ato_id: int) -> None:
    r = _enviar(casa, c, f"/notas/atos/{ato_id}/comunicacao-origem", "ofício à origem",
                acao="oficio", envio_data=casa.hoje, envio_meio="CARTA_REGISTRADA",
                envio_numero="OF-001/2026", envio_por=_admin(casa)["full_name"])
    situacao = casa.um("SELECT situacao FROM nt_comunicacoes_origem WHERE ato_id=%s", (ato_id,))
    assert situacao and situacao["situacao"] == "CUMPRIDA", (
        f"o ofício não baixou a comunicação: {_recados(casa, c, r)}")


def _construir(casa, c, chave: str) -> int:
    rito, degrau = ATOS_DO_RITO[chave]
    d = RITOS[rito]
    ate = DEGRAUS.index(degrau)
    ato_id = _abrir(casa, c, "", d["tipo"]) if chave == "proc_sem_modelo" else _abrir(casa, c, d["modelo"])
    if ate >= DEGRAUS.index("partes"):
        for pessoa, qualificacao in d["partes"]:
            if chave == "proc_partes_incompletas" and pessoa == "beatriz":
                _incluir_parte_sem_qualificacao(casa, c, ato_id, pessoa, qualificacao)
                continue
            # o outorgante da procuração lavrada vem do cartão de autógrafo dele
            cartao = (casa.ids.get("notas_cartao_mario")
                      if chave == "proc_lavrada" and pessoa == "mario" else None)
            _incluir_parte(casa, c, ato_id, pessoa, qualificacao, cartao)
    if ate >= DEGRAUS.index("pronta"):
        teor = d["teor"]
        if chave == "proc_teor_incompleto":
            teor = teor.replace("para representá-lo", "pelo prazo de [PRAZO DO MANDATO], para representá-lo")
        _escrever_o_teor(casa, c, ato_id, teor)
        if rito == "ATA":
            _anexar(casa, c, ato_id, "Fotografia do muro, tirada pelo tabelião às 10h", "muro.png")
        if d["arquivamento"]:
            _anexar(casa, c, ato_id)
            _confirmar_as_folhas(casa, c, ato_id)
        if d["tipo"] == "ESCRITURA":
            _valor(casa, c, ato_id, 15000000 if chave == "esc_com_doi" else 0)
        if chave in ("esc_com_doi", "esc_lavrada_doi_pendente", "esc_lavrada"):
            _doi(casa, c, ato_id)
    if chave in ("subst_com_origem", "subst_com_oficio"):
        _informar_a_origem(casa, c, ato_id)
    if ate >= DEGRAUS.index("lancada"):
        # um número ímpar de páginas deixa o verso da folha para inutilizar
        _lancar(casa, c, ato_id, d["item"], 1 if chave == "proc_lancada" else 2)
    if chave in ("subst_com_origem", "subst_com_oficio"):
        assert casa.um("SELECT 1 AS n FROM nt_comunicacoes_origem WHERE ato_id=%s", (ato_id,)), (
            "o lançamento não fez nascer a obrigação de comunicar a serventia de origem")
    if chave == "subst_com_oficio":
        _anotar_o_oficio(casa, c, ato_id)
    if ate >= DEGRAUS.index("selada"):
        _selar(casa, c, ato_id, d["selo"])
    if ate >= DEGRAUS.index("lavrada") and d["arquivamento"]:
        _selar_o_arquivamento(casa, c, ato_id)
    if chave == "esc_lavrada":
        # o valor entra depois do livro, como na tela das escrituras pendentes: o lançamento
        # com valor pede a tabela de custas, que a casa de ensaio não tem
        _valor(casa, c, ato_id, 15000000)
    casa.ids[f"notas_ato_{chave}"] = ato_id
    casa.pagina("notas_ato", ato_id=ato_id)
    return ato_id


# --------------------------------------------------------------------------- os passos

def passo_sdk_do_leitor(casa) -> None:
    """O SDK da digital é do fabricante e o TI o instala: aqui entram dois arquivos de mentira."""
    import leitor_digital as LD
    pasta = LD.pasta_do_sdk(casa.db.get_setting(LD.CHAVE_DA_PASTA, ""), casa.boot["data_dir"])
    pasta.mkdir(parents=True, exist_ok=True)
    for nome in LD.ARQUIVOS_DO_SDK:
        (pasta / nome).write_text("/* SDK do fabricante, de mentira: a casa de ensaio não o instala */\n",
                                  encoding="utf-8")
        casa.pagina("notas_leitor_digital_sdk", nome=nome)


def _dados_do_cartao(pessoa: str, sexo: str) -> dict:
    nome, cpf = PESSOAS[pessoa]
    return {"nome": nome, "documento": cpf, "rg": "1234567", "rg_orgao": "SSP", "rg_uf": "MA",
            "rg_emissao": "2015-03-06", "nascimento": "1980-05-02", "sexo": sexo,
            "nacionalidade": "brasileira", "naturalidade": "Cidade Exemplo/MA",
            "estado_civil": "solteiro(a)", "profissao": "comerciante", "pai": "João Modelo",
            "mae": "Ana Exemplo" if pessoa != "ana" else "Carla Exemplo",
            "endereco": "Rua Exemplo", "endereco_numero": "10", "bairro": "Centro",
            "cidade": "Cidade Exemplo", "uf": "MA", "cep": "65936000", "celular": "99988880000",
            "email": "exemplo@exemplo.invalid"}


def passo_cartoes(casa) -> None:
    import ato_selado as AS
    import notas_partes as NP
    c = casa.cliente("ADMIN", "novo")
    admin = _admin(casa)
    agora = casa.db.now()
    cns = casa.db.get_setting("ri_cns", "")
    with casa.transacao() as con:
        for pessoa, sexo in (("mario", "M"), ("beatriz", "F"), ("carla", "F"), ("ana", "F")):
            cid = NP.criar_cartao(con, _dados_do_cartao(pessoa, sexo), agora, admin["full_name"],
                                  "Escrevente")
            casa.ids[f"notas_cartao_{pessoa}"] = cid
            if pessoa in ("mario", "beatriz"):
                # o cartão sela na abertura; sem aparelho, o selo entra digitado
                AS.registrar_selo_obtido_a_mao(con, _selo("CARTAO"), tabela="nt_cartoes", ato_id=cid,
                                               atribuicao="NOTAS", agora=agora, cns=cns,
                                               usuario=admin["full_name"])
    for pessoa in ("mario", "beatriz", "carla", "ana"):
        casa.pagina("notas_cartao", cartao_id=casa.ids[f"notas_cartao_{pessoa}"])

    mario, beatriz, ana = (casa.ids[f"notas_cartao_{p}"] for p in ("mario", "beatriz", "ana"))
    # a ficha digitalizada, pela tela do cartão
    for cartao in (mario, beatriz):
        _enviar(casa, c, f"/notas/cartoes/{cartao}/fichas", "ficha do cartão", favorita="1",
                data_coleta=casa.hoje, ficha=(BytesIO(PNG), f"ficha-{cartao}.png"))
        imagem = casa.um("SELECT id FROM nt_cartao_imagens WHERE cartao_id=%s ORDER BY id LIMIT 1",
                         (cartao,))
        assert imagem, f"a ficha do cartão {cartao} não entrou"
        if cartao == mario:
            casa.pagina("notas_cartao_imagem", imagem_id=imagem["id"])
            casa.pagina("notas_cartao_imagem_original", imagem_id=imagem["id"])
    # a foto e a digital (esta só depois da ciência da pessoa)
    _enviar(casa, c, f"/notas/cartoes/{mario}/foto", "foto do cadastro", foto=(BytesIO(PNG), "foto.jpg"))
    _enviar(casa, c, f"/notas/cartoes/{mario}/biometria/ciencia", "ciência da digital", confirmo="1")
    _enviar(casa, c, f"/notas/cartoes/{mario}/digital", "digital do cadastro", dedo="2",
            digital=(BytesIO(PNG), "digital.png"))
    assert casa.um("SELECT COUNT(*) AS n FROM nt_cadastro_imagens WHERE cartao_id=%s", (mario,))["n"] == 2
    casa.pagina("notas_cartao_foto", cartao_id=mario)
    casa.pagina("notas_cartao_digital", cartao_id=mario, dedo=2)
    # a ficha para imprimir: uma com selo (o carimbo) e uma sem
    casa.pagina("notas_cartao_ficha", cartao_id=mario)
    casa.pagina("notas_cartao_ficha", cartao_id=casa.ids["notas_cartao_carla"])
    # o cartão bloqueado
    _enviar(casa, c, f"/notas/cartoes/{ana}", "bloquear o cartão", acao="bloquear",
            motivo="Documento em conferência, cartão bloqueado para o ensaio.")
    assert casa.um("SELECT bloqueado FROM nt_cartoes WHERE id=%s", (ana,))["bloqueado"] == 1


def passo_atos(casa) -> None:
    c = casa.cliente("ADMIN", "novo")
    for chave in ATOS_DO_RITO:
        _construir(casa, c, chave)


def passo_ato_da_base(casa) -> None:
    """A procuração lavrada que a carga de demonstração já traz."""
    from tools import carga_de_demonstracao as CARGA
    achado = casa.um("SELECT id FROM nt_atos WHERE origem='MANUAL' AND origem_chave=%s",
                     (CARGA.MARCA_PROCURACAO,))
    assert achado, "a carga de demonstração não trouxe a procuração"
    casa.ids["notas_ato_proc_da_base"] = int(achado["id"])
    casa.pagina("notas_ato", ato_id=int(achado["id"]))


def passo_arquivos_dos_atos(casa) -> None:
    """Termo do livro, traslado, rascunho do teor e a face a inutilizar: só o ato lançado os tem."""
    ids = casa.ids
    # o traslado muda de rótulo e de carimbo com a espécie do ato; o termo do livro é um só
    for chave in ("proc_lavrada", "esc_lavrada", "ata_lavrada"):
        casa.pagina("notas_ato_traslado", ato_id=ids[f"notas_ato_{chave}"])
    for chave in ("proc_lavrada", "esc_lavrada"):
        casa.pagina("notas_ato_termo_livro", ato_id=ids[f"notas_ato_{chave}"])
    # o rascunho do teor sai antes e depois do livro
    for chave in ("proc_pronta", "proc_lavrada"):
        casa.pagina("notas_ato_teor_odt", ato_id=ids[f"notas_ato_{chave}"])
    # lançada com uma página só: o verso da folha sobra e sai inutilizado
    casa.pagina("notas_ato_inutilizacao", ato_id=ids["notas_ato_proc_lancada"])


def passo_livros(casa) -> None:
    c = casa.cliente("ADMIN", "novo")
    # o livro das procurações abriu sozinho no primeiro lançamento
    aberto = casa.um("SELECT id FROM nt_livros WHERE tipo='PROCURACAO' ORDER BY id LIMIT 1")
    assert aberto, "nenhum livro de procurações abriu com os lançamentos"
    casa.pagina("notas_livro_termo", livro_id=aberto["id"], qual="abertura")
    casa.pagina("notas_livro_conferir", livro_id=aberto["id"])
    # um livro de testamentos aberto e encerrado sem ato: as dez folhas ficam inutilizadas
    _enviar(casa, c, "/notas/livros", "abrir o livro", acao="abrir", tipo="TESTAMENTO",
            numero="1", folhas="10")
    livro = casa.um("SELECT id FROM nt_livros WHERE tipo='TESTAMENTO' ORDER BY id DESC LIMIT 1")
    assert livro, "o livro de testamentos não abriu"
    _enviar(casa, c, "/notas/livros", "encerrar o livro", acao="encerrar", livro_id=str(livro["id"]),
            motivo="livro de ensaio, encerrado sem ato")
    assert casa.um("SELECT folhas_inutilizadas FROM nt_livros WHERE id=%s",
                   (livro["id"],))["folhas_inutilizadas"], "o livro encerrado não inutilizou folhas"
    casa.pagina("notas_livro_termo", livro_id=livro["id"], qual="abertura")
    casa.pagina("notas_livro_termo", livro_id=livro["id"], qual="encerramento")
    casa.pagina("notas_livro_inutilizacao", livro_id=livro["id"])
    casa.pagina("notas_livro_conferir", livro_id=livro["id"])


def passo_remessas(casa) -> None:
    for central in ("CEP", "CESDI", "RCTO"):
        casa.pagina("notas_remessa_pendencias", central=central)


def passo_sinais(casa) -> None:
    import ato_selado as AS
    from notas_schema import SERVICOS, texto_reconhecimento_sinal
    c = casa.cliente("ADMIN", "novo")
    admin = _admin(casa)
    agora = casa.db.now()
    # um sinal com o PDF da central, e outro ainda sem ele
    for titular, cpf, com_pdf in (("Mario Exemplo", "00000000191", True),
                                  ("Beatriz Exemplo", "00000000272", False)):
        campos = {"acao": "novo", "titular": titular, "documento": cpf, "origem": "CENSEC",
                  "observacao": "Sinal de ensaio."}
        if com_pdf:
            campos["pdf"] = (BytesIO(PDF), "sinal.pdf")
        r = _enviar(casa, c, "/notas/sinais", f"sinal de {titular}", **campos)
        achado = re.search(r"/notas/sinais/(\d+)$", r.headers.get("Location", ""))
        assert achado, f"o sinal de {titular} não abriu: {_recados(casa, c, r)}"
        sinal = int(achado.group(1))
        casa.ids[f"notas_sinal_{titular.split()[0].lower()}"] = sinal
        casa.pagina("notas_sinal", sinal_id=sinal)
        if com_pdf:
            assert casa.um("SELECT caminho_pdf FROM nt_sinais_publicos WHERE id=%s",
                           (sinal,))["caminho_pdf"], "o PDF do sinal não ficou"
            casa.pagina("notas_sinal_pdf", sinal_id=sinal)
    # o reconhecimento do sinal sela sozinho e some se o selo falha: nasce pela função de domínio
    sinal = casa.ids["notas_sinal_mario"]
    texto = texto_reconhecimento_sinal("Mario Exemplo", con=casa.db.connect)
    rid = casa.inserir("nt_sinais_reconhecimentos", sinal_id=sinal, data=casa.hoje, hora="10:40:00",
                       servico_codigo=SERVICOS["SINAL"], documento_descricao="Declaração de exemplo",
                       texto=texto, oficial=admin["full_name"], oficial_funcao="Escrevente",
                       origem="MANUAL", criado_em=agora, criado_por=admin["full_name"])
    with casa.transacao() as con:
        AS.registrar_selo_obtido_a_mao(con, _selo("RECFIR"), tabela="nt_sinais_reconhecimentos",
                                       ato_id=rid, atribuicao="NOTAS", agora=agora,
                                       cns=casa.db.get_setting("ri_cns", ""),
                                       usuario=admin["full_name"])
    assert casa.um("SELECT selo FROM nt_sinais_reconhecimentos WHERE id=%s", (rid,))["selo"]
    casa.ids["notas_sinal_reconhecimento"] = rid
    casa.pagina("notas_sinal_reconhecimento_ver", reconhecimento_id=rid)
    casa.pagina("notas_sinal_reconhecimento", _consulta={"busca": "Mario"})


def passo_veiculo(casa) -> None:
    c = casa.cliente("ADMIN", "novo")
    r = _enviar(casa, c, "/notas/veiculos/nova", "comunicação de venda de veículo",
                documento="ATPV_E", placa="ABC1D23", renavam="00639884962",
                vendedor_nome="Mario Exemplo", vendedor_documento="00000000191",
                comprador_nome="Beatriz Exemplo", comprador_documento="00000000272",
                data_venda=casa.hoje, valor="25.000,00", municipio="Cidade Exemplo", uf="MA")
    achado = re.search(r"/notas/veiculos/(\d+)$", r.headers.get("Location", ""))
    assert achado, f"a comunicação não nasceu: {_recados(casa, c, r)}"
    casa.ids["notas_veiculo"] = int(achado.group(1))
    casa.pagina("notas_veiculo", com_id=int(achado.group(1)))


def passo_reconhecimentos(casa) -> None:
    from notas_schema import SERVICOS, texto_reconhecimento
    c = casa.cliente("ADMIN", "novo")
    admin = _admin(casa)
    agora = casa.db.now()
    ids = casa.ids
    # o reconhecimento sela sozinho e desfaz o ato se o selo falha: nasce pelo `inserir`, e o
    # selo entra digitado pela ficha dele
    casos = (("SEMELHANCA", (("mario", "notas_cartao_mario"),), True),
             ("AUTENTICIDADE", (("beatriz", "notas_cartao_beatriz"), ("carla", "notas_cartao_carla")),
              False))
    for especie, firmas, com_selo in casos:
        nomes = [PESSOAS[p][0] for p, _ in firmas]
        rid = casa.inserir("nt_reconhecimentos", data=casa.hoje, hora="10:15", especie=especie,
                           servico_codigo=SERVICOS[especie], quantidade=len(firmas),
                           documento_descricao="Contrato de exemplo",
                           texto=texto_reconhecimento(especie, nomes, False, con=casa.db.connect),
                           oficial=admin["full_name"], oficial_funcao="Escrevente", origem="MANUAL",
                           criado_em=agora, criado_por=admin["full_name"])
        for pessoa, chave in firmas:
            casa.inserir("nt_reconhecimento_partes", reconhecimento_id=rid, cartao_id=ids[chave],
                         nome=PESSOAS[pessoa][0], documento=PESSOAS[pessoa][1], criado_em=agora)
        if com_selo:
            _enviar(casa, c, f"/notas/reconhecimento/{rid}", "selo do reconhecimento", acao="selo",
                    selo=_selo("RECFIR"))
            assert casa.um("SELECT selo FROM nt_reconhecimentos WHERE id=%s", (rid,))["selo"]
        ids[f"notas_reconhecimento_{especie.lower()}"] = rid
        casa.pagina("notas_reconhecimento_ver", reconhecimento_id=rid)
    # o balcão procura o cartão pelo nome, e só então a tela oferece o formulário de reconhecer
    casa.pagina("notas_reconhecimento", _consulta={"busca": "Mario"})


def passo_autenticacoes(casa) -> None:
    """A autenticação sela sozinha e some se o selo falha: nasce pelo `inserir`. Uma fica sem selo
    (a lista oferece pedi-lo) e a outra recebe o digitado pela tela dela (a lista oferece a etiqueta)."""
    from notas_schema import SERVICOS
    c = casa.cliente("ADMIN", "novo")
    admin = _admin(casa)
    agora = casa.db.now()
    for com_selo in (False, True):
        aid = casa.inserir("nt_autenticacoes", data=casa.hoje, hora="10:20", tipo="PADRAO",
                           servico_codigo=SERVICOS["AUTENTICACAO"], folhas=1,
                           documento_descricao="Contrato de exemplo", apresentante="Mario Exemplo",
                           texto="Confere com o original apresentado.", oficial=admin["full_name"],
                           oficial_funcao="Escrevente", origem="MANUAL", criado_em=agora,
                           criado_por=admin["full_name"])
        if com_selo:
            _enviar(casa, c, f"/notas/autenticacao/{aid}/selo", "selo da autenticação", selo=_selo("AUTENT"))
            assert casa.um("SELECT selo FROM nt_autenticacoes WHERE id=%s", (aid,))["selo"], (
                "o selo da autenticação não entrou")
        casa.ids[f"notas_autenticacao_{'selada' if com_selo else 'sem_selo'}"] = aid


#: A ficha que o CCN devolve, com os nomes da casa. O formato é o do contrato do CCN.
FICHA_DO_CCN = {
    "id": "11111111-1111-1111-1111-111111111111", "cpf": "00000000191", "name": "MARIO EXEMPLO",
    "subscriptionName": "CARTORIO EXEMPLO",
    "notary": {"name": "1º TABELIONATO DE CIDADE EXEMPLO", "cns": 1},
    "dateCreated": "2024-02-01T09:00:00", "gender": "Male", "dateOfBirth": "1980-05-02T00:00:00",
    "email": "Mario@Exemplo.invalid", "profession": "lavrador", "civilStatus": "Casado",
    "spouseName": "Beatriz Exemplo", "maritalPropertySystem": "RegimeOfPartialCommunityProperty",
    "motherName": "Ana Exemplo", "fatherName": "João Modelo", "documentType": "IdCard",
    "documentNumber": "123456", "documentIssuer": "ssp", "documentIssueDate": "2015-03-06T00:00:00",
    "documentIssuerState": "MA", "nationality": "Brazilian", "birthCity": "Cidade Exemplo",
    "birthState": "MA",
    "address": {"street": "Rua Grande", "number": "10", "neighbourhood": "Centro",
                "city": "Cidade Exemplo", "state": "MA", "zipCode": "65.936-000"},
    "phones": [{"type": "Home", "number": "(99) 3571-0000"},
               {"type": "Mobile", "number": "+55 99 98888-0000", "primaryMobilePhone": True}],
    "politicallyExposed": True, "investigatedOrAccusedOfTerrorism": False, "blocked": False,
    "files": [{"type": "Documento", "name": "rg.pdf", "contentType": "application/pdf"}],
    "fingerPrints": [{"type": "RightThumb"}],
}


def passo_ccn(casa) -> None:
    import ccn_consulta as CQ
    c = casa.cliente("ADMIN", "novo")
    # o lote: todo cartão com CPF e ficha que ainda não foi aceito
    r = _enviar(casa, c, "/notas/ccn/lotes", "lote do CCN", ambiente="HOMOLOGACAO")
    achado = re.search(r"/notas/ccn/lotes/(\d+)$", r.headers.get("Location", ""))
    assert achado, f"o lote do CCN não nasceu: {_recados(casa, c, r)}"
    lote = int(achado.group(1))
    casa.ids["notas_ccn_lote"] = lote
    casa.pagina("notas_ccn_lote", lote_id=lote)
    casa.pagina("notas_ccn_arquivo", lote_id=lote)
    # a consulta: o pedido pela tela, e a resposta que a extensão do navegador traz pela ponte
    r = _enviar(casa, c, "/notas/ccn/consultas", "consulta ao CCN", cpf="000.000.001-91",
                ambiente="PRODUCAO")
    achado = re.search(r"/notas/ccn/consultas/(\d+)$", r.headers.get("Location", ""))
    assert achado, f"a consulta ao CCN não nasceu: {_recados(casa, c, r)}"
    consulta = int(achado.group(1))
    extensao = casa.app.test_client()                               # sem sessão, como a extensão
    volta = extensao.post("/ccn/ponte/resultado", json={
        "codigo": CQ.codigo_da_consulta(casa.app.secret_key, consulta),
        "achados": [FICHA_DO_CCN], "registros": [FICHA_DO_CCN]})
    assert volta.status_code == 200 and (volta.get_json() or {}).get("ok"), (
        f"a ponte não aceitou a resposta do CCN: {volta.status_code} {volta.get_data(as_text=True)[:200]}")
    casa.ids["notas_ccn_consulta"] = consulta
    casa.pagina("notas_ccn_consulta", consulta_id=consulta)


def passo_certidoes(casa) -> None:
    c = casa.cliente("ADMIN", "novo")
    # a certidão do ato lavrado, com o selo digitado; e a negativa de uma busca sem achado
    pedidos = (
        ("inteiro teor", {"ato_id": str(casa.ids["notas_ato_proc_lavrada"]),
                          "requerente": "Beatriz Exemplo", "busca_item": "13.13.9"}),
        ("negativa", {"nome": "Carla Exemplo", "de": "2000-01-01", "ate": "2000-12-31",
                      "requerente": "Carla Exemplo", "busca_item": "13.13.2"}),
    )
    for rotulo, campos in pedidos:
        antes = casa.um("SELECT COALESCE(MAX(id), 0) AS n FROM nt_certidoes")["n"]
        r = _enviar(casa, c, "/notas/certidoes/emitir", f"certidão {rotulo}", folhas="1",
                    finalidade="instruir processo de exemplo", busca_formulario="1",
                    selo=_selo("CERTID"), **campos)
        nova = casa.um("SELECT id, cancelada, selo FROM nt_certidoes WHERE id > %s ORDER BY id LIMIT 1",
                       (antes,))
        assert nova and not nova["cancelada"] and nova["selo"], (
            f"a certidão ({rotulo}) não saiu: {_recados(casa, c, r)}")
        casa.ids[f"notas_certidao_{rotulo.replace(' ', '_')}"] = int(nova["id"])
        casa.pagina("notas_certidao", certidao_id=int(nova["id"]))
        casa.pagina("notas_certidao_odt", _consulta={"formato": "odt"}, certidao_id=int(nova["id"]))
    # a certidão se pede pelo ato ou pelo nome, e só então a tela oferece o formulário de emitir
    casa.pagina("notas_certidoes", _consulta={"ato_id": casa.ids["notas_ato_proc_lavrada"]})
    casa.pagina("notas_certidoes", _consulta={"nome": "Mario Exemplo"})
    casa.pagina("notas_certidoes", _consulta={"nome": "Carla Exemplo", "de": "2000-01-01", "ate": "2000-12-31"})


def passo_publica_forma(casa) -> None:
    import ato_selado as AS
    import nt_publica_forma as PF
    from bd_nativo import banco
    admin = _admin(casa)
    agora = casa.db.now()
    # a pública forma nasce suspensa e só vira emitida com o selo; a segunda fica como nasceu
    for emitida in (True, False):
        with casa.transacao() as con:
            r = PF.emitir(con, documento_especie="Certificado de regularidade",
                          documento_descricao="folha única, frente e verso",
                          documento_expedidor="Órgão de Exemplo", apresentante="Mario Exemplo",
                          apresentante_documento="00000000191",
                          transcricao="Certificado de regularidade emitido pelo órgão de exemplo em "
                                      "favor de Mario Exemplo, válido por um ano.",
                          folhas=1, hoje=casa.hoje, agora=agora, usuario=admin["full_name"],
                          usuario_funcao="Escrevente")
            if emitida:
                AS.registrar_selo_obtido_a_mao(con, _selo("PUBFOR"), tabela="nt_publicas_formas",
                                               ato_id=r["id"], atribuicao="NOTAS", agora=agora,
                                               cns=casa.db.get_setting("ri_cns", ""),
                                               usuario=admin["full_name"])
                banco(con).escrever("UPDATE nt_publicas_formas SET situacao='EMITIDA' WHERE id=%s",
                                    (r["id"],))
        casa.ids[f"notas_publica_forma_{'emitida' if emitida else 'suspensa'}"] = r["id"]
        casa.pagina("notas_publica_forma_ver", pf_id=r["id"])
        if emitida:
            casa.pagina("notas_publica_forma_odt", _consulta={"formato": "odt"}, pf_id=r["id"])


def passo_leituras(casa) -> None:
    import nt_leitura_documentos as NTL
    admin = _admin(casa)
    agora = casa.db.now()
    rg = {"pessoas": [{"tipo_documento": "RG", "nome": "MARIO EXEMPLO", "numero_documento": "0123456",
                       "orgao_emissor": "SSP/MA", "cpf": "000.000.001-91",
                       "data_nascimento": "05/06/1980", "naturalidade": "CIDADE EXEMPLO - MA",
                       "filiacao_pai": "JOÃO MODELO", "filiacao_mae": "ANA EXEMPLO",
                       "data_expedicao": "10/01/2015", "nacionalidade": "brasileira"}]}
    documentos = [{"arquivo": "identidade.pdf", "n": 1, "attachment_id": None,
                   "tipo": "IDENTIDADE", "dados": rg}]
    arquivos = [{"nome": "identidade.pdf", "sha256": "0" * 64, "attachment_id": None}]
    with casa.transacao() as con:
        lida = NTL.abrir(con, destino="CARTAO", agora=agora, por=admin["full_name"],
                         por_id=admin["id"])
        NTL.concluir(con, lida, arquivos=arquivos,
                     lido={"paginas": [], "documentos": documentos, "envios": []})
        falhou = NTL.abrir(con, destino="VEICULO", agora=agora, por=admin["full_name"],
                           por_id=admin["id"])
        NTL.concluir(con, falhou, arquivos=arquivos, lido=None,
                     erro="A IA não respondeu: tempo esgotado (leitura de ensaio).")
    assert casa.um("SELECT situacao FROM nt_leituras WHERE id=%s", (lida,))["situacao"] == "LIDA"
    assert casa.um("SELECT situacao FROM nt_leituras WHERE id=%s", (falhou,))["situacao"] == "FALHOU"
    casa.ids["notas_leitura_lida"], casa.ids["notas_leitura_falhou"] = lida, falhou
    casa.pagina("notas_leitura_ficha", leitura_id=lida)
    casa.pagina("notas_leitura_ficha", leitura_id=falhou)


def _ia_da_revisao(pasta, *, provedor, sistema, conversa, ferramentas, modelo, maximo_de_saida,
                   **resto):
    """O revisor de mentira: devolve um achado grave e um de atenção, sem rede."""
    texto = json.dumps({"achados": [
        {"gravidade": "GRAVE", "o_que": "O prazo do mandato não está escrito",
         "trecho": "para representá-lo perante as repartições públicas",
         "por_que": "A procuração não diz até quando vale."},
        {"gravidade": "ATENCAO", "o_que": "Estado civil sem regime de bens",
         "trecho": "brasileiro, solteiro", "por_que": "Conferir com o documento."}],
        "parecer": "Texto bom, com um ponto a corrigir antes de lavrar."}, ensure_ascii=False)
    return {"texto": texto, "modelo": modelo, "entrada": 1000, "saida": 200}


def passo_revisao_previa(casa) -> None:
    import revisao_previa as RV
    admin = _admin(casa)
    ato_id = casa.ids["notas_ato_proc_pronta"]
    a = _ato(casa, ato_id)
    with casa.transacao() as con:
        dossie = RV.dossie_notas(con, ato_id)
        rid, _nova = RV.pedir(con, "NOTAS", ato_id, RV.hash_do_ato(a["tipo"], a["teor"]), dossie,
                              rotulo=f"{a['tipo']} das Notas id {ato_id}", usuario=admin["full_name"])
    RV.executar(casa.boot["db_path"], casa.boot["data_dir"], rid, conversar=_ia_da_revisao)
    linha = casa.um("SELECT situacao, graves, erro FROM rv_revisoes WHERE id=%s", (rid,))
    assert linha["situacao"] == "PRONTA", f"a revisão não terminou: {linha}"
    casa.ids["notas_revisao"] = rid
    casa.pagina("revisao_previa_andamento", revisao_id=rid)
    casa.pagina("revisao_previa_notas_ultima", ato_id=ato_id)


def _ia_da_minuta(pasta, *, provedor, sistema, conversa, ferramentas, modelo, maximo_de_saida,
                  **resto):
    """O redator de mentira: guarda o pedido e devolve a minuta no formato combinado."""
    texto = json.dumps({
        "teor": ("PROCURAÇÃO PÚBLICA. Compareceu como outorgante Mario Exemplo, que nomeia sua "
                 "procuradora Beatriz Exemplo para representá-lo perante as repartições públicas "
                 "de Cidade Exemplo/MA.\n\nLida esta procuração, aceitou e assina."),
        "tipo_ato": "", "natureza_titulo": "Procuração pública",
        "partes": [{"nome": "Mario Exemplo", "documento": "000.000.001-91", "papel": "outorgante",
                    "qualificacao": "brasileiro, solteiro, comerciante"},
                   {"nome": "Beatriz Exemplo", "documento": "000.000.002-72", "papel": "outorgado",
                    "qualificacao": "brasileira, solteira, comerciante"}],
        "pendencias": ["o endereço do outorgante não está legível"],
        "fontes": [{"dado": "outorgante", "documento": "identidade.pdf", "pagina": "1"}],
        "observacoes": ""}, ensure_ascii=False)
    return {"texto": texto, "parou": "end_turn", "entrada": 1000, "saida": 200, "modelo": modelo}


def passo_agente_de_minutas(casa) -> None:
    import minuta_ia as MI
    c = casa.cliente("ADMIN", "novo")
    admin = _admin(casa)
    ato_id = _abrir(casa, c, "NT-PROC-PUBLICA")
    anexo = _anexar(casa, c, ato_id, "Identidade do outorgante", "identidade.pdf", PDF)
    with casa.transacao() as con:
        pedido = MI.pedir(con, MI.NOTAS, ato_id, anexos_ids=[anexo], usuario=admin["full_name"])
    MI.executar(casa.boot["db_path"], casa.boot["data_dir"], pedido, conversar=_ia_da_minuta)
    linha = casa.um("SELECT situacao, aplicado_em, erro FROM mi_pedidos WHERE id=%s", (pedido,))
    assert linha["situacao"] == "PRONTA" and linha["aplicado_em"], f"o agente não terminou: {linha}"
    casa.ids["notas_agente_pedido"] = pedido
    casa.ids["notas_ato_proc_do_agente"] = ato_id
    casa.pagina("minuta_ia_pedido", pedido_id=pedido)
    casa.pagina("notas_ato", ato_id=ato_id)


#: A ordem importa: o cartão antes dos atos (uma parte vem dele), os atos antes de quem os usa.
PASSOS = (
    ("SDK do leitor", passo_sdk_do_leitor),
    ("cartões", passo_cartoes),
    ("atos", passo_atos),
    ("ato da base", passo_ato_da_base),
    ("arquivos dos atos", passo_arquivos_dos_atos),
    ("livros", passo_livros),
    ("remessas", passo_remessas),
    ("sinais", passo_sinais),
    ("veículo", passo_veiculo),
    ("reconhecimentos", passo_reconhecimentos),
    ("autenticações", passo_autenticacoes),
    ("CCN", passo_ccn),
    ("certidões", passo_certidoes),
    ("pública forma", passo_publica_forma),
    ("leituras", passo_leituras),
    ("revisão prévia", passo_revisao_previa),
    ("agente de minutas", passo_agente_de_minutas),
)


def semear(casa) -> None:
    import ato_selado as AS
    # Os selos digitados só entram com a trava do selo pago como a base a deixa. Se outra semente a
    # ligou e não a desligou, o erro é dela, e a frase aponta para lá.
    trava = str(casa.db.get_setting(AS.CHAVE_DA_TRAVA, "") or "").strip().upper()
    assert trava == AS.TRAVA_DESLIGADA, (
        f"a trava do selo pago está «{trava or 'ligada'}»: a base a deixa DESLIGADA, e a semente das "
        "notas digita selo. Alguma semente anterior a ligou e não a devolveu.")
    for _nome, passo in PASSOS:
        passo(casa)
