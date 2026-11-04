"""API de leitura de boleto/Pix em PDF ou imagem, inteiramente na serventia."""
from __future__ import annotations

import hashlib
import math
import re
from datetime import date
from io import BytesIO

import despesas as DP
import despesas_fluxo as DF

MAX_BYTES = 15 * 1024 * 1024
MAX_PAGINAS = 12
MAX_PIXELS = 12_000_000


def _textos(texto: str) -> list[str]:
    texto = texto[:120_000]
    saida = re.findall(r'000201[^\r\n]{26,4090}?6304[0-9a-fA-F]{4}', texto)
    saida += re.findall(r'(?<!\d)(?:\d{48}|\d{47}|\d{44})(?!\d)', texto)
    saida += re.findall(r'\d{5}\.?\d{5}\s+\d{5}\.?\d{6}\s+\d{5}\.?\d{6}\s+\d\s+\d{14}', texto)
    for linha in texto.splitlines():
        if re.fullmatch(r'[\d.\s-]+', linha) and len(DP.digitos(linha)) in (44,47,48):
            saida.append(linha)
    return saida


def _codigos_da_imagem(imagem) -> list[str]:
    try:
        import zxingcpp
    except ImportError as erro:
        raise DP.DespesaError('O leitor de QR e barras nao esta instalado no servidor. '
                              'Instale a dependencia zxing-cpp ou cole a linha digitavel.') from erro
    return [r.text for r in zxingcpp.read_barcodes(imagem) if r.valid]


def ler(conteudo: bytes, *, hoje: date) -> dict:
    """Somente extrai e valida; nao grava despesa, nao consulta nem paga no banco."""
    if not conteudo or len(conteudo) > MAX_BYTES:
        raise DP.DespesaError('Escolha um PDF ou imagem de ate 15 MB, com conteudo.')
    encontrados, vistos = [], set()
    def juntar(codigo: str, pagina: int, origem: str):
        codigo = str(codigo or '').strip()
        if not codigo.startswith('000201') and len(DP.digitos(codigo)) not in (44,47,48):
            return  # QR de site, telefone ou outros dados nunca vira destino de pagamento.
        try:
            dados = DF.ler_codigo(codigo, hoje=hoje)
            chave = (DP.ler_codigo_de_barras(codigo)['barras']
                     if dados['forma'] in (DP.BOLETO,DP.ARRECADACAO) else codigo)
        except (DP.DespesaError, ValueError, OverflowError):
            return
        if chave in vistos: return
        vistos.add(chave)
        encontrados.append({**dados,'codigo':codigo,'pagina':pagina,'origem':origem})

    if conteudo.startswith(b'%PDF'):
        import fitz
        try:
            doc = fitz.open(stream=conteudo,filetype='pdf')
        except (RuntimeError, ValueError) as erro:
            raise DP.DespesaError('O PDF nao abre. Salve novamente o documento.') from erro
        with doc:
            if doc.needs_pass:
                raise DP.DespesaError('O PDF esta protegido por senha. Anexe uma copia liberada para leitura.')
            if not 0 < doc.page_count <= MAX_PAGINAS:
                raise DP.DespesaError('A leitura aceita ate 12 paginas. Separe somente a fatura ou guia.')
            for numero,pagina in enumerate(doc,1):
                for texto in _textos(pagina.get_text()): juntar(texto,numero,'texto do PDF')
                from PIL import Image
                largura,altura = pagina.rect.width,pagina.rect.height
                if not math.isfinite(largura*altura) or largura<=0 or altura<=0:
                    raise DP.DespesaError('O PDF tem uma pagina com dimensoes invalidas.')
                escala = min(3.0, math.sqrt(MAX_PIXELS/(largura*altura)))
                pix = pagina.get_pixmap(matrix=fitz.Matrix(escala,escala),colorspace=fitz.csGRAY,alpha=False)
                imagem=Image.frombytes('L',(pix.width,pix.height),pix.samples)
                for codigo in _codigos_da_imagem(imagem): juntar(codigo,numero,'QR/codigo de barras')
    else:
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(BytesIO(conteudo)) as original:
                if original.format not in ('PNG','JPEG'):
                    raise DP.DespesaError('Use PDF, PNG ou JPG para a leitura.')
                if original.width * original.height > MAX_PIXELS:
                    raise DP.DespesaError('A imagem passa de 12 megapixels. Reduza a resolucao ou use PDF.')
                imagem=original.convert('L')
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as erro:
            raise DP.DespesaError('A imagem nao abre ou tem tamanho excessivo. Use PDF, PNG ou JPG.') from erro
        for codigo in _codigos_da_imagem(imagem): juntar(codigo,1,'QR/codigo de barras')
    return {'opcoes':encontrados,'sha256':hashlib.sha256(conteudo).hexdigest(),
            'aviso': ('Escolha o codigo e confira com a fatura. Ler nao cadastra nem envia pagamento.'
                      if encontrados else 'Nenhum Pix ou boleto valido foi encontrado. Tente um arquivo mais nitido ou cole o codigo.')}
