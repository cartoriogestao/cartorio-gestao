"""A senha de consulta do título no ONR — o `CodigoVerificador` (27/11/2026).

    A primeira chamada real ao Acompanhamento de Títulos voltou com «código 36
    — Código Verificador não foi informado»: o manual o dá como opcional, e o
    serviço o exige. É a senha com que o apresentante abre, com o número do
    protocolo, o andamento no Acompanhamento Registral Online (API REST do ONR,
    `protocoloRequest.senha`). Estes testes cobrem: nasce com o «prenotado»,
    sobe no `InsertTituloAT`, fica cifrada, não aparece na prévia nem no erro,
    e sai na ficha e no comprovante. Dados inventados.
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import onr_acompanhamento as A                                     # noqa: E402
import onr_wsoficio as W                                           # noqa: E402
from bd_nativo import banco                                        # noqa: E402
from test_onr_acompanhamento import (AGORA, CERT, ONRDeMentira, _Db,  # noqa: E402,F401
                                     _cofre, _eventos, _soap, _token, con, pasta)


def _enviar(con, pasta, onr, **k):
    return A.enviar_pendentes(
        _Db(con), lambda: W.Sessao(ambiente=W.HOMOLOGACAO, pasta=pasta, transporte=onr,
                                   certificado=CERT),
        amb=W.HOMOLOGACAO, quem="beatriz", agora=lambda: AGORA, **k)


class Recusa(ONRDeMentira):
    def __call__(self, url, corpo, acao):
        metodo = acao.rsplit("/", 1)[-1]
        if metodo == "InsertTituloAT":
            self.chamadas.append((url, metodo, corpo.decode("utf-8")))
            return 200, _soap(metodo, "<RETORNO>false</RETORNO><CODIGOERRO>15</CODIGOERRO>"
                                      "<ERRODESCRICAO>O CPF/CNPJ do apresentante é inválido."
                                      "</ERRODESCRICAO>")
        return super().__call__(url, corpo, acao)


def test_a_senha_nasce_com_o_prenotado_e_sobe_no_insert_titulo(con, pasta):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    con.commit()
    senha = A.senha_ja_gravada(con, 10)
    assert A.senha_valida(senha) and len(senha) == 8
    onr = ONRDeMentira()
    assert _enviar(con, pasta, onr)["enviados"] == 1
    (titulo,) = onr.de("InsertTituloAT")
    assert f"<CodigoVerificador>{senha}</CodigoVerificador>" in titulo
    # na ordem do contrato: depois da natureza, antes do tipo da solicitação
    nomes = re.findall(r"<(\w+)>", titulo.split("<oRequest>")[1].split("</oRequest>")[0])
    assert nomes.index("NaturezaTitulo") < nomes.index("CodigoVerificador") \
        < nomes.index("TipoSolicitacao")
    assert A.senha_ja_gravada(con, 10) == senha               # a mesma, sempre


def test_o_titulo_antigo_ganha_a_senha_na_hora_do_envio(con, pasta):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    banco(con).escrever("DELETE FROM onr_at_senhas")
    con.commit()
    assert A.senha_ja_gravada(con, 10) is None
    onr = ONRDeMentira()
    assert _enviar(con, pasta, onr)["enviados"] == 1
    senha = A.senha_ja_gravada(con, 10)
    assert senha and f"<CodigoVerificador>{senha}</CodigoVerificador>" in onr.de("InsertTituloAT")[0]


def test_a_senha_fica_cifrada_e_presa_ao_titulo(con, pasta, _cofre):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    con.commit()
    senha = A.senha_ja_gravada(con, 10)
    cifra = banco(con).valor("SELECT cifra FROM onr_at_senhas WHERE protocolo_id=10")
    assert senha not in cifra and cifra.startswith("v1:")
    assert A._decifrar(con, 11, cifra) is None                # copiada para outro título, não abre
    assert (_cofre / A.ARQUIVO_DO_COFRE).is_file()            # a chave mora no cofre, fora do banco
    assert not (_cofre / "portal.cred").exists()              # e não no do portal da casa
    import cofre_cred as COFRE
    assert A.ARQUIVO_DO_COFRE == COFRE.ONR_ACOMPANHAMENTO in COFRE.ARQUIVOS


def test_senha_que_nao_abre_e_trocada_so_antes_de_subir(con, pasta, _cofre):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    con.commit()
    (_cofre / A.ARQUIVO_DO_COFRE).unlink()                    # o cofre perdeu a chave
    assert A.senha_ja_gravada(con, 10) is None
    nova = A.senha_do_titulo(con, 10, agora=AGORA)
    assert A.senha_valida(nova) and A.senha_ja_gravada(con, 10) == nova
    banco(con).escrever("""INSERT INTO onr_at_titulos (ambiente, protocolo_id, protocolo_numero,
        id_titulo_onr, como, cadastrado_em) VALUES ('HOMOLOGACAO', 10, '11600', 900,
        'CADASTRADO', %s)""", (AGORA,))
    (_cofre / A.ARQUIVO_DO_COFRE).unlink()
    with pytest.raises(A.AcompanhamentoError, match="UpdateTituloAT"):
        A.senha_do_titulo(con, 10, agora=AGORA)


def test_cofre_fora_do_ar_para_a_rodada_sem_mandar(con, pasta, monkeypatch):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    banco(con).escrever("DELETE FROM onr_at_senhas")
    con.commit()

    def quebra(con):
        raise OSError("disco cheio")
    monkeypatch.setattr(A, "_pasta_do_cofre", quebra)
    onr = ONRDeMentira()
    feito = _enviar(con, pasta, onr)
    assert feito["enviados"] == 0 and "senha de consulta" in feito["parou"]
    assert onr.de("InsertTituloAT") == []
    assert _eventos(con)[0]["situacao"] == "PENDENTE"


def test_a_senha_nao_aparece_na_previa_nem_no_erro(con, pasta):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    con.commit()
    senha = A.senha_ja_gravada(con, 10)
    previa = A.previa_da_prova(con, 10, amb=W.HOMOLOGACAO)
    campos = dict(previa["vai"]["campos"])
    assert campos["CodigoVerificador"] == A.MASCARA_DA_SENHA
    assert senha not in previa["vai"]["envelope"]
    onr = Recusa()
    feito = _enviar(con, pasta, onr)
    assert feito["recusados"] == 1 and senha in onr.de("InsertTituloAT")[0]
    ev = _eventos(con)[0]
    assert senha not in (ev["ultimo_erro"] or "") and senha not in str(feito)


def test_a_ficha_e_o_comprovante_mostram_a_senha(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    html = c.get("/registro-imoveis/protocolo").get_data(as_text=True)
    c.post("/registro-imoveis/protocolo", data={
        "apresentante": "MARIO DE TESTE", "natureza_titulo": "COMPRA E VENDA",
        "objeto": "escritura", "livro_destino": "2", "telefone": "(99) 90000-0000",
        "csrf_token": _token(html)}, follow_redirects=True)
    with db.connect() as cx:
        pid = banco(cx).valor("SELECT MAX(id) FROM ri_protocolos")
        senha = A.senha_ja_gravada(cx, pid)
    assert A.senha_valida(senha)
    ficha = c.get(f"/registro-imoveis/protocolo/{pid}").get_data(as_text=True)
    assert "data-senha-onr" in ficha and senha in ficha

    def texto(resposta):
        with zipfile.ZipFile(io.BytesIO(resposta.data)) as z:
            return re.sub(r"<[^>]+>", " ", z.read("content.xml").decode("utf-8"))

    # envio desligado: o comprovante não fala do ONR
    assert senha not in texto(c.get(f"/registro-imoveis/protocolo/{pid}/comprovante"))
    db.set_settings({A.CHAVE_LIGADO: "1"})
    papel = texto(c.get(f"/registro-imoveis/protocolo/{pid}/comprovante"))
    assert senha in papel and "Acompanhamento Registral Online" in papel
