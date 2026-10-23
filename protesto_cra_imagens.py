"""Imagens t51 da CRA e cópia local da remessa; nenhuma chamada de rede.

Veio no hotfix 3.6.293.3 da produção (19/10/2026, pedido do oficial: as
imagens dos títulos junto à remessa, e uma cópia local que evite pedir de novo
à CRA). Na migração (LH01, 21/10/2026) só o SQL de `anexar` mudou: ele roda
pelo `bd_nativo`, na MESMA conexão — e portanto na mesma transação — do
recebimento, para que falhar ao gravar uma imagem desfaça os títulos também.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from io import BytesIO
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

from bd_nativo import banco

LIMITE_ARQUIVO = 25 * 1024 * 1024
LIMITE_TOTAL = 100 * 1024 * 1024
LIMITE_XML = 64 * 1024 * 1024
EXTENSOES = {'.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.p7s'}


class ImagemCraError(ValueError):
    """Erro pronto para a conferência; a cópia da remessa fica preservada."""


def ler_zip(valor: str) -> tuple[dict, ...]:
    """Lê t51 ZIP/base64, limitado em quantidade e tamanho descompactado."""
    valor = ''.join(valor.split())
    if len(valor) <= 19:  # branco/indicador do layout TXT, sem imagem embutida
        return ()
    try:
        bruto = base64.b64decode(valor, validate=True)
        with zipfile.ZipFile(BytesIO(bruto)) as pacote:
            infos = [i for i in pacote.infolist() if not i.is_dir()]
            if not infos or len(infos) > 100:
                raise ImagemCraError('O ZIP de um título deve conter de 1 a 100 arquivos.')
            if sum(i.file_size for i in infos) > LIMITE_TOTAL:
                raise ImagemCraError('As imagens descompactadas excedem 100 MB.')
            arquivos = []
            for info in infos:
                nome = info.filename.replace('\\', '/')
                partes = PurePosixPath(nome)
                if partes.is_absolute() or '..' in partes.parts or ':' in nome:
                    raise ImagemCraError('O ZIP de imagens contém caminho de arquivo inválido.')
                ext = partes.suffix.lower()
                if ext not in EXTENSOES:
                    raise ImagemCraError('Formato de imagem não aceito no ZIP: ' + ext)
                if info.flag_bits & 1 or info.file_size > LIMITE_ARQUIVO:
                    raise ImagemCraError('Imagem cifrada ou acima de 25 MB no ZIP da CRA.')
                with pacote.open(info) as file:
                    conteudo = file.read(LIMITE_ARQUIVO + 1)
                if not conteudo or len(conteudo) > LIMITE_ARQUIVO:
                    raise ImagemCraError('Imagem vazia ou acima de 25 MB no ZIP da CRA.')
                assinaturas = {'.pdf': (b'%PDF-',), '.png': (b'\x89PNG\r\n\x1a\n',),
                               '.jpg': (b'\xff\xd8\xff',), '.jpeg': (b'\xff\xd8\xff',),
                               '.tif': (b'II*\x00', b'MM\x00*'), '.tiff': (b'II*\x00', b'MM\x00*')}
                if ext in assinaturas and not conteudo.startswith(assinaturas[ext]):
                    raise ImagemCraError('O conteúdo da imagem não corresponde à extensão ' + ext + '.')
                arquivos.append({'nome': re.sub(r'[\x00-\x1f\x7f]', '_', partes.name)[:240], 'extensao': ext,
                                 'conteudo': conteudo, 'sha256': hashlib.sha256(conteudo).hexdigest()})
            return tuple(arquivos)
    except (binascii.Error, ValueError, OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as erro:
        if isinstance(erro, ImagemCraError):
            raise
        raise ImagemCraError('A imagem t51 não é um ZIP/base64 íntegro da CRA.') from erro


def _gravar(caminho: Path, conteudo: bytes) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if caminho.exists():
        if caminho.read_bytes() != conteudo:
            raise ImagemCraError('A cópia local não confere com seu conteúdo original.')
        return
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(dir=caminho.parent, prefix='.recebendo-', delete=False) as file:
            temporario = Path(file.name)
            file.write(conteudo)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporario, caminho)
    finally:
        if temporario is not None and temporario.exists():
            temporario.unlink()


def preparar_pasta(pasta) -> Path:
    """Confere permissão de gravar antes de solicitar o download à CRA."""
    raiz = Path(pasta) / 'Protesto' / 'RemessasCRA'
    try:
        raiz.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=raiz) as file:
            file.write(b'1')
            file.flush()
            os.fsync(file.fileno())
    except OSError as erro:
        raise ImagemCraError('Não foi possível preparar a cópia local da CRA; o download não foi iniciado.') from erro
    return raiz


def guardar_xml(pasta, bruto: str | bytes) -> str:
    dados = bruto.encode('utf-8') if isinstance(bruto, str) else bruto
    if len(dados) > LIMITE_XML:
        raise ImagemCraError('A remessa XML excede o limite de 64 MB.')
    token = hashlib.sha256(dados).hexdigest()
    try:
        _gravar(Path(pasta) / 'Protesto' / 'RemessasCRA' / (token + '.xml'), dados)
    except OSError as erro:
        raise ImagemCraError('Não consegui guardar a cópia local da remessa. Não solicite novo download à CRA.') from erro
    return token


def caminho_xml(pasta, token: str) -> Path:
    if not re.fullmatch('[0-9a-f]{64}', token):
        raise ImagemCraError('Identificação da remessa salva inválida.')
    raiz = (Path(pasta) / 'Protesto' / 'RemessasCRA').resolve()
    caminho = (raiz / (token + '.xml')).resolve()
    if not caminho.is_relative_to(raiz) or not caminho.is_file():
        raise ImagemCraError('A cópia da remessa não foi encontrada.')
    if caminho.stat().st_size > LIMITE_XML or hashlib.sha256(caminho.read_bytes()).hexdigest() != token:
        raise ImagemCraError('A cópia da remessa não passou na conferência de integridade.')
    return caminho


def listar_xml(pasta) -> list[dict]:
    raiz = Path(pasta) / 'Protesto' / 'RemessasCRA'
    if not raiz.is_dir():
        return []
    from datetime import datetime
    return [{'token': file.stem, 'quando': datetime.fromtimestamp(file.stat().st_mtime).strftime('%d/%m/%Y %H:%M'),
             'tamanho': file.stat().st_size}
            for file in sorted(raiz.glob('*.xml'), key=lambda p: p.stat().st_mtime, reverse=True)[:50]
            if re.fullmatch('[0-9a-f]{64}', file.stem)]


def anexar(con, imagens, resultado, *, pasta, agora, usuario_id=None) -> int:
    """Vínculo pelo lote e registro XML que criou o título; mesma transação.

    O arquivo vai ao disco ANTES do INSERT, e por isso um recebimento desfeito
    deixa a imagem órfã em `Titulos/<id>/` — inofensiva no PostgreSQL, em que
    o `id` do título desfeito não volta a ser dado a outro título.
    """
    bd = banco(con)
    quantidade = 0
    for grupo in imagens:
        lote = resultado['lotes'][grupo['lote'] - 1]
        titulo = next((t for t in lote['entraram'] if t['sequencial'] == grupo['sequencial']), None)
        if titulo is None:  # título recusado: os bytes continuam na cópia XML
            continue
        tid = titulo['titulo_id']
        for arquivo in grupo['arquivos']:
            if bd.valor('SELECT EXISTS (SELECT 1 FROM attachments WHERE entity_type=%s '
                        'AND entity_id=%s AND sha256=%s) AS ja',
                        ('PT_TITULO', tid, arquivo['sha256'])):
                continue
            destino = Path(pasta) / 'Protesto' / 'Titulos' / str(tid) / ('cra-' + arquivo['sha256'] + arquivo['extensao'])
            try:
                _gravar(destino, arquivo['conteudo'])
            except OSError as erro:
                raise ImagemCraError('Não consegui salvar as imagens. O recebimento será desfeito; use a cópia local da remessa para tentar novamente.') from erro
            bd.escrever('''INSERT INTO attachments(entity_type,entity_id,original_name,stored_name,
                stored_path,sha256,size_bytes,description,uploaded_by,uploaded_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                ('PT_TITULO', tid, arquivo['nome'], destino.name, str(destino), arquivo['sha256'],
                 len(arquivo['conteudo']), 'Documento do título recebido da CRA junto à remessa XML', usuario_id, agora))
            quantidade += 1
    return quantidade
