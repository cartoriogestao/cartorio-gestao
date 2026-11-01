"""O COMPROVANTE DE PAGAMENTO — por e-mail ou WhatsApp, para o contato da despesa.

Relato #152 e pedido do oficial (30/10/2026): «uma forma de enviar o comprovante de
pagamento, por whatsapp ou email cadastrado na despesa».

SÓ SAI PELO CLIQUE DE UMA PESSOA, e só da despesa paga: nenhum robô manda isto.

O QUE VAI: O DEMONSTRATIVO, QUE NÃO É O COMPROVANTE DO BANCO
    A API do Inter não entrega o comprovante. O oficial escolheu (31/10/2026) um PDF da
    casa com os dados que o banco informou, e o próprio papel diz o que ele é. O E2E é o
    que liga o papel ao Pix: sem ele o demonstrativo não sai. Quem quiser mandar também
    outro arquivo escolhe na ficha, e só por e-mail: o documento da despesa pode ser o
    recibo da folha inteira, com o salário de todos, e por isso nunca vai sem alguém
    escolher.

O WHATSAPP SÓ ACEITA TEXTO LIVRE DENTRO DA JANELA DE 24 H (`wa_modelos`)
    Não há modelo da Meta para comprovante. Com a janela aberta, sai pela conta da casa;
    com o PDF; fora dela, a ficha oferece o PDF para baixar e o link que abre o WhatsApp
    de quem clicou, com o texto pronto. A pessoa é quem junta o arquivo e aperta enviar.

A REDE FICA FORA DE TODA TRANSAÇÃO, como nos avisos de andamento. O endereço e o
telefone não vão ao rastro nem à auditoria.
"""
from __future__ import annotations

import mimetypes
import smtplib
import urllib.parse
from datetime import date, datetime
from pathlib import Path
from typing import Any

import despesas as DP
import serventia as SERV
import wa_balcao as WA
import wa_modelos as MOD
from bd_nativo import banco

SITUACOES_PAGAS = (DP.PAGA, DP.CONCILIADA, DP.PAGA_FORA)


def init_contato_schema(con) -> None:
    """As duas colunas do contato. Idempotente. Depois das tabelas das despesas."""
    bd = banco(con)
    for tabela in ("dp_despesas", "dp_recorrentes"):
        for coluna in ("contato_email", "contato_whatsapp"):
            if not bd.tem_coluna(tabela, coluna):
                bd.escrever(f"ALTER TABLE {tabela} ADD COLUMN {coluna} TEXT NOT NULL DEFAULT ''")


def gravar_contato(con, despesa_id: int, *, email: Any, whatsapp: Any, por: str,
                   agora: datetime) -> None:
    """Muda o contato da despesa. ESCREVE. Vale em qualquer situação: não mexe no pagamento."""
    email, whatsapp = DP.conferir_contato(email, whatsapp)
    bd = banco(con)
    DP._prender(bd, despesa_id)
    bd.escrever("UPDATE dp_despesas SET contato_email = %s, contato_whatsapp = %s WHERE id = %s",
                (email, whatsapp, int(despesa_id)))
    DP._evento(bd, despesa_id, "CONTATO", "ok", "Contato do comprovante alterado", por,
               DP._carimbo(agora))


def foi_paga(d: dict) -> bool:
    return d["situacao"] in SITUACOES_PAGAS


def _dia(valor: Any) -> str:
    try:
        return date.fromisoformat(str(valor or "")[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return ""


def texto(d: dict) -> tuple[str, str]:
    """O assunto e o corpo. Só calcula. Sem CPF, sem chave Pix e sem conta."""
    linhas = ["Demonstrativo de pagamento", "",
              f"Favorecido: {d['beneficiario_nome']}",
              f"Referente a: {d['descricao']}",
              f"Valor: R$ {DP.reais(int(d['valor']))}"]
    dia = _dia(d.get("data_pagamento")) or _dia(d.get("paga_em"))
    if dia:
        linhas.append(f"Data do pagamento: {dia}")
    if d.get("banco_e2e"):
        linhas.append(f"Identificador do Pix: {d['banco_e2e']}")
    return "Demonstrativo de pagamento", "\n".join(linhas)


AVISO_DO_PAPEL = ("Documento gerado pelo sistema da serventia com os dados informados pelo banco. "
                  "Não substitui o comprovante emitido pelo banco. O identificador do Pix (E2E) "
                  "permite localizar este pagamento.")


def pode_gerar(d: dict) -> bool:
    """Há o que afirmar? Paga, com o E2E do banco e sem dúvida sobre quem recebeu."""
    return (foi_paga(d) and bool(d.get("banco_e2e"))
            and not (d.get("recebedor_divergente") and not d.get("recebedor_aceito_em")))


def nome_do_demonstrativo(d: dict) -> str:
    return f"demonstrativo_de_pagamento_{int(d['id'])}.pdf"


def linhas_do_demonstrativo(d: dict, serventia: dict) -> list[tuple[str, str]]:
    """O que o papel diz, na ordem. Só calcula. CPF sempre mascarado; a chave Pix não vai."""
    linhas = [("Pagador", serventia.get("unit_name") or ""),
              ("Favorecido", d["beneficiario_nome"]),
              ("CPF/CNPJ do favorecido", SERV.mascarar_documento(d.get("beneficiario_documento"))),
              ("Referente a", d["descricao"]),
              ("Valor", f"R$ {DP.reais(int(d['valor']))}"),
              ("Data do pagamento", _dia(d.get("data_pagamento")) or _dia(d.get("paga_em"))),
              ("Banco do pagador", "Banco Inter, por Pix"),
              ("Identificador do Pix (E2E)", d.get("banco_e2e") or ""),
              ("Recebedor informado pelo banco", d.get("banco_recebedor_nome") or ""),
              ("CPF/CNPJ informado pelo banco", d.get("banco_recebedor_documento") or ""),
              ("Instituição do recebedor", d.get("banco_recebedor_instituicao") or ""),
              ("Despesa nº", str(d["id"]))]
    return [(rotulo, valor) for rotulo, valor in linhas if valor]


def _para_a_fonte(valor: str) -> str:
    """A fonte do PDF só desenha o Latin-1: o travessão da descrição sairia como «?»."""
    for de, para in (("—", "-"), ("–", "-"), ("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'")):
        valor = valor.replace(de, para)
    return valor.encode("latin-1", "replace").decode("latin-1")


def pdf_do_demonstrativo(d: dict, serventia: dict, agora: datetime) -> bytes:
    """O PDF do demonstrativo. Só calcula. Recusa o que não pode afirmar."""
    if not pode_gerar(d):
        raise DP.DespesaError("O demonstrativo sai depois que a conferência do extrato trouxer o "
                              "identificador do Pix, e sem dúvida sobre quem recebeu.")
    import pymupdf
    doc = pymupdf.open()
    pagina = doc.new_page(width=595, height=842)
    pagina.insert_text((50, 70), "DEMONSTRATIVO DE PAGAMENTO", fontname="hebo", fontsize=16)
    y = 100
    for rotulo, valor in linhas_do_demonstrativo(d, serventia):
        valor = _para_a_fonte(valor)
        altura = 18 * (1 + len(valor) // 55)
        pagina.insert_textbox(pymupdf.Rect(50, y, 215, y + altura), rotulo, fontname="hebo", fontsize=10)
        pagina.insert_textbox(pymupdf.Rect(220, y, 545, y + altura), valor, fontname="helv", fontsize=10)
        y += altura + 4
    pagina.draw_line((50, y + 6), (545, y + 6), width=0.5)
    pagina.insert_textbox(pymupdf.Rect(50, y + 14, 545, y + 60), AVISO_DO_PAPEL, fontname="helv", fontsize=9)
    pagina.insert_text((50, y + 76), f"Emitido em {agora.strftime('%d/%m/%Y às %H:%M')}.",
                       fontname="helv", fontsize=9)
    try:
        return doc.tobytes()
    finally:
        doc.close()


def _pronta(con, despesa_id: int) -> dict:
    d = DP.despesa(con, despesa_id)
    if not d:
        raise DP.DespesaError("Despesa não encontrada.")
    if not foi_paga(d):
        raise DP.DespesaError("O comprovante só sai depois de a despesa estar paga.")
    if d["recebedor_divergente"] and not d["recebedor_aceito_em"]:
        raise DP.DespesaError("O banco informa outro recebedor para este pagamento: resolva "
                              "isso na ficha antes de mandar o comprovante.")
    return d


def _conferir_anexo(con, despesa_id: int, anexo_id: Any) -> tuple[str, bytes, str] | None:
    """O arquivo escolhido, se ele é mesmo desta despesa. Só LÊ."""
    if not str(anexo_id or "").isdigit():
        return None
    achado = next((a for a in DP.anexos(con, despesa_id) if a["id"] == int(anexo_id)), None)
    if not achado:
        raise DP.DespesaError("Esse arquivo não é desta despesa.")
    try:
        dados = Path(achado["stored_path"]).read_bytes()
    except OSError as erro:
        raise DP.DespesaError("Não consegui ler o arquivo escolhido.") from erro
    mime = mimetypes.guess_type(achado["original_name"])[0] or "application/octet-stream"
    return achado["original_name"], dados, mime


def _registrar(db, despesa_id: int, mensagem: str, por: str, agora: datetime) -> None:
    with db.transaction() as con:
        DP._evento(banco(con), despesa_id, "COMPROVANTE", "ok", mensagem, por, DP._carimbo(agora))


def enviar_email(db, despesa_id: int, *, por: str, agora: datetime, anexo_id: Any = None,
                 pasta_dados: Any = None) -> None:
    """Manda pelo SMTP da automação, para o e-mail da despesa. ESCREVE o rastro depois."""
    import automacao_avisos as AV
    with db.connect() as con:
        d = _pronta(con, despesa_id)
        cfg = AV.configuracao_de_email(con)
        anexo = _conferir_anexo(con, despesa_id, anexo_id)
    if not d.get("contato_email"):
        raise DP.DespesaError("Esta despesa não tem e-mail: preencha o contato.")
    if not cfg["host"]:
        raise DP.DespesaError("O e-mail da casa não está configurado (Automação → avisos).")
    assunto, corpo = texto(d)
    anexos = [anexo] if anexo else []
    if pode_gerar(d):
        anexos.insert(0, (nome_do_demonstrativo(d),
                          pdf_do_demonstrativo(d, SERV.dados(db.get_settings), agora),
                          "application/pdf"))
    if not anexos:
        raise DP.DespesaError("Ainda não há o que mandar: o demonstrativo espera o identificador "
                              "do Pix na conferência do extrato, e nenhum arquivo foi escolhido.")
    extra = {"anexos": anexos}
    try:
        AV.ENVIO["email"](dict(cfg, destinos=[d["contato_email"]]),
                          AV._senha_do_smtp(pasta_dados, cfg), assunto=assunto, corpo=corpo, **extra)
    except (OSError, smtplib.SMTPException, ValueError) as erro:
        raise DP.DespesaError(f"O e-mail não saiu: {erro}") from erro
    nomes = ", ".join(a[0] for a in anexos)
    _registrar(db, despesa_id, f"Por e-mail, com {nomes}", por, agora)


def _conversa(con, numero: str) -> dict | None:
    """A conversa deste número. A Meta às vezes guarda o celular sem o nono dígito."""
    variantes = [numero]
    if len(numero) == 13 and numero[4] == "9":
        variantes.append(numero[:4] + numero[5:])
    elif len(numero) == 12:
        variantes.append(numero[:4] + "9" + numero[4:])
    for variante in variantes:
        achada = banco(con).um("SELECT id, wa_id FROM wa_conversa WHERE wa_id = %s", (variante,))
        if achada:
            return achada
    return None


def whatsapp_na_ficha(con, d: dict, agora: Any) -> dict | None:
    """O que a ficha oferece: enviar pela casa, ou o link. Só LÊ."""
    if not foi_paga(d) or not d.get("contato_whatsapp"):
        return None
    conversa = _conversa(con, d["contato_whatsapp"])
    aberta = bool(conversa) and not MOD.fora_da_janela(
        WA.ultima_do_cliente(con, conversa["id"]), agora)
    link = (f"https://wa.me/{d['contato_whatsapp']}?text="
            f"{urllib.parse.quote(texto(d)[1])}")
    return {"janela_aberta": aberta, "link": link}


def enviar_whatsapp(db, despesa_id: int, *, por: str, agora: datetime, agora_texto: str,
                    pasta_arquivos: Any) -> None:
    """Manda o PDF pela conta da casa, dentro da janela de 24 h. ESCREVE o rastro depois."""
    import wa_midia as MIDIA
    import wa_schema as SCH
    with db.connect() as con:
        d = _pronta(con, despesa_id)
        if not d.get("contato_whatsapp"):
            raise DP.DespesaError("Esta despesa não tem WhatsApp: preencha o contato.")
        conversa = _conversa(con, d["contato_whatsapp"])
        if not conversa or MOD.fora_da_janela(WA.ultima_do_cliente(con, conversa["id"]), agora_texto):
            raise DP.DespesaError("Essa pessoa não escreveu à casa nas últimas 24 horas, e a Meta "
                                  "recusaria. Use «Abrir no WhatsApp».")
        token = WA.ler_config(con, SCH.CHAVE_TOKEN)
        phone = WA.ler_config(con, SCH.CHAVE_PHONE)
    corpo = texto(d)[1]
    dados = pdf_do_demonstrativo(d, SERV.dados(db.get_settings), agora)
    nome = nome_do_demonstrativo(d)
    salvo = None
    try:
        tipo, mime = MIDIA.conferir_envio(nome, len(dados))
        salvo = MIDIA.guardar(MIDIA.pasta_do_mes(pasta_arquivos, agora_texto), nome, dados)
        midia_id = MIDIA.subir(token, phone, dados, mime, salvo["nome"])
        with db.connect() as con:
            pedido = MIDIA.montar_envio(con, conversa["wa_id"], tipo, midia_id, legenda=corpo,
                                        nome=salvo["nome"])
        meta_id = WA.postar_envio(pedido)
    except (MIDIA.MidiaErro, WA.EnvioErro) as erro:
        # O que não saiu não fica guardado como se tivesse saído.
        if salvo and salvo.get("novo"):
            Path(salvo["caminho"]).unlink(missing_ok=True)
        raise DP.DespesaError(f"O WhatsApp não saiu: {erro}") from erro
    with db.transaction() as con:
        WA.gravar_saida(con, conversa["id"], corpo, meta_id, autor=por, agora=agora_texto,
                        tipo=tipo, arquivo={**salvo, "mime": mime})
    _registrar(db, despesa_id, f"Pelo WhatsApp da casa, com {nome}", por, agora)
