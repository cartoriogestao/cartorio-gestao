"""Documento e API locais: codigo validado, selecao humana e isolamento de anexos."""
from datetime import date
from io import BytesIO

import fitz
import numpy as np
import pytest
import zxingcpp
from PIL import Image

import despesas as DP
import despesas_documento as DD
from bd_nativo import banco
from tests.conftest import cg_login
from tests.test_despesas import AGORA, boleto, pix
from tests.test_despesas_fluidez import BASE, _cadastrar, _token

HOJE = date(2026,11,4)


def _png(texto, formato=zxingcpp.BarcodeFormat.QRCode):
    codigo=zxingcpp.create_barcode(texto,formato)
    imagem=Image.fromarray(np.asarray(zxingcpp.write_barcode_to_image(codigo,scale=4)))
    buf=BytesIO(); imagem.save(buf,format='PNG'); return buf.getvalue()


def _pdf():
    with fitz.open() as doc:
        p=doc.new_page()
        p.insert_text((30,35),boleto(12345),fontsize=9)
        p.insert_image(fitz.Rect(30,70,260,300),stream=_png(pix('123.45')))
        return doc.tobytes()


def test_le_qr_pix_e_barra_itf_sem_rede():
    qr=DD.ler(_png(pix('123.45')),hoje=HOJE)['opcoes']
    barras=DD.ler(_png(boleto(12345),zxingcpp.BarcodeFormat.ITF),hoje=HOJE)['opcoes']
    assert qr[0]['forma']==DP.PIX_COPIA_E_COLA and qr[0]['valor']=='123,45'
    assert barras[0]['forma']==DP.BOLETO and barras[0]['codigo']==boleto(12345)


def test_pdf_apresenta_as_duas_alternativas_para_usuario_escolher():
    r=DD.ler(_pdf(),hoje=HOJE)
    assert {o['forma'] for o in r['opcoes']}=={DP.BOLETO,DP.PIX_COPIA_E_COLA}
    assert all(o['pagina']==1 for o in r['opcoes'])


@pytest.mark.parametrize('texto',['https://example.com/pagar','Telefone 11999999999','000201corrompido'])
def test_qr_de_site_telefone_ou_pix_sem_crc_nao_vira_pagamento(texto):
    assert DD.ler(_png(texto),hoje=HOJE)['opcoes']==[]


def test_recusa_pdf_grande_protegido_imagem_gigante_e_arquivo_ilegivel():
    with fitz.open() as doc:
        for _ in range(13): doc.new_page()
        com_paginas=doc.tobytes()
    with fitz.open() as doc:
        doc.new_page()
        protegido=doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256,user_pw='ficticia')
    img=Image.new('L',(4000,4000),'white'); buf=BytesIO(); img.save(buf,format='PNG')
    for conteudo in (com_paginas,protegido,buf.getvalue(),b'nao e arquivo',b'x'*(DD.MAX_BYTES+1)):
        with pytest.raises(DP.DespesaError): DD.ler(conteudo,hoje=HOJE)


def test_api_le_upload_sem_cadastrar_ou_enviar_pagamento(cg_casa_logada):
    c,db=cg_casa_logada['c'],cg_casa_logada['db']
    r=c.post(BASE+'/ler-documento',data={'csrf_token':_token(c,BASE+'/nova'),
        'documento':(BytesIO(_pdf()),'fatura-ficticia.pdf')})
    assert r.status_code==200 and len(r.json['opcoes'])==2
    with db.connect() as con: assert banco(con).valor('SELECT count(*) FROM dp_despesas')==0
    assert 'Buscar Pix ou boleto' in c.get(BASE+'/nova').get_data(as_text=True)


def test_anexo_exige_despesa_certa_caminho_da_despesa_e_perfil(cg_casa_logada,tmp_path):
    casa=cg_casa_logada; db,c=casa['db'],casa['c']; i=_cadastrar(db)
    conteudo=_pdf()
    with db.transaction() as con:
        uid=banco(con).um("SELECT id FROM users WHERE username='mario'")['id']
        a=DP.guardar_anexo(con,i,nome_arquivo='fatura-ficticia.pdf',conteudo=conteudo,
            pasta=casa['acervo']/'despesas',usuario_id=uid,agora=AGORA.isoformat())
    rota=f'{BASE}/{i}/ler-anexo/{a}'; csrf=_token(c,f'{BASE}/{i}')
    r=c.post(rota,data={'csrf_token':csrf})
    assert r.status_code==200 and len(r.json['opcoes'])==2
    assert c.post(f'{BASE}/{i+1}/ler-anexo/{a}',data={'csrf_token':csrf}).status_code==404
    db.create_user('balcao','BALCAO EXEMPLO','Senha#12345','USER')
    outro=casa['app'].test_client(); cg_login(outro,'balcao','Senha#12345')
    assert outro.post(rota,data={'csrf_token':_token(outro,BASE+'/nova')}).status_code==403
    externo=tmp_path/'outra.pdf'; externo.write_bytes(conteudo)
    with db.transaction() as con:
        banco(con).escrever('UPDATE attachments SET stored_path=%s WHERE id=%s',(str(externo),a))
    assert c.post(rota,data={'csrf_token':csrf}).status_code==404
