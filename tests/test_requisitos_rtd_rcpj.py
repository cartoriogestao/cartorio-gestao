"""O QUE A LEI E AS NORMAS MANDAM O TERMO E A CERTIDÃO DIZEREM — RTD e RCPJ (LT05).

    «os modelos têm de abarcar o que a LEI e as NORMAS exigem» — o oficial,
    20/10/2026

A MATRIZ É ESTA LISTA (`REQUISITOS`), e `docs/REQUISITOS_LEGAIS.md` (seção do
RTD e do RCPJ) é ela escrita em prosa: cada linha é UM elemento obrigatório de
UM papel, com o artigo que o exige. Para cada linha o teste:

    1. MONTA O PAPEL com um contexto de teste COMPLETO — o mesmo montador que a
       tela chama (`rg_teor_rtdpj.gerar_pdf`, `atrib_certidao.montar_teor` e o
       papel por texto, `rg_certidao_pdf.gerar_pdf`, `rg_notificacao`,
       `rg_livro_contabil`, `rg_web.papel_html`), e não uma cópia do texto;
    2. CONFERE QUE O ELEMENTO APARECE NO PAPEL — o rótulo e o valor;
    3. CONFERE QUE O MODELO DA CASA TEM O CAMPO — o padrão em `modelos_padrao/`
       (o claro `{…}` ou a variável Jinja), porque o elemento que só aparece
       porque o código o escreve some no primeiro ajuste da casa.

    Os PDFs são imagem: o texto deles se lê CAPTURANDO o que se desenha
    (`ImageDraw.text`) — é exatamente o que vai para a folha, selo incluído.

PRECEDÊNCIA DAS FONTES (pedido do oficial): Lei 6.015/1973 (LRP) e leis da
atribuição; Código Nacional de Normas (Prov. CNJ 149/2023); Código de Normas
Extrajudicial do MA (Prov. COGEX 28/2026, «CN-MA»). Os textos estão em
`referencia/normas/` e `referencia/codigo_de_normas_extrajudicial_ma.txt`.

ELEMENTO QUE O MODELO NÃO TEM É DEFEITO DO MODELO: está `xfail(strict=True)` com
o artigo. `strict` faz o teste avisar no dia em que o modelo ganhar o campo.

O LD09 (21/10/2026) consertou os que faltavam por falta do DADO: o protocolo e o
apresentante saem do título; o extrato do Livro C, as indicações do art. 120 e
a matrícula do periódico são declarações que quem lavra escreve na tela do
registro e que ficam no ato (`rg_registro.DECLARACOES_POR_SERIE`); o total de
páginas do Livro F é a conta das folhas; o número da averbação é o do ato.

O LIVRO E A FOLHA NO ALTO DO TERMO ficaram em `xfail` até a resposta do
oficial (21/10/2026, pergunta 28): ele decidiu NÃO pô-los — a LRP art. 133 se
lê com as normas que permitem o livro digital, e no livro digital «livro e
folha» no cabeçalho não fazem sentido. Os sete casos viraram o registro da
decisão: conferem que o cabeçalho do termo NÃO os cita (LH13).

Dados fictícios (LGPD).
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

from bd_nativo import banco  # noqa: E402
from conftest import cg_login  # noqa: E402

SENHA = "Senha#12345"
SERVENTIA = "Ofício Único de Cidade Exemplo/MA"
CNS = "000000"
OFICIAL = "FULANO DE EXEMPLO"
TITULO_DO_OFICIAL = "Oficial de Registro"
FUNCAO = "Escrevente Substituto"
CIDADE = "Cidade Exemplo"
NUMERO_REGISTRO = 4321
FOLHA = 17
VOLUME = "3"
DIA_DO_ATO = date(2026, 10, 5)
DIA_DO_ATO_EXTENSO = "5 de outubro de 2026"
PROTOCOLO = "987"
DATA_DO_PROTOCOLO = "02/10/2026"
APRESENTANTE = "SICRANO APRESENTANTE DE EXEMPLO"
NATUREZA = "Contrato de locação de imóvel residencial"
DATA_ASSINATURA = "01/10/2026"
DENOMINACAO = "ASSOCIAÇÃO DE EXEMPLO"
TEOR_DO_REGISTRO = "CONTRATO DE EXEMPLO, trasladado na íntegra, com 3 folhas."
TEOR_DA_AVERBACAO = ("CERTIFICO que me foi apresentado para ser AVERBADO no Registro "
                     f"nº {NUMERO_REGISTRO} o documento digitalizado abaixo:\n"
                     "Tipo do ato: Aditivo de prorrogação do prazo.\n"
                     "Data da assinatura: 03/10/2026.")
SELO_DO_ATO = "AUTENT000000TESTE0000004321"
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")
SELO_DA_CERTIDAO = "AUTENT000000TESTE0000009876"


def _texto_do_selo(numero: str, ato: str, total: str, emol: str) -> str:
    """O texto que o aparelho devolve (a forma medida em test_selo_no_papel)."""
    return (f"Poder Judiciario - TJMA. Selo: {numero}, 05/10/2026 10:00:00, "
            f"Ato: {ato}, Total R$ {total} Emol R$ {emol} FERC R$ 1,44 "
            f"FADEP R$ 1,91 FEMP R$ 1,91 Consulte em https://selo.tjma.jus.br")


def _selo(numero: str, ato: str, total: str, emol: str) -> dict:
    return {"numero": numero, "texto": _texto_do_selo(numero, ato, total, emol),
            "qr_texto": f"https://selo.tjma.jus.br/#/resumo/{numero}"}


SV = {"unit_name": SERVENTIA, "ri_cns": CNS, "ri_cidade": CIDADE, "ri_uf": "MA",
      "serventia_titular": OFICIAL, "serventia_titulo": TITULO_DO_OFICIAL,
      "serventia_endereco": "Rua de Exemplo, 1", "serventia_cep": "65000-000",
      "serventia_telefone": "(99) 0000-0000", "serventia_email": "contato@exemplo.invalid",
      "serventia_cnpj": ""}


def _normal(texto: str) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def _sem_tags(html: str) -> str:
    import html as H
    return _normal(H.unescape(re.sub(r"<[^>]+>", " ", html)))


# ------------------------------------------------------------ os montadores


def _desenhado(monkeypatch, gerar) -> str:
    """O texto que o PDF desenha — capturado de `ImageDraw.text`."""
    from PIL import ImageDraw
    linhas: list[str] = []
    desenhar = ImageDraw.ImageDraw.text

    def capturar(self, xy, texto, *a, **kw):
        linhas.append(str(texto))
        return desenhar(self, xy, texto, *a, **kw)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", capturar)
    try:
        pdf = gerar()
    finally:
        monkeypatch.setattr(ImageDraw.ImageDraw, "text", desenhar)
    assert pdf.startswith(b"%PDF")
    return _normal(" ".join(linhas))


def _folha():
    from PIL import Image
    return Image.new("RGB", (600, 800), "white")


# AS DECLARAÇÕES QUE A LAVRATURA GRAVA NO ATO (LD09, 21/10/2026), uma por
# livro — o que quem lavra escreve na tela do registro, e o termo reimprime
# (`rg_registro.DECLARACOES_POR_SERIE`). Fictícias (LGPD).
DECLARACOES_DE_EXEMPLO = {
    "TD_C": {   # o extrato (LRP art. 143; CN-MA art. 981)
        "valor": "R$ 12.345,67", "prazo": "doze meses", "lugar": CIDADE,
        "partes": ("LOCADOR: FULANO DE EXEMPLO, brasileiro, comerciante; "
                   "LOCATÁRIA: BELTRANA DE EXEMPLO, brasileira, professora"),
        "testemunhas": "CICLANO DE EXEMPLO e DEOCLÉCIA DE EXEMPLO",
        "reconhecimento": ("02/10/2026, por semelhança, no Tabelionato de "
                           "Exemplo (tabelião JOÃO DE EXEMPLO)"),
        "imposto": "nenhum devido (locação não é fato gerador de imposto)"},
    "PJ_A": {   # a inscrição da pessoa jurídica (LRP art. 120)
        "denominacao": DENOMINACAO, "fins": "promover a cultura de exemplo",
        "sede": "Rua de Exemplo, 100, Centro, Cidade Exemplo/MA",
        "duracao": "por tempo indeterminado",
        "administracao": ("pela diretoria; representa-a o presidente, ativa e "
                          "passivamente, judicial e extrajudicialmente"),
        "reforma": "sim, pela assembleia geral, por dois terços dos associados",
        "responsabilidade": "não",
        "extincao": ("por deliberação da assembleia; o patrimônio vai a "
                     "entidade de fins iguais"),
        "fundadores": "FULANO DE EXEMPLO, brasileiro, casado, comerciante",
        "diretoria": "FULANA DE EXEMPLO (presidente), brasileira, solteira, professora",
        "residencia_apresentante": "Rua do Apresentante, 1, Cidade Exemplo/MA"},
    "PJ_B": {   # a matrícula do periódico (LRP art. 123, I)
        "titulo_periodico": "GAZETA DE EXEMPLO",
        "sede_redacao": "Rua da Redação, 10, Cidade Exemplo/MA",
        "oficinas": "oficina própria, na sede da redação",
        "diretor": "FULANO DE EXEMPLO, 40 anos, brasileiro, Rua de Exemplo, 2",
        "proprietario": "EDITORA DE EXEMPLO LTDA, Rua de Exemplo, 3"},
}


def _dados_do_teor(*, serie: str, tipo: str, motivo=None) -> dict:
    """O que a rota passa ao teor — lido do ato e do título
    (`rg_registro.dados_do_termo`, LD09): o protocolo e o apresentante do
    título e as declarações do livro, no registro; o número de ordem, na
    averbação."""
    declarado = {}
    if tipo == "REGISTRO":
        declarado = dict(protocolo=PROTOCOLO, data_protocolo=DATA_DO_PROTOCOLO,
                         apresentante=APRESENTANTE,
                         declaracoes=DECLARACOES_DE_EXEMPLO.get(serie))
    elif tipo == "AVERBACAO":
        declarado = dict(numero_averbacao=NUMERO_REGISTRO + 1)
    return dict(motivo=motivo, numero_registro=NUMERO_REGISTRO,
                lavrante_nome=OFICIAL, lavrante_funcao=FUNCAO, cns=CNS,
                unit_short=SERVENTIA, cidade=CIDADE, uf="MA", dia=DIA_DO_ATO,
                serie=serie, atribuicao=3 if serie.startswith("PJ") else 4,
                tipo_ato=tipo, natureza_ato=NATUREZA, data_assinatura=DATA_ASSINATURA,
                **declarado)


def _termo(monkeypatch, *, serie: str, tipo: str, motivo=None) -> str:
    """O termo do ato (PDF do teor), como `rcpj_rtd_ato_teor` o monta."""
    import rg_teor_rtdpj as RGTEOR
    return _desenhado(monkeypatch, lambda: RGTEOR.gerar_pdf(
        imagens=[_folha()], selo_averbacao=_selo(SELO_DO_ATO, "15.3.1", "91,61", "81,80"),
        **_dados_do_teor(serie=serie, tipo=tipo, motivo=motivo)))


def _serie_e_tipo_do_termo(papel: str) -> tuple[str, str]:
    serie = {"TERMO_AV_TD": "TD_B", "TERMO_AV_PJ": "PJ_A"}.get(papel, papel[6:])
    return serie, ("AVERBACAO" if papel.startswith("TERMO_AV") else "REGISTRO")


def _cabecalho_do_termo(papel: str) -> list[str]:
    """As linhas do alto de cada folha do termo, como `gerar_pdf` as recebe
    de `textos_prontos` — o mesmo ato de `_termo`."""
    import rg_teor_rtdpj as RGTEOR
    serie, tipo = _serie_e_tipo_do_termo(papel)
    return RGTEOR.textos_prontos(**_dados_do_teor(serie=serie, tipo=tipo))[
        "linhas_cabecalho"]


def _dados_do_registro(serie: str) -> dict:
    atribuicao = 3 if serie.startswith("PJ") else 4
    registro = {"id": 1, "atribuicao": atribuicao, "serie": serie,
                "numero": NUMERO_REGISTRO, "volume": None, "natureza": NATUREZA,
                "requerente_nome": DENOMINACAO, "situacao": "ATIVO",
                "teor": TEOR_DO_REGISTRO}
    # o registro com o selo dele: a certidão o reproduz abaixo do ato (LD05)
    atos = [{"id": 11, "registro_id": 1, "tipo": "REGISTRO", "folha": FOLHA,
             "numero_ordem": NUMERO_REGISTRO, "data_ato": "2026-10-05T10:00:00",
             "teor": TEOR_DO_REGISTRO, "livro_numero": VOLUME, "selo": SELO_DO_ATO},
            {"id": 12, "registro_id": 1, "tipo": "AVERBACAO", "folha": FOLHA + 1,
             "numero_ordem": NUMERO_REGISTRO + 1, "data_ato": "2026-10-06T10:00:00",
             "teor": TEOR_DA_AVERBACAO, "livro_numero": VOLUME}]
    return {"registro": registro, "atos": atos}


def _certidao_por_texto(*, serie: str, ato_ids=None) -> str:
    """A certidão por texto (.odt): o teor de `montar_teor` no papel
    RCPJ_RTD_CERTIDAO_ODT, mais o carimbo do selo — o que a rota imprime."""
    import atrib_certidao as CE
    import modelos_da_casa as MODELOS
    import ri_odt as RODT
    chave = "RCPJ_CERTIDAO" if serie.startswith("PJ") else "RTD_CERTIDAO"
    teor = CE.montar_teor(
        "RCPJ_RTD", _dados_do_registro(serie), modelo=MODELOS.padrao_de(chave),
        ato_ids=ato_ids,
        modelo_so_averbacoes=MODELOS.padrao_de(CE.CHAVE_SO_AVERBACOES))
    certidao = {"numero": 12, "ano": 2026, "teor": teor, "cancelada": 0,
                "motivo_cancelamento": None, "emitida_em": "2026-10-05T10:00:00",
                "hash_certidao": "ab" * 32}
    import serventia
    papel = CE._montar_papel_por_texto(
        MODELOS.padrao_de(CE.CHAVE_PAPEL_POR_TEXTO), certidao,
        sv=serventia.dados(SV), hoje=DIA_DO_ATO_EXTENSO)
    carimbo, _ = RODT.carimbo_da_certidao_odf(
        _texto_do_selo(SELO_DA_CERTIDAO, "15.10.1", "53,58", "47,84"))
    return _sem_tags(papel + " " + carimbo)


def _certidao_por_reproducao(monkeypatch, *, serie: str) -> str:
    """A certidão em PDF (capa e folhas), como `atribuicoes_certidao_imprimir`."""
    import rg_certidao_pdf as RGCERT
    return _desenhado(monkeypatch, lambda: RGCERT.gerar_pdf(
        numero=NUMERO_REGISTRO, imagens=[_folha()], lavrante_nome=OFICIAL,
        lavrante_funcao=FUNCAO, denominacao=DENOMINACAO, natureza=NATUREZA,
        data_registro="2026-10-05", protocolo=PROTOCOLO,
        data_apresentacao="2026-10-02", cns=CNS, unit_short=SERVENTIA,
        oficial=OFICIAL, endereco="Rua de Exemplo, 1", cidade=CIDADE, uf="MA",
        serie=serie, atribuicao=3 if serie.startswith("PJ") else 4,
        volume=VOLUME, dia=DIA_DO_ATO, certidao_numero="12", certidao_ano="2026",
        com_emolumentos=False,
        selo=_selo(SELO_DA_CERTIDAO, "15.10.1", "53,58", "47,84")))


def _nota_devolutiva() -> str:
    import modelos_da_casa as MODELOS
    import rg_web as RGW
    import serventia
    contexto = dict(
        t={"id": 1, "numero": 987, "rotulo": "3", "data_apresentacao": "2026-10-02",
           "hora": "09:15:00", "apresentante": APRESENTANTE,
           "apresentante_documento": "00000000191", "natureza": NATUREZA},
        q={"exigencias": "Apresentar o original com firma reconhecida do credor.",
           "fundamentacao": "Lei 6.015/1973, art. 130, § 3º.",
           "prazo_ate": "2026-11-20", "data_qualificacao": "2026-10-05"},
        sv=serventia.dados(SV), data_extenso=DIA_DO_ATO_EXTENSO, oficial=OFICIAL,
        funcao=FUNCAO, nome_da_atribuicao="RTD — Registro de Títulos e Documentos",
        apresentado_em="02/10/2026", qualificado_em="05/10/2026",
        prazo_ate="20/11/2026", fmt_date=str)
    return _sem_tags(RGW.papel_html(MODELOS.padrao_de(RGW.CHAVE_NOTA), contexto,
                                    chave=RGW.CHAVE_NOTA))


def _etiqueta() -> str:
    import modelos_da_casa as MODELOS
    import notas_selo as NSELO
    import rg_web as RGW
    import selo_no_papel as SNPAPEL
    marca = NSELO.marca_do_selo(SELO_DO_ATO)
    e = {"atribuicao": "RTD — Registro de Títulos e Documentos", "cartorio": SERVENTIA,
         "tipo": "REGISTRO", "livro": VOLUME, "serie": "TD_B", "folha": FOLHA,
         "numero": NUMERO_REGISTRO, "data": "05/10/2026", "natureza": NATUREZA,
         "requerente": APRESENTANTE, "protocolo": PROTOCOLO, "selo": SELO_DO_ATO,
         "oficial": OFICIAL, "funcao": FUNCAO, "qr": marca["qr"],
         "qr_texto": marca["qr_texto"], "qr_possivel": marca["qr_possivel"],
         "valores": SNPAPEL.linha_de_valores(
             _texto_do_selo(SELO_DO_ATO, "15.3.1", "91,61", "81,80"))}
    html = RGW.papel_html(MODELOS.padrao_de(RGW.CHAVE_ETIQUETA),
                          {"e": e, "m": {}, "vez": 1}, chave=RGW.CHAVE_ETIQUETA)
    return _sem_tags(html) + (" QR-DO-SELO" if "<svg" in html else "")


# ---- os que precisam da casa: a notificação e o livro contábil, montados pelo
# domínio (o mesmo da tela) e lidos na página que imprime

def _dias_validos(db, quantos: int) -> list[str]:
    """Dias passados em que a norma deixa diligenciar (CN-MA art. 986, § 4º),
    um sim e um não — dias alternados —, do mais antigo para o mais novo."""
    from datetime import timedelta

    from ri_schema import feriados_nacionais, ler_feriados_locais
    locais = ler_feriados_locais(db.get_setting("ri_feriados_locais", ""))
    dias, d = [], date.today() - timedelta(days=1)
    while len(dias) < quantos:
        if d.weekday() != 6 and d not in feriados_nacionais(d.year) | locais:
            dias.append(d.isoformat())
            d -= timedelta(days=1)
        d -= timedelta(days=1)
    return sorted(dias)


def _gravar_selo(bd, numero: str, tabela: str, ato_id: int, ato: str,
                 total: str, emol: str) -> None:
    bd.escrever(
        """INSERT INTO sd_selos(numero, texto, sid, caminho, atribuicao, referencia,
               ambiente, obtido_em, obtido_por, tabela, ato_id)
           VALUES (%s,%s,%s,'/selo/rtdpj/atos-em-geral','RTD',%s,'HOMOLOGACAO',
                   '2026-10-05T10:00:00',%s,%s,%s)""",
        (numero, _texto_do_selo(numero, ato, total, emol), f"sid-{numero}",
         f"{tabela}:{ato_id}", OFICIAL, tabela, ato_id))


def _notificacao(casa, resultado: str) -> dict:
    """Registro, notificação, idas, certidão e averbação — pelo domínio."""
    import rg_notificacao as N
    import rg_registro as RG
    import serventia
    db = casa["db"]
    dia = _dias_validos(db, 1)[0]
    with db.transaction() as con:
        bd = banco(con)
        r = RG.abrir_registro(con, serie="TD_B", sv=serventia.dados(SV),
                              agora=f"{dia}T09:00:00", data_extenso=DIA_DO_ATO_EXTENSO,
                              natureza="Notificação extrajudicial",
                              requerente_nome=APRESENTANTE,
                              teor="NOTIFICAÇÃO EXTRAJUDICIAL DE EXEMPLO.")
        nid = N.abrir(con, registro_id=r["registro_id"], agora=f"{dia}T09:00:00",
                      destinatario_nome="CICLANO DESTINATÁRIO DE EXEMPLO",
                      destinatario_documento="00000000191",
                      endereco="Rua do Destinatário, 100, Centro", usuario=OFICIAL)
        bd.escrever("UPDATE rg_notificacoes SET apresentado_em=%s WHERE id=%s",
                    ("2000-01-03", nid))
    idas = ([("10:00", "ENTREGUE")] if resultado == "POSITIVA" else
            [("09:00", "AUSENTE"), ("14:00", "NAO_LOCALIZADO"), ("19:00", "MUDOU_SE")])
    datas = _dias_validos(db, len(idas))
    with db.transaction() as con:
        for (hora, achado), d in zip(idas, datas):
            N.registrar_ida(con, nid, data=d, hora=hora, resultado=achado,
                            agora=f"{dia}T21:00:00", usuario=OFICIAL)
        banco(con).escrever(
            "UPDATE rg_notificacao_diligencias SET selo_situacao='SELADO' "
            "WHERE notificacao_id=%s", (nid,))
        if resultado == "NEGATIVA":
            N.certificar_negativa(con, nid, agora=f"{dia}T21:00:00", usuario=OFICIAL)
        c = N.emitir_certidao(con, nid, agora=f"{dia}T21:10:00", sv=serventia.dados(SV),
                              data_extenso=DIA_DO_ATO_EXTENSO, usuario=OFICIAL)
        banco(con).escrever(
            "UPDATE rg_notificacao_certidoes SET selo=%s, selo_situacao='SELADO' "
            "WHERE id=%s", (SELO_DA_CERTIDAO, c["certidao_id"]))
        _gravar_selo(banco(con), SELO_DA_CERTIDAO, "rg_notificacao_certidoes",
                     c["certidao_id"], "15.8.2", "53,58", "47,84")
        lugar = N.averbar(con, nid, sv=serventia.dados(SV), agora=f"{dia}T21:20:00",
                          data_extenso=DIA_DO_ATO_EXTENSO, usuario=OFICIAL)
    cliente = casa["app"].test_client()
    cg_login(cliente, "oficial", SENHA)
    pagina = cliente.get(f"/rcpj-rtd/notificacao/certidao/{c['certidao_id']}")
    with db.connect() as con:
        averbacao = banco(con).valor("SELECT teor FROM rg_atos WHERE id=%s",
                                     (lugar["ato_id"],))
    html = pagina.get_data(as_text=True)
    return {"certidao": _sem_tags(html) + (" QR-DO-SELO" if 'class="qr"' in html else ""),
            "averbacao": _normal(averbacao), "datas": datas, "registro": r}


def _livro_contabil(casa, qual: str) -> str:
    import rg_livro_contabil as LC
    import serventia
    db = casa["db"]
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever("""INSERT INTO cx_servicos (codigo, codigo_tj, descricao, ativo)
                       VALUES (493, '15.7.1', 'Até cinco folhas', 1)
                       ON CONFLICT (codigo) DO NOTHING""")
        p = LC.pedir(con, {"pj_nome": DENOMINACAO, "pj_cnpj": "00.000.043/0001-77",
                           "tipo_livro": "DIARIO", "numero_livro": "2", "folhas": "100",
                           "forma": "PAPEL"}, agora="2026-10-05T09:00:00", usuario=OFICIAL)
        LC.autenticar(con, p["id"], codigo_tj="15.7.1", serventia=serventia.dados(SV),
                      hoje="2026-10-05", agora="2026-10-05T10:00:00", usuario=OFICIAL,
                      funcao=FUNCAO)
        bd.escrever("UPDATE rg_livros_contabeis SET selo=%s WHERE id=%s",
                    (SELO_DO_ATO, p["id"]))
        LC.marcar_selado(con, p["id"])
        _gravar_selo(bd, SELO_DO_ATO, "rg_livros_contabeis", p["id"], "15.7.1",
                     "99,07", "89,52")
    db.set_settings(SV)
    cliente = casa["app"].test_client()
    cg_login(cliente, "oficial", SENHA)
    html = cliente.get(f"/rcpj-rtd/livros-contabeis/{p['id']}/papel/{qual}").get_data(
        as_text=True)
    papel = re.search(r'<pre class="papel"[^>]*>(.*?)</pre>', html, re.S).group(1)
    selo = re.search(r'class="selo-da-autenticacao".*?</div>\s*</div>', html, re.S)
    return (_sem_tags(papel) + " " + (_sem_tags(selo.group(0)) if selo else "")
            + (" QR-DO-SELO" if 'class="qr"' in html else ""))


# ------------------------------------------------------------- a matriz


@dataclass(frozen=True)
class Req:
    papel: str               # a chave do papel na matriz (ver MONTADORES)
    elemento: str            # o que a norma exige, em palavras
    artigo: str              # de onde vem a exigência
    esperado: tuple          # o rótulo e o valor, como saem no papel
    campos: tuple = ()       # (chave do modelo padrão, campo) que o carregam
    defeito: str = ""        # o porquê do xfail — vazio quando o papel já diz
    # O QUE A CASA DECIDIU NÃO PÔR (LH13): expressões que NÃO podem estar no
    # cabeçalho do termo, e (chave, campo) que o padrão NÃO pode ter.
    fora_do_cabecalho: tuple = ()
    campos_fora: tuple = ()


def _r(papel, elemento, artigo, esperado, campos=(), defeito="", *,
       fora_do_cabecalho=(), campos_fora=()):
    return Req(papel, elemento, artigo, tuple(esperado), tuple(campos), defeito,
               tuple(fora_do_cabecalho), tuple(campos_fora))


CAMPOS_DO_TERMO = {
    "TERMO_TD_B": "RTD_TEOR_REGISTRO", "TERMO_TD_C": "RTD_TEOR_REGISTRO",
    "TERMO_TD_F": "RTD_TEOR_REGISTRO", "TERMO_PJ_A": "RCPJ_TEOR_REGISTRO",
    "TERMO_PJ_B": "RCPJ_TEOR_REGISTRO", "TERMO_AV_TD": "RTD_TEOR_AVERBACAO",
    "TERMO_AV_PJ": "RCPJ_TEOR_AVERBACAO"}


# O ARTIGO DE CADA ELEMENTO DEPENDE DA ATRIBUIÇÃO: a escrituração do RTD está
# na LRP, arts. 132 a 155, e no CN-MA, arts. 963 a 985; a do RCPJ, na LRP,
# arts. 114 a 126, e no CN-MA, arts. 403 a 411 — que não repetem tudo. Onde o
# RCPJ não tem regra própria, vale a do RTD «por analogia», e está dito.
FONTES = {
    "serventia": ("LRP art. 133; CN-MA art. 977",
                  "LRP art. 133, por analogia; CN-MA art. 406"),
    "livro_folha": ("LRP arts. 133 e 135, parágrafo único",
                    "LRP art. 133, por analogia; CN-MA art. 408, § 3º"),
    "numero": ("LRP arts. 136, 1º, e 153; CN-MA art. 973",
               "LRP art. 120, caput; CN-MA art. 409"),
    "especie": ("LRP art. 146; CN-MA art. 966, III",
                "LRP art. 120, caput (a espécie do ato); CN-MA art. 409"),
    "natureza": ("LRP arts. 135, 3º, e 146; CN-MA art. 966, II",
                 "LRP art. 120, caput; CN-MA art. 409"),
    "trasladacao": ("LRP art. 142 e § 1º; CN-MA art. 980",
                    "LRP art. 121; CN-MA art. 406 (lançamento vinculado às imagens)"),
    "subscricao": ("LRP arts. 142, § 1º, e 152; CN-MA art. 972",
                   "Lei 8.935/1994, art. 20; LRP art. 142, § 1º, por analogia"),
    "data": ("LRP art. 152 («datado»); CN-MA art. 972",
             "LRP art. 152, por analogia; CN-MA art. 408, § 1º"),
}


def _comuns_do_termo(papel: str, verbo: str, atribuicao: str) -> list[Req]:
    m = CAMPOS_DO_TERMO[papel]
    i = 1 if "PJ" in papel else 0
    return [
        _r(papel, "a serventia, no alto da folha", FONTES["serventia"][i],
           [SERVENTIA], [(m, "{unit_short}")]),
        _r(papel, "o CNS da serventia", "CN-MA art. 977 (identificação da serventia)",
           [f"CNS {CNS}"], [(m, "{cns}")]),
        _r(papel, "a atribuição (o título do livro)", FONTES["serventia"][i].split(";")[0],
           [atribuicao], [(m, "{atribuicao}")]),
        # ERA `xfail` («a decidir com o oficial»), e virou o REGISTRO DA
        # DECISÃO. O oficial, em 21/10/2026, respondendo à pergunta 28: «28 tem
        # que ser lida em conjunto com outras normas, inclusive estaduais que
        # permitem que esses livros sejam digitais, nao fazendo sentido colocar
        # livro e folha». A LRP arts. 133 e 135 (e o CN-MA art. 408, § 3º, no
        # RCPJ) se leem com as normas do livro digital; o livro e a folha do
        # ato estão na etiqueta, na certidão e no Livro de Protocolo, como a
        # ordem de 11/09/2026 deixou. O caso confere que o alto do termo
        # continua SEM eles — quem os puser de volta muda uma decisão do
        # oficial, e este teste avisa.
        _r(papel, "o livro e a folha FORA do alto do termo (decisão do oficial de 21/10/2026)",
           FONTES["livro_folha"][i], [],
           fora_do_cabecalho=(r"\blivro\b", r"\bfolhas?\b", r"\bfls?\.", r"\bs[ée]rie\b",
                              rf"\b{FOLHA}\b"),
           campos_fora=[(m, "{livro}"), (m, "{folha}")]),
        _r(papel, "o número de ordem do registro", FONTES["numero"][i],
           [f"Registro nº {NUMERO_REGISTRO}"], [(m, "{numero}")]),
        _r(papel, "a espécie do lançamento", FONTES["especie"][i],
           [verbo], [(m, verbo)]),
        _r(papel, "a natureza do título", FONTES["natureza"][i],
           ["Tipo do ato:", NATUREZA], [(m, "{natureza_ato}")]),
        _r(papel, "a trasladação do documento, que o termo encerra", FONTES["trasladacao"][i],
           ["arquivado em sua íntegra mediante digitalização"],
           [(m, "arquivado em sua íntegra")]),
        _r(papel, "quem subscreve e assina, com a função", FONTES["subscricao"][i],
           [f"Eu, {OFICIAL}, {FUNCAO}, o subscrevo e assino"],
           [(m, "{full_name}"), (m, "{funcao}")]),
        _r(papel, "o local e a data do ato", FONTES["data"][i],
           [f"{CIDADE}/MA, {DIA_DO_ATO_EXTENSO}"], [(m, "{cidade}"), (m, "{data_extenso}")]),
        _r(papel, "o selo de fiscalização, no corpo do ato", "CN-MA arts. 130 e 131",
           [SELO_DO_ATO]),
        _r(papel, "a consulta do selo", "CN-MA art. 132",
           ["Consulte em https://selo.tjma.jus.br"],
           [("RCPJ_RTD_PDF_MOLDURA", "{endereco}")]),
        _r(papel, "os emolumentos do ato, no próprio documento", "LRP art. 14, parágrafo único",
           ["Total R$ 91,61", "Emol R$ 81,80"]),
    ]


def _so_do_registro(papel: str) -> list[Req]:
    """A data do protocolo e o apresentante — no RTD pela LRP art. 136; no
    RCPJ pelo art. 120 (caput e VI), que a matrícula segue (art. 126).

    Consertado no LD09 (21/10/2026): o padrão ganhou as linhas
    «Protocolizado em {data_protocolo}, sob o nº {protocolo}.» e
    «Apresentante: {apresentante}.», e a rota as lê do título
    (`rg_registro.dados_do_termo`)."""
    m = CAMPOS_DO_TERMO[papel]
    rcpj = "PJ" in papel
    return [
        _r(papel, "a data do protocolo (da apresentação), antes do registro",
           "LRP art. 120, caput, e 126" if rcpj else "LRP art. 136",
           [f"Protocolizado em {DATA_DO_PROTOCOLO}, sob o nº {PROTOCOLO}"],
           [(m, "{data_protocolo}"), (m, "{protocolo}")]),
        _r(papel, "o nome do apresentante, antes do registro",
           ("LRP art. 120, VI («nome e residência do apresentante»), e 126" if rcpj
            else "LRP arts. 136 e 146; CN-MA art. 966, IV"),
           [f"Apresentante: {APRESENTANTE}"], [(m, "{apresentante}")]),
    ]


REQUISITOS: list[Req] = [
    # ---------------- TERMOS (o que se lavra no livro)
    *_comuns_do_termo("TERMO_TD_B", "REGISTRADO", "Registro de Títulos e Documentos"),
    *_so_do_registro("TERMO_TD_B"),
    *_comuns_do_termo("TERMO_TD_C", "REGISTRADO", "Registro de Títulos e Documentos"),
    *_so_do_registro("TERMO_TD_C"),
    # consertado no LD09 (21/10/2026): o extrato é declaração do ato — quem
    # lavra a escreve na tela do registro, ela vai para `rg_atos.declaracoes`,
    # e o padrão tem uma linha para cada elemento (`DECLARACOES_DE_EXEMPLO`)
    *[_r("TERMO_TD_C", f"no registro por extrato: {nome}",
         "LRP art. 143; CN-MA art. 981, " + inciso, [valor], [("RTD_TEOR_REGISTRO", claro)])
      for nome, inciso, valor, claro in (
          ("o valor", "II", "R$ 12.345,67", "{valor}"),
          ("o prazo", "II", "doze meses", "{prazo}"),
          ("o lugar da celebração", "II", "celebrado em Cidade Exemplo", "{lugar}"),
          ("o nome e a condição jurídica das partes", "III", "LOCADOR:", "{partes}"),
          ("as testemunhas", "IV", "Testemunhas:", "{testemunhas}"),
          ("o reconhecimento de firma e o tabelião", "VI", "firma reconhecida", "{reconhecimento}"),
          ("o imposto pago", "VIII", "imposto", "{imposto}"))],
    *_comuns_do_termo("TERMO_TD_F", "REGISTRADO", "Registro de Títulos e Documentos"),
    *_so_do_registro("TERMO_TD_F"),
    # consertado no LD09: o PDF conta as folhas que traslada, e o padrão tem a
    # linha «Total de páginas registradas: {paginas}.» — só no Livro F
    _r("TERMO_TD_F", "o número total de páginas registradas",
       "LRP art. 127-A, § 3º", ["Total de páginas registradas: 1 página"],
       [("RTD_TEOR_REGISTRO", "{paginas}")]),
    *_comuns_do_termo("TERMO_PJ_A", "REGISTRADO", "Registro Civil das Pessoas Jurídicas"),
    *_so_do_registro("TERMO_PJ_A"),
    # consertado no LD09: as indicações do art. 120 são declaração do ato,
    # escrita na tela do registro e gravada nele, como o extrato do Livro C
    *[_r("TERMO_PJ_A", f"a indicação do art. 120, {inciso}: {nome}",
         f"LRP art. 120, {inciso}; CN-MA art. 409", [valor],
         [("RCPJ_TEOR_REGISTRO", claro)])
      for inciso, nome, valor, claro in (
          ("I", "a denominação, os fins, a sede e a duração", f"Denominação: {DENOMINACAO}",
           "{denominacao}"),
          ("II", "o modo de administração e representação", "administra", "{administracao}"),
          ("III", "se o estatuto é reformável e de que modo", "reformável", "{reforma}"),
          ("IV", "se os membros respondem subsidiariamente", "subsidiariamente",
           "{responsabilidade}"),
          ("V", "as condições de extinção e o destino do patrimônio", "extinção",
           "{extincao}"),
          ("VI", "os fundadores e a diretoria, qualificados", "Diretoria:", "{diretoria}"))],
    *_comuns_do_termo("TERMO_PJ_B", "REGISTRADO", "Registro Civil das Pessoas Jurídicas"),
    *_so_do_registro("TERMO_PJ_B"),
    # consertado no LD09: a matrícula declara o que o art. 123, I, pede
    *[_r("TERMO_PJ_B", f"na matrícula do periódico: {nome}", f"LRP art. 123, I, {alinea}",
         [valor], [("RCPJ_TEOR_REGISTRO", claro)])
      for alinea, nome, valor, claro in (
          ("a", "o título do periódico e a sede da redação", "Título do periódico:",
           "{titulo_periodico}"),
          ("b", "o diretor ou redator-chefe", "Diretor:", "{diretor}"),
          ("c", "o proprietário", "Proprietário:", "{proprietario}"))],
    *_comuns_do_termo("TERMO_AV_TD", "AVERBADO", "Registro de Títulos e Documentos"),
    *_comuns_do_termo("TERMO_AV_PJ", "AVERBADO", "Registro Civil das Pessoas Jurídicas"),
    *[_r(papel, "a data da assinatura do documento averbado",
         "LRP art. 128 (a ocorrência que altera o registro); ordem do oficial de 11/09/2026",
         ["Data da assinatura:", DATA_ASSINATURA], [(CAMPOS_DO_TERMO[papel], "{data_assinatura}")])
      for papel in ("TERMO_AV_TD", "TERMO_AV_PJ")],
    # consertado no LD09: o cabeçalho do termo da averbação diz o número de
    # ordem dela («Averbação nº {numero_averbacao}»), como a certidão o imprime
    *[_r(papel, "o número de ordem da própria averbação",
         "LRP arts. 149 e 153; CN-MA art. 968", [f"Averbação nº {NUMERO_REGISTRO + 1}"],
         [(CAMPOS_DO_TERMO[papel], "{numero_averbacao}")])
      for papel in ("TERMO_AV_TD", "TERMO_AV_PJ")],

    # ---------------- A CERTIDÃO DE INTEIRO TEOR, POR TEXTO (.odt)
    *[req for serie, papel, nome_reg in (
        ("TD_B", "CERTIDAO_TEXTO_RTD", "Registro de Títulos e Documentos"),
        ("PJ_A", "CERTIDAO_TEXTO_RCPJ", "Registro de Pessoas Jurídicas"))
      for chave in (("RTD_CERTIDAO",) if serie == "TD_B" else ("RCPJ_CERTIDAO",))
      for req in (
        _r(papel, "a serventia que certifica", "CN-MA art. 977; LRP art. 19",
           [SERVENTIA], [("RCPJ_RTD_CERTIDAO_ODT", "sv.unit_name")]),
        _r(papel, "o oficial", "LRP art. 19 («autenticada pelo oficial»)",
           [f"{TITULO_DO_OFICIAL}: {OFICIAL}"], [("RCPJ_RTD_CERTIDAO_ODT", "sv.serventia_titular")]),
        _r(papel, "o CNS", "CN-MA art. 977", [f"CNS {CNS}"], [("RCPJ_RTD_CERTIDAO_ODT", "sv.ri_cns")]),
        _r(papel, "o número da certidão", "controle da casa (at_certidoes)",
           ["CERTIDÃO n. 12/2026"], [("RCPJ_RTD_CERTIDAO_ODT", "c.numero")]),
        _r(papel, "o livro, com o número do volume", "LRP art. 18",
           [f'no Livro "{serie[-1]}-{VOLUME}" de {nome_reg}'],
           [("RCPJ_CERTIDAO__onde", "{livro}"), ("RCPJ_CERTIDAO__onde", "{registro}")]),
        _r(papel, "a folha", "LRP art. 18", [f"fls. {FOLHA}"],
           [("RCPJ_CERTIDAO__onde_folha", "{folha}")]),
        _r(papel, "o número de ordem do ato", "LRP art. 18", [f"ATO n. {NUMERO_REGISTRO}"],
           [("RCPJ_CERTIDAO__onde_ato", "{numero}")]),
        _r(papel, "a data do registro", "LRP art. 18", ["datada de 05/10/2026"],
           [("RCPJ_CERTIDAO__onde_data", "{data}")]),
        _r(papel, "a natureza do registro", "CN-MA art. 420, I (RCPJ); LRP art. 19",
           [NATUREZA], [(chave, "{natureza}")]),
        _r(papel, "o inteiro teor do termo", "LRP arts. 19, § 1º, e 161; CN-MA art. 420, IV",
           ["COM O SEGUINTE TEOR", TEOR_DO_REGISTRO], [(chave, "{teor}")]),
        _r(papel, "as averbações, cada uma com o seu número", "LRP arts. 19 e 128",
           [f"AVERBAÇÃO n. {NUMERO_REGISTRO + 1}", "Aditivo de prorrogação do prazo"],
           [("RCPJ_CERTIDAO__averbacao", "{ordem}"), ("RCPJ_CERTIDAO__averbacao", "{teor}")]),
        _r(papel, "o local e a data da emissão", "LRP art. 19",
           [f"{CIDADE}-MA, {DIA_DO_ATO_EXTENSO}"], [("RCPJ_RTD_CERTIDAO_ODT", "hoje")]),
        _r(papel, "quem assina", "LRP art. 19", [OFICIAL, TITULO_DO_OFICIAL],
           [("RCPJ_RTD_CERTIDAO_ODT", "sv.serventia_titulo")]),
        _r(papel, "a impressão digital (autenticidade)", "LRP art. 19, § 5º (identificação segura)",
           ["Autenticidade:", "ab" * 32], [("RCPJ_RTD_CERTIDAO_ODT", "c.hash_certidao")]),
        _r(papel, "o selo da certidão", "CN-MA arts. 130 e 131", [SELO_DA_CERTIDAO]),
        _r(papel, "a consulta do selo (QR e endereço)", "CN-MA art. 132",
           [f"https://selo.tjma.jus.br/#/resumo/{SELO_DA_CERTIDAO}"]),
        _r(papel, "os emolumentos da certidão", "LRP art. 14, parágrafo único",
           ["Total R$ 53,58", "Emol R$ 47,84"]),
        # consertado no LD05 (21/10/2026): o selo de cada ato sai logo
        # abaixo dele, como o Livro 3 já fazia (`atrib_certidao.fecho_do_ato`)
        _r(papel, "o selo de cada ato reproduzido", "CN-MA art. 131; LRP art. 19, § 1º",
           [f"Selo de fiscalização do ato: {SELO_DO_ATO}"],
           [("RCPJ_CERTIDAO__selo_do_ato", "{selos}")]),
      )],
    # ---------------- A CERTIDÃO SÓ DAS AVERBAÇÕES
    _r("CERTIDAO_SO_AVERBACOES", "o objeto: as averbações, e não o registro",
       "LRP art. 19 (a certidão do que foi pedido)",
       ["ao qual constam as seguintes averbações", "Aditivo de prorrogação do prazo"],
       [("RCPJ_RTD_CERTIDAO_SO_AVERBACOES", "{teor}")]),
    _r("CERTIDAO_SO_AVERBACOES", "o registro a que se referem, com livro e número",
       "LRP art. 18", [f'no Livro "B-{VOLUME}"', f"ATO n. {NUMERO_REGISTRO}"],
       [("RCPJ_RTD_CERTIDAO_SO_AVERBACOES", "{onde}")]),
    # ---------------- A CERTIDÃO POR REPRODUÇÃO (PDF: capa e folhas)
    *[req for serie, papel, chave in (("TD_B", "CERTIDAO_PDF_RTD", "RTD_CERTIDAO_CAPA"),
                                      ("PJ_A", "CERTIDAO_PDF_RCPJ", "RCPJ_CERTIDAO_CAPA"))
      for req in (
        _r(papel, "a serventia e o CNS", "CN-MA art. 977", [SERVENTIA, f"CNS {CNS}"],
           [(chave, "{unit_short}"), (chave, "{cns}")]),
        _r(papel, "o oficial", "LRP art. 19", [f"Oficial: {OFICIAL}"], [(chave, "{oficial}")]),
        _r(papel, "o número e a data do registro", "LRP art. 18",
           [f"Nº {NUMERO_REGISTRO} de 05/10/2026"], [(chave, "{numero}"), (chave, "{data_registro}")]),
        _r(papel, "o protocolo e a data da apresentação", "LRP arts. 135 e 146",
           [f"protocolado sob nº {PROTOCOLO}", "apresentado em 02/10/2026"],
           [(chave, "{protocolo}"), (chave, "{data_apresentacao}")]),
        _r(papel, "o livro, com o volume", "LRP art. 18", [f"{serie[-1]}-{VOLUME}"],
           [(chave, "{livro}")]),
        _r(papel, "quantas páginas reproduz", "LRP art. 19, § 1º (reprografia)",
           ["contendo 1 (uma) página(s)"], [(chave, "{paginas}"), (chave, "{paginas_extenso}")]),
        _r(papel, "a denominação e a natureza", "CN-MA art. 420", [DENOMINACAO, NATUREZA],
           [(chave, "{denominacao}"), (chave, "{natureza}")]),
        _r(papel, "o local, a data e quem subscreve", "LRP art. 19",
           [f"{CIDADE}, {DIA_DO_ATO_EXTENSO}", f"Eu, {OFICIAL}, {FUNCAO}, o subscrevo e assino"],
           [(chave, "{data_extenso}"), (chave, "{full_name}")]),
        _r(papel, "o selo da certidão e a consulta", "CN-MA arts. 131 e 132",
           [SELO_DA_CERTIDAO, "Consulte em https://selo.tjma.jus.br"]),
        _r(papel, "os emolumentos da certidão", "LRP art. 14, parágrafo único",
           ["Total R$ 53,58", "Emol R$ 47,84"]),
      )],
    # ---------------- A NOTIFICAÇÃO (CN-MA arts. 986 a 993; LRP art. 160)
    *[req for papel, chave in (("NOTIFICACAO_POSITIVA", "RTD_CERTIDAO_NOTIFICACAO_POSITIVA"),
                               ("NOTIFICACAO_NEGATIVA", "RTD_CERTIDAO_NOTIFICACAO_NEGATIVA"))
      for req in (
        _r(papel, "a serventia e o oficial", "CN-MA art. 977",
           [SERVENTIA, f"{TITULO_DO_OFICIAL}: {OFICIAL}", f"CNS {CNS}"]),
        _r(papel, "o registro do documento notificado (número e livro)",
           "CN-MA art. 988, § 2º (não há certidão antes do registro); LRP art. 160, § 1º",
           ["Livro B do Registro de Títulos e Documentos"], [(chave, "{onde}")]),
        _r(papel, "o destinatário, com o documento", "CN-MA art. 986",
           ["CICLANO DESTINATÁRIO DE EXEMPLO", "CPF/CNPJ 00000000191"],
           [(chave, "{destinatario}"), (chave, "{documento}")]),
        _r(papel, "o endereço da diligência", "CN-MA arts. 986, § 3º, e 987, § 2º",
           ["Rua do Destinatário, 100, Centro"], [(chave, "{endereco}")]),
        _r(papel, "o local e a data da certidão", "LRP art. 19", [CIDADE, DIA_DO_ATO_EXTENSO],
           [(chave, "{cidade}"), (chave, "{data_extenso}")]),
        _r(papel, "quem expediu", "LRP art. 19 (autenticada pelo oficial)", [OFICIAL]),
        _r(papel, "o selo da certidão, com QR e consulta", "CN-MA arts. 130 a 132",
           [SELO_DA_CERTIDAO, "QR-DO-SELO",
            f"https://selo.tjma.jus.br/#/resumo/{SELO_DA_CERTIDAO}"]),
        _r(papel, "os emolumentos da certidão", "LRP art. 14, parágrafo único",
           ["Total R$ 53,58", "Emol R$ 47,84"]),
      )],
    _r("NOTIFICACAO_POSITIVA", "o dia e a hora em que se notificou", "CN-MA art. 986, § 4º",
       ["no dia {dia}", "às 10:00"], [("RTD_CERTIDAO_NOTIFICACAO_POSITIVA", "{data_da_notificacao}"),
                                      ("RTD_CERTIDAO_NOTIFICACAO_POSITIVA", "{hora_da_notificacao}")]),
    _r("NOTIFICACAO_POSITIVA", "como se efetivou (entrega, recusa ou procurador)",
       "CN-MA arts. 986 e 992", ["entregando-lhe uma via do documento registrado"],
       [("RTD_CERTIDAO_NOTIFICACAO_POSITIVA", "{como}"),
        ("RTD_CERTIDAO_NOTIFICACAO_POSITIVA__entregue", "entregando-lhe")]),
    _r("NOTIFICACAO_NEGATIVA", "as três diligências, em dias e horários alternados",
       "CN-MA art. 987, § 2º", ["nas 3 diligências", "1ª em {d0}, às 09:00",
                                "2ª em {d1}, às 14:00", "3ª em {d2}, às 19:00"],
       [("RTD_CERTIDAO_NOTIFICACAO_NEGATIVA", "{quantas}"),
        ("RTD_CERTIDAO_NOTIFICACAO_NEGATIVA", "{diligencias}"),
        ("RTD_CERTIDAO_NOTIFICACAO_NEGATIVA__ida", "{data}"),
        ("RTD_CERTIDAO_NOTIFICACAO_NEGATIVA__ida", "{hora}")]),
    _r("AVERBACAO_NOTIFICACAO_POSITIVA", "a averbação à margem: quem, quando e a certidão",
       "CN-MA arts. 986, § 2º, e 987, §§ 1º e 4º; LRP art. 160, § 1º",
       ["AVERBAÇÃO DE NOTIFICAÇÃO", "CICLANO DESTINATÁRIO DE EXEMPLO",
        "foi notificado(a) do documento deste registro no dia {dia}",
        "certidão de notificação nº 1/"],
       [("RTD_CERTIDAO_NOTIFICACAO_POSITIVA__averbacao", "{data_da_notificacao}"),
        ("RTD_CERTIDAO_NOTIFICACAO_POSITIVA__averbacao", "{certidao}")]),
    _r("AVERBACAO_NOTIFICACAO_NEGATIVA", "a averbação à margem: as diligências e a certidão",
       "CN-MA arts. 986, § 2º, e 987, §§ 1º, 2º e 4º",
       ["AVERBAÇÃO DE NOTIFICAÇÃO NEGATIVA", "realizadas 3 diligências",
        "Rua do Destinatário, 100", "certidão de notificação nº 1/"],
       [("RTD_CERTIDAO_NOTIFICACAO_NEGATIVA__averbacao", "{quantas}"),
        ("RTD_CERTIDAO_NOTIFICACAO_NEGATIVA__averbacao", "{certidao}")]),
    # ---------------- A AUTENTICAÇÃO DE LIVRO CONTÁBIL (CC art. 1.181; CN-MA art. 402, V)
    *[req for qual, chave in (("abertura", "RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA"),
                              ("encerramento", "RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO"),
                              ("certidao", "RCPJ_LIVRO_CONTABIL_CERTIDAO"))
      for papel in (f"LIVRO_CONTABIL_{qual.upper()}",)
      for req in (
        _r(papel, "o livro (tipo e número de ordem)", "CC art. 1.181; CN-MA art. 402, V",
           ["Livro Diário nº 2"], [(chave, "{tipo_livro}"), (chave, "{numero_livro}")]),
        _r(papel, "a pessoa jurídica e o CNPJ", "CC art. 1.181; CN-MA art. 402, V",
           [DENOMINACAO, "00.000.043/0001-77"], [(chave, "{pj_nome}"), (chave, "{pj_cnpj}")]),
        _r(papel, "as folhas e a numeração", "CC art. 1.181 (termos de abertura e encerramento)",
           ["100 folhas", "numeradas de 1 a 100"],
           [(chave, "{folhas}"), (chave, "{folha_de}"), (chave, "{folha_ate}")]),
        _r(papel, "o número do controle da autenticação", "CN-MA art. 402, V",
           ["nº 1/2026"], [(chave, "{numero}"), (chave, "{ano}")]),
        _r(papel, "o local, a data e quem assina", "CN-MA art. 972 (datado e assinado)",
           [f"{CIDADE}/MA, {{data}}", OFICIAL, FUNCAO],
           [(chave, "{cidade_uf}"), (chave, "{data_extenso}"), (chave, "{full_name}")]),
        _r(papel, "o selo, conferível no papel (número, QR e consulta)", "CN-MA arts. 130 a 132",
           [SELO_DO_ATO, "QR-DO-SELO", f"https://selo.tjma.jus.br/#/resumo/{SELO_DO_ATO}"]),
        _r(papel, "os emolumentos da autenticação", "LRP art. 14, parágrafo único",
           ["Total R$ 99,07", "Emol R$ 89,52"]),
      )],
    *[_r(f"LIVRO_CONTABIL_{qual.upper()}", "a serventia que autentica, com o CNS", "CN-MA art. 977",
         [f"de {SERVENTIA} — CNS {CNS}"], [(chave, "{unit_name}"), (chave, "{cns}")])
      for qual, chave in (("abertura", "RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA"),
                          ("certidao", "RCPJ_LIVRO_CONTABIL_CERTIDAO"))],
    _r("LIVRO_CONTABIL_ABERTURA", "a finalidade do livro", "CC art. 1.181",
       ["destina-se à escrituração"], [("RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA", "destina-se")]),
    _r("LIVRO_CONTABIL_CERTIDAO", "o selo citado no texto da certidão", "CN-MA art. 131",
       [f"Selo de fiscalização: {SELO_DO_ATO}"], [("RCPJ_LIVRO_CONTABIL_CERTIDAO", "{selo}")]),
    # ---------------- A NOTA DEVOLUTIVA (CN-MA arts. 41 e 975; LRP art. 156)
    *[_r("NOTA_DEVOLUTIVA", nome, artigo, esperado, [("RCPJ_RTD_NOTA", campo)])
      for nome, artigo, esperado, campo in (
          ("o papel timbrado da serventia", "CN-MA art. 41 («em papel timbrado do cartório»)",
           [SERVENTIA, f"CNS {CNS}"], "sv.unit_name"),
          ("o protocolo do título", "CN-MA art. 41; LRP art. 146", ["n. 987", "fl. 3"], "t.numero"),
          ("a data da apresentação", "LRP art. 146", ["Apresentado em 02/10/2026"], "apresentado_em"),
          ("o apresentante", "CN-MA art. 966, IV", [APRESENTANTE], "t.apresentante"),
          ("a natureza do título", "CN-MA art. 966, II", [NATUREZA], "t.natureza"),
          ("as exigências, claras e objetivas", "CN-MA arts. 41 e 975",
           ["EXIGÊNCIAS A CUMPRIR:", "Apresentar o original com firma reconhecida do credor."],
           "q.exigencias"),
          ("o fundamento legal", "CN-MA art. 41, § 1º", ["FUNDAMENTO:", "Lei 6.015/1973, art. 130, § 3º."],
           "q.fundamentacao"),
          ("o prazo e o que fazer", "CN-MA art. 41, § 1º (os procedimentos a adotar)",
           ["até 20/11/2026", "reapresentando o título"], "prazo_ate"),
          ("a data", "CN-MA art. 41", [f"{CIDADE}/MA, {DIA_DO_ATO_EXTENSO}"], "data_extenso"),
          ("a identificação e a assinatura de quem qualificou", "CN-MA art. 41",
           [OFICIAL, FUNCAO], "oficial"))],
    # ---------------- A ETIQUETA (a declaração no corpo do título — LRP art. 147)
    *[_r("ETIQUETA", nome, artigo, esperado, campos)
      for nome, artigo, esperado, campos in (
          ("a serventia", "CN-MA art. 977", [SERVENTIA], [("RCPJ_RTD_ETIQUETA", "e.cartorio")]),
          ("o ato, o livro, a folha e o número de ordem", "LRP art. 147; CN-MA art. 967, § 1º",
           ["Registro", f"n. {VOLUME}", f"fl. {FOLHA}", f"sob o n. {NUMERO_REGISTRO}"],
           [("RCPJ_RTD_ETIQUETA", "e.folha"), ("RCPJ_RTD_ETIQUETA", "e.numero")]),
          ("a data do lançamento", "LRP art. 147; CN-MA art. 967, § 1º", ["05/10/2026"],
           [("RCPJ_RTD_ETIQUETA", "e.data")]),
          ("o protocolo", "CN-MA art. 966, § 1º", [f"protocolo n. {PROTOCOLO}"],
           [("RCPJ_RTD_ETIQUETA", "e.protocolo")]),
          ("o selo, com QR e consulta", "CN-MA arts. 130 a 132",
           [SELO_DO_ATO, "QR-DO-SELO", "selo.tjma.jus.br"], [("RCPJ_RTD_ETIQUETA", "e.selo")]),
          ("os emolumentos", "LRP art. 14, parágrafo único", ["Total R$ 91,61", "Emol R$ 81,80"],
           [("RCPJ_RTD_ETIQUETA", "e.valores")]),
          ("quem rubrica, com a função", "LRP art. 147 («rubricando o oficial»)",
           [OFICIAL, FUNCAO], [("RCPJ_RTD_ETIQUETA", "e.oficial")]))],
]

# ---------------- O TERMO DO CANCELAMENTO (LD05, 21/10/2026)
#
# O cancelamento ganhou termo próprio (RTD_TEOR_CANCELAMENTO e
# RCPJ_TEOR_CANCELAMENTO). LRP art. 165 e CN-MA art. 994, § 1º: o oficial
# certifica o cancelamento e a causa dele, mencionando o documento que o
# autorizou, datando e assinando. Bloco à parte da lista de cima, para o lote
# que mexe nas marcas dela não conflitar com este.
MOTIVO_DO_CANCELAMENTO = "Quitação do credor de exemplo, com firma reconhecida."
REQUISITOS += [
    req for papel, chave, i in (("TERMO_CANC_TD", "RTD_TEOR_CANCELAMENTO", 0),
                                ("TERMO_CANC_PJ", "RCPJ_TEOR_CANCELAMENTO", 1))
    for req in (
        _r(papel, "a serventia, no alto da folha", FONTES["serventia"][i],
           [SERVENTIA], [(chave, "{unit_short}")]),
        _r(papel, "o CNS da serventia", "CN-MA art. 977 (identificação da serventia)",
           [f"CNS {CNS}"], [(chave, "{cns}")]),
        _r(papel, "o registro cancelado, com o número",
           "LRP art. 165; CN-MA art. 994, § 1º",
           [f"CANCELADO o Registro nº {NUMERO_REGISTRO}"],
           [(chave, "CANCELADO"), (chave, "{numero}")]),
        _r(papel, "a causa do cancelamento e o documento que o autorizou",
           "LRP art. 165 («a razão dele, mencionando-se o documento que o "
           "autorizou»); CN-MA art. 994, § 1º",
           ["documento que o autorizou", MOTIVO_DO_CANCELAMENTO], [(chave, "{motivo}")]),
        _r(papel, "quem subscreve e assina, com a função",
           "LRP art. 165 («assinando»); CN-MA art. 994, § 1º",
           [f"Eu, {OFICIAL}, {FUNCAO}, o subscrevo e assino"],
           [(chave, "{full_name}"), (chave, "{funcao}")]),
        _r(papel, "o local e a data", "LRP art. 165 («datando»); CN-MA art. 994, § 1º",
           [f"{CIDADE}/MA, {DIA_DO_ATO_EXTENSO}"],
           [(chave, "{cidade}"), (chave, "{data_extenso}")]),
        _r(papel, "o selo de fiscalização, no corpo do ato", "CN-MA arts. 130 e 131",
           [SELO_DO_ATO]),
    )]


# ---------------- A CERTIDÃO NEGATIVA (LD05, 21/10/2026)
#
# Serviços 314 e 315: a pesquisa pelo nome nos livros do RTD ou do RCPJ (LRP
# arts. 16, 17 e 19; CN-MA art. 963, § 3º), no papel por texto da casa.
PESQUISADO = "BELTRANO PESQUISADO DE EXEMPLO"
REQUISITOS += [
    req for papel, sigla, nome_reg in (
        ("CERTIDAO_NEGATIVA_RTD", "RTD", "Registro de Títulos e Documentos"),
        ("CERTIDAO_NEGATIVA_RCPJ", "RCPJ", "Registro de Pessoas Jurídicas"))
    for req in (
        _r(papel, "o nome pesquisado", "CN-MA art. 963, § 3º (pelo nome das partes)",
           [PESQUISADO], [("RCPJ_RTD_CERTIDAO_NEGATIVA", "{nome}")]),
        _r(papel, "o CPF ou CNPJ pesquisado", "CN-MA art. 963, IV e § 3º (o documento "
           "de identificação no indicador)", ["000.000.001-91"],
           [("RCPJ_RTD_CERTIDAO_NEGATIVA", "{documento}")]),
        _r(papel, "os livros pesquisados", "LRP art. 19 (a certidão do que foi pedido)",
           [nome_reg], [("RCPJ_RTD_CERTIDAO_NEGATIVA", "{registro}")]),
        _r(papel, "que nada consta, nem registro nem averbação", "LRP arts. 16 e 17",
           ["NÃO CONSTA registro nem averbação"],
           [("RCPJ_RTD_CERTIDAO_NEGATIVA", "NÃO CONSTA")]),
        _r(papel, "a serventia que certifica", "CN-MA art. 977; LRP art. 19",
           [SERVENTIA, f"CNS {CNS}"], [("RCPJ_RTD_CERTIDAO_ODT", "sv.unit_name")]),
        _r(papel, "o número da certidão", "controle da casa (at_certidoes)",
           ["CERTIDÃO n. 12/2026"], [("RCPJ_RTD_CERTIDAO_ODT", "c.numero")]),
        _r(papel, "o local e a data da emissão", "LRP art. 19",
           [f"{CIDADE}-MA, {DIA_DO_ATO_EXTENSO}"], [("RCPJ_RTD_CERTIDAO_ODT", "hoje")]),
        _r(papel, "quem assina", "LRP art. 19", [OFICIAL, TITULO_DO_OFICIAL]),
        _r(papel, "o selo da certidão, com os emolumentos", "CN-MA arts. 130 e 131; "
           "LRP art. 14, parágrafo único", [SELO_DA_CERTIDAO, "Total R$ 53,58"]),
    )]


# ---------------- A CERTIDÃO DO RCPJ EM BREVE RELATO (LD05, 21/10/2026)
#
# CN-MA art. 420, II: a situação atual da pessoa jurídica, pelos dados que quem
# leu o estatuto gravou na ficha do registro.
SEDE = "Rua de Exemplo, 100, Centro, Cidade Exemplo/MA"
OBJETO = "Promover atividades culturais de exemplo."
CAPITAL = "não tem (associação civil)"
DIRETORIA = "FULANA DE EXEMPLO (presidente)"
_BR = "CN-MA art. 420, II"
REQUISITOS += [
    _r("CERTIDAO_BREVE_RELATO", elemento, _BR, esperado,
       [("RCPJ_CERTIDAO_BREVE_RELATO", campo)])
    for elemento, esperado, campo in (
        ("a denominação", [f"Denominação: {DENOMINACAO}"], "{denominacao}"),
        ("o endereço da sede", [f"Endereço da sede: {SEDE}"], "{sede}"),
        ("o número de inscrição no CNPJ", ["CNPJ: 00.000.043/0001-77"], "{cnpj}"),
        ("o objeto social", [f"Objeto social: {OBJETO}"], "{objeto}"),
        ("o capital social", [f"Capital social: {CAPITAL}"], "{capital}"),
        ("os sócios e as participações (com fins lucrativos)", [], "{socios}"),
        ("os membros da diretoria (sem fins lucrativos)",
         [f"Membros da diretoria: {DIRETORIA}"], "{diretoria}"),
        ("a data do último ato registrado ou averbado",
         ["último ato registrado ou averbado nesta Serventia: 06/10/2026"],
         "{ultimo_ato}"),
        ("o registro da pessoa jurídica, com livro e número",
         [f'no Livro "A-{VOLUME}"', f"ATO n. {NUMERO_REGISTRO}"], "{onde}"),
    )] + [
    _r("CERTIDAO_BREVE_RELATO", "a serventia que certifica", "CN-MA art. 977; LRP art. 19",
       [SERVENTIA, f"CNS {CNS}"], [("RCPJ_RTD_CERTIDAO_ODT", "sv.unit_name")]),
    _r("CERTIDAO_BREVE_RELATO", "o local e a data da emissão", "LRP art. 19",
       [f"{CIDADE}-MA, {DIA_DO_ATO_EXTENSO}"], [("RCPJ_RTD_CERTIDAO_ODT", "hoje")]),
    _r("CERTIDAO_BREVE_RELATO", "quem assina", "LRP art. 19", [OFICIAL, TITULO_DO_OFICIAL]),
    _r("CERTIDAO_BREVE_RELATO", "o selo da certidão", "CN-MA arts. 130 e 131",
       [SELO_DA_CERTIDAO]),
]


def _breve_relato() -> str:
    """A certidão em breve relato (.odt), como a rota a imprime."""
    import atrib_certidao as CE
    import modelos_da_casa as MODELOS
    import ri_odt as RODT
    import serventia
    dados = _dados_do_registro("PJ_A")
    dados["registro"].update(
        requerente_documento="00000043000177", pj_sede=SEDE, pj_objeto=OBJETO,
        pj_capital=CAPITAL, pj_diretoria=DIRETORIA, pj_socios=None,
        pj_dados_em="2026-10-07T10:00:00")
    certidao = {"numero": 12, "ano": 2026, "teor": CE.teor_do_breve_relato(dados),
                "cancelada": 0, "motivo_cancelamento": None,
                "emitida_em": "2026-10-07T10:00:00", "hash_certidao": "ab" * 32}
    papel = CE._montar_papel_por_texto(
        MODELOS.padrao_de(CE.CHAVE_PAPEL_POR_TEXTO), certidao,
        sv=serventia.dados(SV), hoje=DIA_DO_ATO_EXTENSO)
    carimbo, _ = RODT.carimbo_da_certidao_odf(
        _texto_do_selo(SELO_DA_CERTIDAO, "15.10.1", "53,58", "47,84"))
    return _sem_tags(papel + " " + carimbo)


def _certidao_negativa(sigla: str) -> str:
    """A certidão negativa por texto (.odt), como a rota a imprime."""
    import atrib_certidao as CE
    import modelos_da_casa as MODELOS
    import ri_odt as RODT
    import serventia
    teor = CE.teor_da_negativa(atribuicao=sigla, nome=PESQUISADO,
                               documento="00000000191")
    certidao = {"numero": 12, "ano": 2026, "teor": teor, "cancelada": 0,
                "motivo_cancelamento": None, "emitida_em": "2026-10-05T10:00:00",
                "hash_certidao": "ab" * 32, "registro_id": 0}
    papel = CE._montar_papel_por_texto(
        MODELOS.padrao_de(CE.CHAVE_PAPEL_POR_TEXTO), certidao,
        sv=serventia.dados(SV), hoje=DIA_DO_ATO_EXTENSO)
    carimbo, _ = RODT.carimbo_da_certidao_odf(
        _texto_do_selo(SELO_DA_CERTIDAO, "15.10.1", "53,58", "47,84"))
    return _sem_tags(papel + " " + carimbo)


def _montar(papel: str, casa, monkeypatch) -> tuple[str, dict]:
    """O papel montado, e os valores que dependem do dia em que o teste roda."""
    if papel == "CERTIDAO_BREVE_RELATO":
        return _breve_relato(), {}
    if papel.startswith("CERTIDAO_NEGATIVA_"):
        return _certidao_negativa(papel.rsplit("_", 1)[-1]), {}
    if papel.startswith("TERMO_CANC_"):
        return _termo(monkeypatch, serie="TD_B" if papel.endswith("TD") else "PJ_A",
                      tipo="CANCELAMENTO", motivo=MOTIVO_DO_CANCELAMENTO), {}
    if papel.startswith("TERMO_"):
        serie, tipo = _serie_e_tipo_do_termo(papel)
        return _termo(monkeypatch, serie=serie, tipo=tipo), {}
    if papel.startswith("CERTIDAO_TEXTO_"):
        return _certidao_por_texto(serie="TD_B" if papel.endswith("RTD") else "PJ_A"), {}
    if papel == "CERTIDAO_SO_AVERBACOES":
        return _certidao_por_texto(serie="TD_B", ato_ids=[12]), {}
    if papel.startswith("CERTIDAO_PDF_"):
        return _certidao_por_reproducao(
            monkeypatch, serie="TD_B" if papel.endswith("RTD") else "PJ_A"), {}
    if papel == "NOTA_DEVOLUTIVA":
        return _nota_devolutiva(), {}
    if papel == "ETIQUETA":
        return _etiqueta(), {}
    if "NOTIFICACAO" in papel:
        feito = _notificacao(casa, "POSITIVA" if papel.endswith("POSITIVA") else "NEGATIVA")
        br = [f"{d[8:10]}/{d[5:7]}/{d[:4]}" for d in feito["datas"]]
        texto = feito["averbacao"] if papel.startswith("AVERBACAO") else feito["certidao"]
        return texto, {"dia": br[-1], **{f"d{i}": x for i, x in enumerate(br)}}
    if papel.startswith("LIVRO_CONTABIL_"):
        qual = papel.split("_")[-1].lower()
        # os termos se congelam na autenticação; a certidão se monta ao
        # imprimir, e é datada do dia em que sai
        quando = (DIA_DO_ATO if qual != "certidao" else date.today())
        return _livro_contabil(casa, qual), {
            "data": f"{quando.day} de {MESES[quando.month - 1]} de {quando.year}"}
    raise AssertionError(papel)


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("oficial", OFICIAL, SENHA, "ADMIN")
    with db.transaction() as con:          # quem assina, com a função (Lei 8.935, art. 20)
        banco(con).escrever("UPDATE users SET funcao=%s WHERE username='oficial'",
                            (FUNCAO,))
    db.set_settings(SV)
    return cg_casa


def _param(req: Req):
    marcas = ([pytest.mark.xfail(strict=True, reason=f"DEFEITO do modelo: {req.defeito} "
                                                    f"({req.artigo})")]
              if req.defeito else [])
    return pytest.param(req, id=f"{req.papel}-{req.elemento}", marks=marcas)


@pytest.mark.parametrize("req", [_param(r) for r in REQUISITOS])
def test_o_papel_traz_o_elemento_que_a_norma_exige_e_o_modelo_tem_o_campo(
        req, casa, monkeypatch):
    import modelos_da_casa as MODELOS
    texto, dia = _montar(req.papel, casa, monkeypatch)
    for pedaco in req.esperado:
        pedaco = _normal(pedaco.format(**dia) if dia else pedaco)
        assert pedaco in texto, f"«{pedaco}» não está no papel {req.papel} ({req.artigo})"
    for chave, campo in req.campos:
        assert campo in MODELOS.padrao_de(chave), (
            f"o modelo padrão {chave} não tem «{campo}» ({req.artigo})")
    if req.fora_do_cabecalho:
        linhas = _cabecalho_do_termo(req.papel)
        # o cabeçalho medido é o que vai ao papel, linha por linha
        assert linhas and all(_normal(ln) in texto for ln in linhas), (linhas, texto)
        junto = " ".join(linhas)
        for proibido in req.fora_do_cabecalho:
            assert not re.search(proibido, junto, re.IGNORECASE), (
                f"o alto do termo {req.papel} cita /{proibido}/: {junto!r} — o oficial "
                "decidiu em 21/10/2026 que o livro e a folha não vão ali")
    for chave, campo in req.campos_fora:
        assert campo not in MODELOS.padrao_de(chave), (
            f"o modelo padrão {chave} voltou a ter «{campo}» (decisão de 21/10/2026)")


@pytest.mark.parametrize("chave", sorted(set(CAMPOS_DO_TERMO.values())))
def test_a_casa_nao_consegue_por_livro_e_folha_no_alto_do_termo(chave):
    """A OUTRA METADE DA DECISÃO DE 21/10/2026 (pergunta 28, LH13). A letra b
    pedia «Livro B-1 — fl. 17» no alto de cada folha, com os claros `{livro}` e
    `{folha}`, e tirava a recusa. O oficial ficou com a letra a: «28 tem que
    ser lida em conjunto com outras normas, inclusive estaduais que permitem
    que esses livros sejam digitais, nao fazendo sentido colocar livro e
    folha». A recusa fica: o ajuste do papel na tela de Modelos que puser o
    livro ou a folha no ===CABECALHO=== não grava, e o termo não imprime."""
    import modelos_da_casa as MODELOS
    import rg_teor_rtdpj as RGTEOR
    padrao = MODELOS.padrao_de(chave)
    assert RGTEOR.conferir_teor(padrao) == ""
    com_livro = padrao.replace("===CABECALHO===\n", "===CABECALHO===\nLivro B-1 — fl. 17\n", 1)
    assert com_livro != padrao
    assert "livro/folha" in RGTEOR.conferir_teor(com_livro)


def test_a_matriz_cobre_todos_os_papeis_do_rtd_e_do_rcpj_no_catalogo():
    """Todo papel do RTD/RCPJ no catálogo é conferido por alguma linha da
    matriz — ou está aqui dito por que não (peça de outro papel, moldura)."""
    import modelos_da_casa as MODELOS
    conferidos = {chave for r in REQUISITOS for chave, _ in r.campos}
    fora = {
        # pecas e molduras: conferidas pelo papel que as usa
        "RCPJ_CERTIDAO__cancelado", "RCPJ_CERTIDAO__registro",
        "RCPJ_CERTIDAO__registro_rcpj", "RCPJ_CERTIDAO__registro_rtd",
        "RCPJ_CERTIDAO_FAIXA", "RTD_CERTIDAO_FAIXA",
        "RTD_CERTIDAO_NOTIFICACAO_POSITIVA__procurador",
        "RTD_CERTIDAO_NOTIFICACAO_POSITIVA__recusou",
        # a etiqueta dos selos que vieram de fora (não é ato desta casa)
        "RCPJ_RTD_ETIQUETA_SELO_EXTERNO", "RCPJ_RTD_ETIQUETA_SELO_EXTERNO__manual",
        "RCPJ_RTD_ETIQUETA_SELO_EXTERNO__razao"}
    do_rtd_rcpj = {c["chave"] for c in MODELOS.CATALOGO
                   if c["chave"].startswith(("RCPJ_", "RTD_"))}
    assert do_rtd_rcpj, "o catálogo não tem os papéis do RTD/RCPJ"
    assert do_rtd_rcpj - conferidos - fora == set()
