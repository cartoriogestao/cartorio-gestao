"""Prévia segura dos modelos, sem gravar e sem precisar escolher um ato real.

O editor manda o rascunho das três partes. Este módulo usa o mesmo formato do
papel (Jinja ou chaves simples), preenche um caso hipotético legível e devolve
HTML para um iframe isolado. A conferência definitiva continua acontecendo ao
gravar; a prévia existe para a pessoa enxergar a forma enquanto escreve.
"""
from __future__ import annotations

import html
import re
from typing import Any

from jinja2 import ChainableUndefined
from jinja2.sandbox import SandboxedEnvironment

import modelos_da_casa as CASA


class Claro(ChainableUndefined):
    """Um dado ausente aparece na folha, em vez de desaparecer em silêncio."""

    def __str__(self) -> str:
        nome = self._undefined_name or "campo"
        return f"[{nome}]"

    def __html__(self) -> str:
        return html.escape(str(self))

    def __bool__(self) -> bool:
        return True

    def __iter__(self):
        return iter(())


class Dados(dict):
    """Dicionário que também aceita ``a.numero`` nos modelos."""

    __getattr__ = dict.get


def _d(**itens: Any) -> Dados:
    return Dados(itens)


CONTEXTO = {
    "hoje": "8 de setembro de 2026",
    "agora": "2026-09-08T10:30:00",
    "data_abertura_br": "8 de setembro de 2026",
    "uf_extenso": "Maranhão",
    "protocolo_atual": "12.345",
    "sv": _d(nome="SERVENTIA EXTRAJUDICIAL DE EXEMPLO",
             unit_name="SERVENTIA EXTRAJUDICIAL DE EXEMPLO",
             cns="000000", cidade="Cidade Exemplo", uf="UF",
             endereco="Rua Principal, nº 100, Centro",
             telefone="(99) 3531-0000", registrador="FULANO DE TAL",
             titulo="Tabelião e Oficial"),
    "serventia": _d(nome="SERVENTIA EXTRAJUDICIAL DE EXEMPLO",
                    cns="000000", cidade="Cidade Exemplo", uf="UF",
                    endereco="Rua Principal, nº 100, Centro",
                    registrador="FULANO DE TAL"),
    "a": _d(numero=123, livro_numero=15, livro_folha=42,
            data_ato="08/09/2026", tipo="Compra e venda",
            teor="Ato hipotético para conferência visual do modelo."),
    "m": _d(numero=12345, logradouro="Imóvel urbano situado na Rua das Flores",
            cidade="Cidade Exemplo", uf="UF", proprietario="MARIA DE EXEMPLO"),
    "protocolo": _d(numero=12345, apresentante="JOÃO DE EXEMPLO",
                    natureza="ESCRITURA PÚBLICA DE COMPRA E VENDA",
                    data="08/09/2026"),
    "p": _d(numero=12345, apresentante="JOÃO DE EXEMPLO",
            natureza_titulo="ESCRITURA PÚBLICA DE COMPRA E VENDA",
            documento_descricao="Traslado da escritura", objeto="Imóvel urbano",
            matricula_numero="12.345", hora="10:30", livro_destino="2",
            selo_prenotacao="SELO000000EXEMPLO01"),
    "documento": "000.000.000-00", "telefone": "(99) 99999-0000",
    "email": "exemplo@exemplo.com", "data": "08/09/2026",
    "limite": "8 de outubro de 2026", "faltam": 20, "prazo": 20,
    "hoje_extenso": "8 de setembro de 2026", "emitido_por": "BEATRIZ DE EXEMPLO",
    "funcao": "Tabeliã Registradora Substituta",
    "nota": _d(numero=27, exigencias="Apresentar documento atualizado."),
    "partes": [_d(nome="JOÃO DE EXEMPLO", documento="000.000.000-00"),
               _d(nome="MARIA DE EXEMPLO", documento="111.111.111-11")],
    "itens": [_d(descricao="Emolumentos", valor="R$ 100,00")],
    "selos": [_d(codigo="SELO000000EXEMPLO01", texto="Consulte o selo no TJMA")],
}


AMOSTRAS_CHAVES = Dados({
    "cns": "000000", "atribuicao": "Registro Civil das Pessoas Jurídicas",
    "unit_short": "OFÍCIO ÚNICO DE EXEMPLO / UF",
    "tipo_ato": "AVERBACAO", "verbo": "AVERBADO",
    "full_name": "FULANO DE TAL",
    "data_extenso": "11 de setembro de 2026",
    "nome": "MARIA DE EXEMPLO", "matricula": "000000 01 55 2026 1 00001 123 0000123 45",
    "numero": "123", "livro": "A-15", "folha": "42", "termo": "123",
    "data": "8 de setembro de 2026", "cidade": "Cidade Exemplo",
    "uf": "MA", "serventia": "SERVENTIA EXTRAJUDICIAL DE EXEMPLO",
    "oficial": "FULANO DE TAL", "declarante": "JOÃO DE EXEMPLO",
    "registrado": "MARIA DE EXEMPLO", "contraente": "JOÃO DE EXEMPLO",
    "contraentes": "JOÃO DE EXEMPLO e MARIA DE EXEMPLO",
    "falecido": "JOSÉ DE EXEMPLO", "selo": "SELO000000EXEMPLO01",
    "base": "Aos oito dias do mês de setembro de dois mil e vinte e seis",
    "posteriori": "Nada mais.", "edital": "A intimação ocorreu regularmente.",
    "copia": "Fica arquivada cópia do título.",
    "intimacao": "Certifico que o devedor foi intimado.",
    "praca": "Cidade Exemplo - UF", "motivo": "falta de pagamento",
    "titulo": "TERMO HIPOTÉTICO", "tipo": "REGISTRO",
    "teor": "Texto hipotético do ato para conferência visual.",
    "onde": 'no Livro "A-5" de Registro de Pessoas Jurídicas, fls. 42, ATO n. 123',
    "natureza": ", ATA DE CONSTITUIÇÃO",
    "pedido": "a requerimento verbal de parte interessada",
    "desde": "Setembro de 2021", "identificacao": "MARIA DE EXEMPLO, CPF: 000.000.000-00",
    "periodo_anos": "5", "cabeca": "CERTIFICO que foram encontrados registros.",
    "corpo": "1) Título n. 123; protestado em 08/09/2026; Livro 10, fl. 42.",
    "fecho": "CERTIFICO ainda que consta a baixa e o cancelamento.",
})


class ChavesComAmostra(Dados):
    def __missing__(self, chave: str) -> str:
        return f"[{chave.replace('_', ' ')}]"


def montar(partes: list[str]) -> str:
    presentes = [str(x or "") for x in partes]
    primeiro = presentes[0] if presentes else ""
    depois = [x.strip() for x in presentes[1:] if x.strip()]
    return primeiro if not depois else primeiro.rstrip() + "\n\n" + "\n\n".join(depois)


def renderizar(chave: str, partes: list[str]) -> tuple[str, str]:
    """Devolve ``(documento, erro)`` para o rascunho informado."""
    fonte = montar(partes)
    try:
        if CASA.formato_de(chave) == CASA.CHAVES:
            alvo = (chave or "").strip().upper()
            if alvo in ("RI_LIVRO3_FICHA", "RI_LIVRO3_CERTIDAO"):
                import livro3_modelos_ensaio as L3

                dados = L3.claros_de(alvo)
            else:
                dados = ChavesComAmostra(AMOSTRAS_CHAVES)
            documento = fonte.format_map(dados)
        else:
            env = SandboxedEnvironment(autoescape=False, undefined=Claro)
            documento = env.from_string(fonte).render(**CONTEXTO)
        documento = documento.replace("@@BRASAO@@", "")
        return documento, ""
    except Exception as erro:  # a mensagem é mostrada ao lado do editor
        return "", f"{type(erro).__name__}: {erro}"


def resposta_previa(con, ato: str, form) -> tuple[dict, int]:
    """Monta o JSON da prévia ao editar — mesma regra nos seis submódulos e em `/modelos`."""
    import modelos_elementos as ELEM

    alvo = (ato or "").strip().upper()
    if alvo not in ELEM.CASA.POR_CHAVE:
        return {"ok": False, "erro": "Modelo desconhecido."}, 400
    partes = ELEM.partes_do_documento(con, alvo)
    for indice, parte in enumerate(ELEM.PARTES):
        campo = f"parte_{parte.lower()}"
        if campo in form:
            partes[indice] = form.get(campo) or ""
    documento, erro = renderizar(alvo, partes)
    if erro:
        return {"ok": False, "erro": erro}, 200
    titulo = ELEM.CASA.POR_CHAVE[alvo]["nome"]
    return {"ok": True, "html": pagina(documento, titulo=titulo)}, 200


def pagina(documento: str, *, titulo: str) -> str:
    """Coloca a saída dentro de uma folha previsível e própria para iframe."""
    # Texto puro também precisa parecer documento; modelos HTML/ODT já trazem
    # seus próprios parágrafos e tabelas.
    tem_marcacao = bool(re.search(r"</?(?:p|table|div|h[1-6]|br|ul|ol)\b", documento,
                                  flags=re.I))
    miolo = documento if tem_marcacao else "".join(
        f"<p>{html.escape(linha) or '&nbsp;'}</p>" for linha in documento.splitlines())
    return f"""<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">
<style>
*{{box-sizing:border-box}} body{{margin:0;background:#dfe3e8;color:#181818;
font:14px Georgia,'Times New Roman',serif}} .folha{{width:210mm;min-height:297mm;
margin:18px auto;padding:18mm 17mm;background:white;box-shadow:0 10px 30px #0002}}
p{{margin:0 0 7px;text-align:justify;line-height:1.45}} table{{width:100%;border-collapse:collapse}}
td,th{{padding:4px}} img{{max-width:100%}} .rotulo{{font:11px -apple-system,BlinkMacSystemFont,
'Segoe UI',sans-serif;color:#68707b;margin-bottom:12px;border-bottom:1px solid #ddd;padding-bottom:7px}}
@media(max-width:850px){{.folha{{width:calc(100% - 20px);margin:10px;padding:24px;min-height:calc(100vh - 20px)}}}}
</style></head><body><article class=\"folha\"><div class=\"rotulo\">Prévia hipotética — {html.escape(titulo)}</div>{miolo}</article></body></html>"""
