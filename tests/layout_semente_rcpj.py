"""Semente da casa de ensaio: rcpj. Ver `layout_casa.py`.

O QUE SEMEIA
    O título do RCPJ e do RTD em cada estado que muda as fases da ficha (recebido, com exigência,
    qualificado, registrado, devolvido, cancelado), os registros que saem dele (ativo, com averbação,
    cancelado, do RCPJ), a certidão, a notificação do RTD, a autenticação de livro contábil e a apostila.

POR QUE O CAMINHO NÃO É SÓ O DA TELA
    O selo só sai do aparelho, e a trava barra a rede. O ato que a tela sela vai com selo digitado (o
    formato que a casa aceita); o que só o aparelho sela (a diligência, a certidão da notificação e a
    autenticação de livro) vai pela função de domínio, com o selo digitado no razão.

OS SELOS SAEM DE 99 PARA BAIXO: `sd_selos.numero` é único, e as outras áreas contam de baixo.
"""
from __future__ import annotations

import io
from datetime import date, timedelta

import layout_ensaio as E

#: Rota com número que não tem como abrir aqui: endpoint -> o motivo.
SEM_SEMENTE: dict[str, str] = {}

CPF = "00000000191"
CNPJ = "00000043000177"
PREFIXO_DO_SELO = "AVESVD000000NARRKWVNJCRSVO"
ENDERECO = "Rua da Demonstração, 100, Centro, Cidade Exemplo/MA"


# ------------------------------------------------------------------- o que se repete


def _arquivo(formato: str) -> bytes:
    from PIL import Image
    saida = io.BytesIO()
    Image.new("RGB", (600, 800), "white").save(saida, formato)
    return saida.getvalue()


def _selo(casa) -> str:
    usados = {x["numero"] for x in casa.ler(
        "SELECT numero FROM sd_selos WHERE numero LIKE %s", (PREFIXO_DO_SELO + "%",))}
    for n in range(99, -1, -1):
        if f"{PREFIXO_DO_SELO}{n:02d}" not in usados:
            return f"{PREFIXO_DO_SELO}{n:02d}"
    raise AssertionError("acabaram os selos de ensaio da área rcpj")


def _ultimo(casa, tabela: str) -> int:
    return int(casa.um(f"SELECT COALESCE(MAX(id), 0) AS n FROM {tabela}")["n"])


def _br(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def _avisos(c, r) -> str:
    """O que a tela disse, para a recusa não ficar muda."""
    try:
        if r.status_code in (301, 302, 303):
            r = c.get(r.headers["Location"])
        flashes = E.ler_pagina(r.get_data(as_text=True)).flashes
        return " | ".join(texto for _classe, texto in flashes) or f"HTTP {r.status_code}"
    except Exception:                                                 # noqa: BLE001
        return f"HTTP {r.status_code}"


def _enviar(casa, c, endereco: str, o_que: str, nasceu, **campos):
    """Manda o formulário como a tela manda e confere que a linha nasceu. `nasceu` devolve o que ficou."""
    r = casa.postar(endereco, _cliente=c, **campos)
    achado = nasceu()
    assert achado, f"{o_que}: a tela não gravou ({_avisos(c, r)})"
    return achado


def _quem(casa) -> tuple[str, dict]:
    """Quem assina o que a função de domínio lavra, e a serventia: o que a rota passaria."""
    from serventia import dados
    nome = casa.um("SELECT full_name FROM users WHERE id=%s", (casa.ids["admin"],))["full_name"]
    return nome, dados(casa.db.get_settings)


def _extenso(casa) -> str:
    from ri_web import data_por_extenso
    return data_por_extenso(date.fromisoformat(casa.hoje))


# ------------------------------------------------------------------- a tabela que a casa não traz


def _tabela_de_emolumentos(casa) -> None:
    """Só os itens que a apostila, o livro contábil e a notificação consultam. A casa não traz tabela."""
    itens = (
        (422, "13.23", "Apostila de Haia - certificação de documentos produzidos em território nacional",
         ("125,01", "3,75", "5,00", "5,00", "1,25")),
        (493, "15.7.1", "Autenticação de livro contábil, até cinco folhas",
         ("89,52", "2,69", "3,58", "3,58", "0,90")),
        (453, "15.8.1", "Diligência para notificação extrajudicial em zona urbana, por destinatário",
         ("31,14", "0,93", "1,25", "1,25", "0,31")),
        (454, "15.8.2", "Certidão à margem do registro, por destinatário",
         ("47,84", "1,44", "1,91", "1,91", "0,48")),
    )
    casa.sql("INSERT INTO cx_vigencias (codigo, descricao, vigente, inicio, fim, importado_em) "
             "VALUES (%s, '2026', 1, '2026-01-01', NULL, '2026-08-21') ON CONFLICT (codigo) DO NOTHING",
             (10022,))
    for codigo, tj, descricao, valores in itens:
        total = sum(round(float(v.replace(",", ".")) * 100) for v in valores)
        casa.sql("INSERT INTO cx_servicos (codigo, codigo_tj, descricao, ativo) VALUES (%s, %s, %s, 1) "
                 "ON CONFLICT (codigo) DO NOTHING", (codigo, tj, descricao))
        casa.sql("INSERT INTO cx_servico_valores (servico, vigencia, emolumentos, ferc, femp, fadep, ferrfis, total) "
                 "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (servico, vigencia) DO NOTHING",
                 (codigo, 10022, *valores, f"{total // 100},{total % 100:02d}"))


def _selar_a_mao(casa, tabela: str, ato_id: int, atribuicao: str, item: str) -> str:
    """O selo que o aparelho daria, digitado no razão com o texto que ele imprime. Devolve o número."""
    import ato_selado as AS
    nome, sv = _quem(casa)
    numero = _selo(casa)
    agora = casa.db.now()
    texto = (f"Poder Judiciario - TJMA. Selo: {numero}, {_br(agora[:10])} {agora[11:19]}, Ato: {item}, "
             "Consulte em https://selo.tjma.jus.br")
    with casa.transacao() as con:
        AS.registrar_selo_obtido_a_mao(con, numero, tabela=tabela, ato_id=ato_id, atribuicao=atribuicao,
                                       agora=agora, cns=sv.get("ri_cns"), usuario=nome, texto=texto)
    return numero


# ------------------------------------------------------------------- os títulos


def _receber(casa, c, atribuicao: int, o_que: str, **campos) -> int:
    antes = _ultimo(casa, "rg_titulos")
    dados = {"apresentante": "Ana Exemplo", "apresentante_documento": CPF, "telefone": "(00) 0000-0000",
             "email": "ana@exemplo.invalid", "natureza": "Contrato de locação de imóvel",
             "valor_declarado": "R$ 12.000,00", "vias": "1", "forma": "PAPEL", **campos}
    r = casa.postar(f"/rcpj-rtd/titulos/novo?atribuicao={atribuicao}", _cliente=c, **dados)
    novo = _ultimo(casa, "rg_titulos")
    assert novo > antes, f"{o_que}: o título não entrou ({_avisos(c, r)})"
    return novo


def _anexar(casa, c, titulo_id: int, o_que: str, nome: str, conteudo: bytes) -> int:
    return int(_enviar(
        casa, c, f"/rcpj-rtd/titulo/{titulo_id}/arquivo", o_que,
        lambda: casa.um("SELECT id FROM attachments WHERE entity_type=%s AND entity_id=%s ORDER BY id DESC LIMIT 1",
                        ("RG_TITULO", titulo_id)),
        arquivo=(io.BytesIO(conteudo), nome), descricao="Título apresentado")["id"])


def _qualificar(casa, c, titulo_id: int, resultado: str, o_que: str, **campos) -> None:
    esperada = "QUALIFICADO" if resultado == "POSITIVA" else "EXIGENCIA"
    _enviar(casa, c, f"/rcpj-rtd/titulo/{titulo_id}/qualificar", o_que,
            lambda: casa.um("SELECT id FROM rg_titulos WHERE id=%s AND situacao=%s", (titulo_id, esperada)),
            resultado=resultado, **campos)


def _encerrar(casa, c, titulo_id: int, situacao: str, o_que: str) -> None:
    _enviar(casa, c, f"/rcpj-rtd/titulo/{titulo_id}/encerrar", o_que,
            lambda: casa.um("SELECT id FROM rg_titulos WHERE id=%s AND situacao=%s", (titulo_id, situacao)),
            situacao=situacao, motivo="Motivo de ensaio do encerramento do título.")


def _registrar(casa, c, titulo_id: int, o_que: str) -> int:
    """O registro do título qualificado, com o selo digitado. Devolve o id do registro."""
    achado = _enviar(
        casa, c, f"/rcpj-rtd/titulo/{titulo_id}/registrar", o_que,
        lambda: casa.um("SELECT registro_id FROM rg_titulos WHERE id=%s AND situacao='REGISTRADO'", (titulo_id,)),
        serie="TD_B", teor="Registro integral do contrato de ensaio, com as cláusulas de exemplo.",
        selo=_selo(casa))
    return int(achado["registro_id"])


# ------------------------------------------------------------------- o título que veio da Central


def _titulo_da_central(casa) -> int:
    """O pedido da Central entra pela função de domínio: a fila de lá é rede, e a rede está barrada."""
    import rg_titulo as TIT
    nome, sv = _quem(casa)
    pedido = {"Protocolo": "000000000002", "DataCadastro": casa.hoje, "Situacao": {"Nome": "Em andamento"},
              "Cliente": {"Nome": "Carla Exemplo", "CPFCNPJ": CPF, "Email": "carla@exemplo.invalid"},
              "Servico": {"Nome": "Registro de título"}, "DescricaoResumida": "Contrato de exemplo",
              "ValorOrcamento": "R$ 12.000,00"}
    with casa.transacao() as con:
        feito = TIT.receber_da_central(con, pedido, atribuicao=4, sv=sv, agora=casa.db.now(),
                                       data_extenso=_extenso(casa), usuario=nome)
    return int(feito["titulo_id"])


# ------------------------------------------------------------------- os registros


def _anexar_ao_registro(casa, c, registro_id: int, o_que: str) -> None:
    _enviar(casa, c, f"/rcpj-rtd/{registro_id}/arquivo", o_que,
            lambda: casa.um("SELECT id FROM attachments WHERE entity_type=%s AND entity_id=%s",
                            ("RG_REGISTRO", registro_id)),
            arquivo=(io.BytesIO(_arquivo("PNG")), "documento.png"), descricao="Documento apresentado")


def _registro_novo(casa, c, o_que: str, **campos) -> int:
    antes = _ultimo(casa, "rg_registros")
    dados = {"serie": "TD_B", "natureza": "Contrato de comodato", "requerente_nome": "João Modelo",
             "requerente_documento": CPF, "teor": "Registro integral do contrato de ensaio.",
             "selo": _selo(casa), **campos}
    r = casa.postar("/rcpj-rtd/novo", _cliente=c, **dados)
    novo = _ultimo(casa, "rg_registros")
    assert novo > antes, f"{o_que}: o registro não abriu ({_avisos(c, r)})"
    return novo


def _lancar(casa, c, registro_id: int, tipo: str, o_que: str, **campos) -> int:
    """A averbação ou o cancelamento, com o selo digitado. Devolve o id do ato."""
    antes = _ultimo(casa, "rg_atos")
    r = casa.postar(f"/rcpj-rtd/{registro_id}/lancar", _cliente=c, tipo=tipo, selo=_selo(casa), **campos)
    ato = casa.um("SELECT id FROM rg_atos WHERE registro_id=%s AND tipo=%s AND id>%s ORDER BY id DESC LIMIT 1",
                  (registro_id, tipo, antes))
    assert ato, f"{o_que}: o ato não foi lançado ({_avisos(c, r)})"
    return int(ato["id"])


def _certidao(casa, c, registro_id: int, o_que: str) -> int:
    antes = _ultimo(casa, "at_certidoes")
    r = casa.postar(f"/atribuicoes/certidoes/RCPJ_RTD/{registro_id}", _cliente=c, requerente="Carla Exemplo",
                    requerente_documento=CPF, finalidade="Prova em processo de exemplo", selo=_selo(casa))
    novo = _ultimo(casa, "at_certidoes")
    assert novo > antes, f"{o_que}: a certidão não saiu ({_avisos(c, r)})"
    return novo


def _certidao_negativa(casa) -> int:
    """A certidão negativa do RTD pela função de domínio, com o selo que o aparelho daria."""
    import atrib_certidao as CE
    nome, _sv = _quem(casa)
    with casa.transacao() as con:
        feita = CE.emitir_negativa(con, atribuicao="RTD", nome="Mario Exemplo", documento="", hoje=casa.hoje,
                                   agora=casa.db.now(), requerente="Carla Exemplo", requerente_documento=CPF,
                                   finalidade="Prova em processo de exemplo", usuario=nome, usuario_nome=nome,
                                   usuario_funcao="Escrevente")
    _selar_a_mao(casa, "at_certidoes", feita["certidao_id"], "RTD", "15.10")
    return feita["certidao_id"]


# ------------------------------------------------------------------- a notificação


def _dias_de_diligencia(casa, quantos: int) -> list[date]:
    """Os últimos dias, até hoje, em que a norma deixa fazer diligência. Do mais velho ao mais novo."""
    import rg_notificacao as RN
    achados, dia = [], date.fromisoformat(casa.hoje)
    while len(achados) < quantos:
        try:
            RN.conferir_dia_e_hora(dia.isoformat(), "10:00")
        except RN.NotificacaoError:
            pass
        else:
            achados.append(dia)
        dia -= timedelta(days=1)
    return list(reversed(achados))


def _notificar(casa, c, titulo_id: int, o_que: str, nome: str) -> int:
    antes = _ultimo(casa, "rg_notificacoes")
    # O campo se chama `endereco`, como o parâmetro de `postar`: por isso o envio é direto.
    r = c.post("/rcpj-rtd/notificacoes/nova", data={
        "csrf_token": casa.token(c), "titulo_id": str(titulo_id), "destinatario_nome": nome,
        "destinatario_documento": CPF, "endereco": ENDERECO, "zona": "URBANA"})
    novo = _ultimo(casa, "rg_notificacoes")
    assert novo > antes, f"{o_que}: a notificação não abriu ({_avisos(c, r)})"
    return novo


def _ida(casa, notificacao_id: int, dia: date, hora: str, resultado: str) -> dict:
    """A diligência pela função de domínio: a rota pediria o selo ao aparelho, e a rede está barrada."""
    import rg_notificacao as RN
    nome, _sv = _quem(casa)
    with casa.transacao() as con:
        return RN.registrar_ida(con, notificacao_id, data=dia.isoformat(), hora=hora, resultado=resultado,
                                agora=casa.db.now(), usuario=nome)


def _selar_a_diligencia(casa, diligencia_id: int) -> None:
    _selar_a_mao(casa, "rg_notificacao_diligencias", diligencia_id, "RTD", "15.8.1")
    casa.sql("UPDATE rg_notificacao_diligencias SET selo_situacao='SELADO', selo_motivo=NULL WHERE id=%s",
             (diligencia_id,))


def _certificar(casa, notificacao_id: int) -> int:
    """A certidão da notificação, com o selo que o aparelho daria. Devolve o id da certidão."""
    import rg_notificacao as RN
    nome, sv = _quem(casa)
    with casa.transacao() as con:
        certidao = RN.emitir_certidao(con, notificacao_id, agora=casa.db.now(), sv=sv,
                                      data_extenso=_extenso(casa), usuario=nome)
    _selar_a_mao(casa, "rg_notificacao_certidoes", certidao["certidao_id"], "RTD", "15.8.2")
    casa.sql("UPDATE rg_notificacao_certidoes SET selo_situacao='SELADO', selo_motivo=NULL WHERE id=%s",
             (certidao["certidao_id"],))
    return certidao["certidao_id"]


# ------------------------------------------------------------------- o livro contábil e a apostila


def _nasceu_em(casa, tabela: str):
    """O que diz o id da linha nova, ou 0 se nada nasceu. Chame ANTES de enviar: ela olha o último id agora."""
    antes = _ultimo(casa, tabela)

    def achar() -> int:
        n = _ultimo(casa, tabela)
        return n if n > antes else 0
    return achar


def _livro_contabil(casa, c, o_que: str, **campos) -> int:
    dados = {"pj_nome": "Associação Exemplo", "pj_cnpj": CNPJ, "tipo_livro": "DIARIO", "numero_livro": "1",
             "folhas": "50", "forma": "PAPEL", "apresentante_nome": "Beatriz Exemplo", **campos}
    return _enviar(casa, c, "/rcpj-rtd/livros-contabeis/novo", o_que, _nasceu_em(casa, "rg_livros_contabeis"), **dados)


def _autenticar(casa, livro_id: int) -> None:
    """A autenticação pela função de domínio, com o selo que o aparelho daria: a rota o pediria à rede."""
    import rg_livro_contabil as RLC
    nome, sv = _quem(casa)
    with casa.transacao() as con:
        RLC.autenticar(con, livro_id, codigo_tj="15.7.1", serventia=sv, hoje=casa.hoje, agora=casa.db.now(),
                       usuario=nome, funcao="Escrevente")
    _selar_a_mao(casa, "rg_livros_contabeis", livro_id, "RCPJ", "15.7.1")
    with casa.transacao() as con:
        RLC.marcar_selado(con, livro_id)


def _documento_de_apostila(casa, c, pedido_id: int, o_que: str, **campos) -> int:
    dados = {"documento_tipo": "REGISTRO_CIVIL", "documento_data": casa.hoje, "signatario_nome": "Mario Exemplo",
             "signatario_cargo": "Oficial de Registro Civil", **campos}
    return _enviar(casa, c, f"/apostila/pedido/{pedido_id}/documento", o_que, _nasceu_em(casa, "ap_apostilas"), **dados)


def _situacao_da_apostila(casa, apostila_id: int, situacao: str):
    return lambda: casa.um("SELECT id FROM ap_apostilas WHERE id=%s AND situacao=%s", (apostila_id, situacao))


# ------------------------------------------------------------------- a semente


def _processo_fiduciario(casa, c) -> int:
    """Um processo qualificado: a autuação pela tela, e o resto pela tela do passo."""
    import rg_fiduciaria as FID
    titulo = _receber(casa, c, 4, "título do processo fiduciário", natureza="Requerimento de consolidação fiduciária")
    pid = _enviar(casa, c, "/rcpj-rtd/fiduciaria/nova", "processo fiduciário", _nasceu_em(casa, "rg_fiduciarias"),
                  titulo_id=titulo, credor_nome="Banco Exemplo", devedor_nome="Ana Exemplo",
                  bem_descricao="Motocicleta exemplo", valor_divida="1.000,00")
    nome, _sv = _quem(casa)
    with casa.transacao() as con:
        FID.qualificar(con, pid, resultado="POSITIVA", itens=[r["chave"] for r in FID.REQUISITOS if r["obrigatorio"]],
                       dia=casa.hoje, agora=casa.db.now(), usuario=nome)
    return pid


def semear(casa) -> None:
    c = casa.cliente("ADMIN", "novo")
    _tabela_de_emolumentos(casa)

    # O título de uma notificação foi apresentado antes da primeira diligência, e a diligência não se
    # faz domingo nem feriado: as datas saem da regra da própria norma.
    dias = _dias_de_diligencia(casa, 4)
    apresentado = (dias[0] - timedelta(days=1)).isoformat()

    # ---- o título do RTD, em cada estado que muda as fases
    recebido = _receber(casa, c, 4, "título recebido", data_apresentacao=apresentado, serie="TD_B")
    recebido_pdf = _anexar(casa, c, recebido, "título recebido", "titulo.pdf", _arquivo("PDF"))
    _enviar(casa, c, f"/rcpj-rtd/titulo/{recebido}/encaminhar", "passagem pela Central",
            lambda: casa.um("SELECT id FROM rg_encaminhamentos WHERE titulo_id=%s", (recebido,)),
            sentido="ENVIADO", protocolo_central="000000000001", observacao="Passagem de ensaio pelo portal.")

    exigencia = _receber(casa, c, 4, "título com exigência", natureza="Contrato de prestação de serviços")
    _qualificar(casa, c, exigencia, "NEGATIVA", "qualificação negativa",
                exigencias="Apresentar o original, com o reconhecimento de firma do locador.",
                fundamentacao="Lei 6.015/1973, art. 130.",
                prazo_ate=(date.fromisoformat(casa.hoje) + timedelta(days=15)).isoformat())

    qualificado = _receber(casa, c, 4, "título qualificado", natureza="Contrato de comodato de veículo")
    qualificado_pdf = _anexar(casa, c, qualificado, "título qualificado", "titulo.pdf", _arquivo("PDF"))
    _qualificar(casa, c, qualificado, "POSITIVA", "qualificação positiva",
                fundamentacao="Título em ordem para registro.")

    registrado = _receber(casa, c, 4, "título registrado", data_apresentacao=apresentado,
                          natureza="Contrato de locação comercial", serie="TD_B")
    registrado_png = _anexar(casa, c, registrado, "título registrado", "titulo.png", _arquivo("PNG"))
    _qualificar(casa, c, registrado, "POSITIVA", "qualificação do título a registrar",
                fundamentacao="Título em ordem para registro.")
    r1 = _registrar(casa, c, registrado, "registro do título")
    _anexar_ao_registro(casa, c, r1, "documento do registro")

    devolvido = _receber(casa, c, 4, "título devolvido", natureza="Procuração particular")
    _qualificar(casa, c, devolvido, "NEGATIVA", "qualificação do título devolvido",
                exigencias="Falta a assinatura do outorgante, que não consta do papel.")
    _encerrar(casa, c, devolvido, "DEVOLVIDO", "título devolvido")

    cancelado = _receber(casa, c, 4, "título cancelado", natureza="Cessão de crédito")
    _encerrar(casa, c, cancelado, "CANCELADO", "título cancelado")

    # ---- o título do RCPJ: a ficha dele pede a lista de presença
    rcpj = _receber(casa, c, 3, "título do RCPJ", natureza="Estatuto de associação civil", serie="PJ_A",
                    apresentante="Beatriz Exemplo")
    _qualificar(casa, c, rcpj, "POSITIVA", "qualificação do título do RCPJ",
                fundamentacao="Lei 6.015/1973, art. 120.")
    rcpj_exigencia = _receber(casa, c, 3, "título do RCPJ com exigência", natureza="Estatuto de associação civil",
                              serie="PJ_A", apresentante="Beatriz Exemplo")
    _qualificar(casa, c, rcpj_exigencia, "NEGATIVA", "qualificação negativa do RCPJ",
                exigencias="Falta a ata de fundação, assinada por todos os fundadores.")

    # ---- o título que veio da Central: forma eletrônica, e sem atendimento no balcão
    da_central = _titulo_da_central(casa)

    # ---- os registros: o do título (com averbação), o cancelado e o da pessoa jurídica
    ato_do_registro = casa.um("SELECT id FROM rg_atos WHERE registro_id=%s AND tipo='REGISTRO'", (r1,))["id"]
    averbacao = _lancar(casa, c, r1, "AVERBACAO", "averbação do registro", natureza_ato="Alteração contratual",
                        data_assinatura=_br(casa.hoje), novo_arquivo=(io.BytesIO(_arquivo("PNG")), "averbacao.png"))
    r2 = _registro_novo(casa, c, "registro a cancelar")
    _anexar_ao_registro(casa, c, r2, "documento do registro a cancelar")
    cancelamento = _lancar(casa, c, r2, "CANCELAMENTO", "cancelamento do registro",
                           motivo="Contrato rescindido por acordo entre as partes de exemplo.")
    r3 = _registro_novo(casa, c, "registro do RCPJ", serie="PJ_A", natureza="Alteração de endereço da sede",
                        requerente_nome="Associação Exemplo", requerente_documento=CNPJ,
                        enquadramento_cnma="NAO_SE_APLICA",
                        justificativa_cnma="Ato fora dos arts. 410, 412 e 413 do CN-MA.",
                        declaracao_denominacao="Associação Exemplo", declaracao_sede=ENDERECO)
    _enviar(casa, c, f"/rcpj-rtd/{r3}/dados-pj", "dados da pessoa jurídica",
            lambda: casa.um("SELECT id FROM rg_registros WHERE id=%s AND pj_dados_em IS NOT NULL", (r3,)),
            pj_sede=ENDERECO, pj_objeto="Fins culturais e recreativos, sem fins econômicos.",
            pj_capital="Sem capital social.", pj_socios="Mario Exemplo e Carla Exemplo.",
            pj_diretoria="Presidente: Mario Exemplo. Tesoureira: Carla Exemplo.")
    _anexar_ao_registro(casa, c, r3, "documento do registro do RCPJ")

    # ---- a certidão do registro, a negativa e a cancelada
    certidao = _certidao(casa, c, r1, "certidão do registro")
    certidao_cancelada = _certidao(casa, c, r2, "certidão do registro cancelado")
    _enviar(casa, c, f"/atribuicoes/certidoes/{certidao_cancelada}/cancelar", "cancelamento da certidão",
            lambda: casa.um("SELECT id FROM at_certidoes WHERE id=%s AND cancelada=1", (certidao_cancelada,)),
            motivo="Emitida sobre o registro errado, no ensaio.", selo_cancelado_tjma="1")
    certidao_negativa_do_rtd = _certidao_negativa(casa)

    # ---- a notificação do RTD, nos três estados
    n_em_diligencia = _notificar(casa, c, recebido, "notificação em diligência", "Mario Exemplo")
    _ida(casa, n_em_diligencia, dias[1], "09:00", "AUSENTE")

    n_positiva = _notificar(casa, c, registrado, "notificação positiva", "Carla Exemplo")
    primeira = _ida(casa, n_positiva, dias[1], "10:00", "ENTREGUE")
    _selar_a_diligencia(casa, primeira["diligencia_id"])
    certidao_positiva = _certificar(casa, n_positiva)

    n_sem_certidao = _notificar(casa, c, registrado, "notificação positiva sem certidão", "Ana Exemplo")
    recusou = _ida(casa, n_sem_certidao, dias[2], "11:00", "RECUSOU")
    _selar_a_diligencia(casa, recusou["diligencia_id"])

    n_negativa = _notificar(casa, c, registrado, "notificação negativa", "João Modelo")
    primeira = _ida(casa, n_negativa, dias[0], "08:00", "AUSENTE")
    _ida(casa, n_negativa, dias[1], "14:00", "MUDOU_SE")
    _ida(casa, n_negativa, dias[2], "19:00", "NAO_LOCALIZADO")
    _selar_a_diligencia(casa, primeira["diligencia_id"])
    _enviar(casa, c, f"/rcpj-rtd/notificacao/{n_negativa}/negativa", "resultado negativo",
            lambda: casa.um("SELECT id FROM rg_notificacoes WHERE id=%s AND situacao='NEGATIVA'", (n_negativa,)))
    certidao_negativa = _certificar(casa, n_negativa)
    _enviar(casa, c, f"/rcpj-rtd/notificacao/{n_negativa}/averbar", "averbação do resultado negativo",
            lambda: casa.um("SELECT id FROM rg_notificacoes WHERE id=%s AND averbacao_ato_id IS NOT NULL",
                            (n_negativa,)))

    # ---- a autenticação de livro contábil: o pedido e a autenticada (com os três papéis)
    _enviar(casa, c, "/rcpj-rtd/livros-contabeis/configuracao", "item da autenticação de livro",
            lambda: casa.db.get_setting("rcpj_livro_contabil_item", "") == "15.7.1", item="15.7.1")
    livro_pedido = _livro_contabil(casa, c, "pedido de autenticação", registro_id=str(r3))
    livro_autenticado = _livro_contabil(casa, c, "pedido de autenticação do razão", tipo_livro="RAZAO",
                                        registro_id=str(r3))
    _autenticar(casa, livro_autenticado)

    # ---- a apostila: o módulo vem fechado de fábrica, e o pedido leva um documento em cada situação
    import apostila as AP
    import modulos_ligados as MODLIG
    _enviar(casa, c, "/administrativo/gestor/apostila", "alcance da apostila",
            lambda: MODLIG.alcance(casa.db.get_setting, AP.MODULO) == MODLIG.TODOS, alcance="TODOS", servico="")
    sigla = next((s for s in ("RTD", "RCPJ") if s in AP.ATRIBUICOES_LIBERADAS), AP.ATRIBUICOES_LIBERADAS[0])
    pedido = _enviar(casa, c, "/apostila/pedido", "pedido de apostila", _nasceu_em(casa, "ap_pedidos"),
                     recebido_em=casa.hoje, atribuicao=sigla, requerente_nome="Ana Exemplo",
                     requerente_documento=CPF, requerente_contato="ana@exemplo.invalid", pais_destino="Portugal")
    emitida = _documento_de_apostila(casa, c, pedido, "documento a emitir")
    sem_selo = _documento_de_apostila(casa, c, pedido, "documento emitido sem selo", documento_tipo="JUDICIAL")
    cancelada = _documento_de_apostila(casa, c, pedido, "documento a cancelar", documento_tipo="NOTARIAL",
                                       signatario_nome="Beatriz Exemplo", signatario_cargo="Tabeliã")
    recusada = _documento_de_apostila(casa, c, pedido, "documento a recusar", documento_tipo="ESCOLAR")
    pendente = _documento_de_apostila(casa, c, pedido, "documento pendente", documento_tipo="REGISTRAL")
    for numero, cada, selo in ((1, emitida, "SELO EXEMPLO 0001"), (2, sem_selo, ""), (3, cancelada, "")):
        _enviar(casa, c, f"/apostila/{cada}/emitir", "apostila emitida", _situacao_da_apostila(casa, cada, "EMITIDA"),
                codigo_cnj=f"BR-EXEMPLO-000{numero}", emitida_em=casa.hoje, selo=selo)
    _enviar(casa, c, f"/apostila/{cancelada}/cancelar", "apostila cancelada",
            _situacao_da_apostila(casa, cancelada, "CANCELADA"), motivo="Cancelada no sistema do CNJ, no ensaio.")
    _enviar(casa, c, f"/apostila/{recusada}/recusar", "apostila recusada",
            _situacao_da_apostila(casa, recusada, "RECUSADA"), motivo="Documento sem assinatura que se possa conferir.")

    fiduciario = _processo_fiduciario(casa, c)

    casa.ids.update({
        "rcpj_fiduciaria": fiduciario,
        "rcpj_titulo_recebido": recebido, "rcpj_titulo_exigencia": exigencia,
        "rcpj_titulo_qualificado": qualificado, "rcpj_titulo_registrado": registrado,
        "rcpj_titulo_devolvido": devolvido, "rcpj_titulo_cancelado": cancelado, "rcpj_titulo_rcpj": rcpj,
        "rcpj_titulo_rcpj_exigencia": rcpj_exigencia, "rcpj_titulo_da_central": da_central,
        "rcpj_registro_do_titulo": r1, "rcpj_registro_cancelado": r2, "rcpj_registro_da_pj": r3,
        "rcpj_notificacao_em_diligencia": n_em_diligencia, "rcpj_notificacao_positiva": n_positiva,
        "rcpj_notificacao_sem_certidao": n_sem_certidao, "rcpj_notificacao_negativa": n_negativa,
        "rcpj_certidao_da_notificacao_positiva": certidao_positiva,
        "rcpj_certidao_da_notificacao_negativa": certidao_negativa,
        "rcpj_certidao": certidao, "rcpj_certidao_cancelada": certidao_cancelada,
        "rcpj_certidao_negativa": certidao_negativa_do_rtd,
        "rcpj_ato_do_registro": ato_do_registro, "rcpj_ato_averbacao": averbacao, "rcpj_ato_cancelamento": cancelamento,
        "rcpj_livro_pedido": livro_pedido, "rcpj_livro_autenticado": livro_autenticado,
        "rcpj_apostila_pedido": pedido, "rcpj_apostila_emitida": emitida, "rcpj_apostila_sem_selo": sem_selo,
        "rcpj_apostila_cancelada": cancelada, "rcpj_apostila_recusada": recusada, "rcpj_apostila_pendente": pendente})

    casa.pagina("rcpj_rtd_fiduciaria", proc_id=fiduciario)
    casa.pagina("rcpj_rtd_fiduciaria_peca", proc_id=fiduciario, qual="NOTIFICACAO")
    casa.pagina("rcpj_rtd_titulo", titulo_id=recebido)
    casa.pagina("rcpj_rtd_titulo_recibo", titulo_id=recebido)
    casa.pagina("rcpj_rtd_titulo_ver", titulo_id=recebido, anexo_id=recebido_pdf)
    casa.pagina("rcpj_rtd_titulo", titulo_id=exigencia)
    casa.pagina("rcpj_rtd_titulo_nota", titulo_id=exigencia)
    casa.pagina("rcpj_rtd_titulo", titulo_id=qualificado)
    casa.pagina("rcpj_rtd_titulo_ver", titulo_id=qualificado, anexo_id=qualificado_pdf)
    casa.pagina("rcpj_rtd_titulo", titulo_id=registrado)
    casa.pagina("rcpj_rtd_titulo_ver", titulo_id=registrado, anexo_id=registrado_png)
    casa.pagina("rcpj_rtd_titulo_teor_previa", titulo_id=registrado)
    casa.pagina("rcpj_rtd_titulo", titulo_id=devolvido)
    casa.pagina("rcpj_rtd_titulo", titulo_id=cancelado)
    casa.pagina("rcpj_rtd_titulo", titulo_id=rcpj)
    casa.pagina("rcpj_rtd_titulo", titulo_id=rcpj_exigencia)
    casa.pagina("rcpj_rtd_titulo_nota", titulo_id=rcpj_exigencia)
    casa.pagina("rcpj_rtd_titulo", titulo_id=da_central)

    casa.pagina("rcpj_rtd_registro", registro_id=r1)
    casa.pagina("rcpj_rtd_registro", registro_id=r2)
    casa.pagina("rcpj_rtd_registro", registro_id=r3)
    casa.pagina("rcpj_rtd_certidao_previa", registro_id=r1)
    # `/teor-averbacao/previa` é o outro endereço da mesma função: a rota tem dois, e a casa anota um.
    casa.pagina("rcpj_rtd_teor_averbacao_previa", registro_id=r1)
    casa.pagina("rcpj_rtd_teor_averbacao_previa", {"tipo": "REGISTRO"}, registro_id=r1)
    casa.pagina("rcpj_rtd_ato_teor", ato_id=ato_do_registro)
    casa.pagina("rcpj_rtd_ato_teor", ato_id=averbacao)
    casa.pagina("rcpj_rtd_ato_teor", ato_id=cancelamento)

    # A negativa não reproduz documento: a impressão dela vai pelo .odt, e o PDF precisa do LibreOffice.
    for cada, formato in ((certidao, None), (certidao_cancelada, None), (certidao_negativa_do_rtd, "odt")):
        casa.pagina("atribuicoes_certidao", certidao_id=cada)
        casa.pagina("atribuicoes_certidao_imprimir", {"formato": formato} if formato else None, certidao_id=cada)
        casa.pagina("atribuicoes_certidao_odt", {"formato": "odt"}, certidao_id=cada)

    casa.pagina("rcpj_rtd_notificacao", notificacao_id=n_em_diligencia)
    casa.pagina("rcpj_rtd_notificacao", notificacao_id=n_positiva)
    casa.pagina("rcpj_rtd_notificacao", notificacao_id=n_sem_certidao)
    casa.pagina("rcpj_rtd_notificacao", notificacao_id=n_negativa)
    casa.pagina("rcpj_rtd_notificacao_certidao_ver", certidao_id=certidao_positiva)
    casa.pagina("rcpj_rtd_notificacao_certidao_ver", certidao_id=certidao_negativa)

    casa.pagina("rcpj_rtd_livro_contabil_ficha", livro_id=livro_pedido)
    casa.pagina("rcpj_rtd_livro_contabil_ficha", livro_id=livro_autenticado)
    for qual in ("abertura", "encerramento", "certidao"):
        casa.pagina("rcpj_rtd_livro_contabil_papel", livro_id=livro_autenticado, qual=qual)

    casa.pagina("apostila_pedido", pedido_id=pedido)
    for cada in (emitida, sem_selo, cancelada):
        casa.pagina("apostila_certidao", apostila_id=cada)
