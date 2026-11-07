"""Semente da casa de ensaio: protesto. Ver `layout_casa.py`.

O QUE ELA PÕE NA CASA
    Um título em cada estado que muda as fases da ficha (`ESTADOS`), do começo ao fim do rito, e o
    que cada rota com número da área precisa para abrir: o aviso, o edital, a remessa da CRA com o
    que ela gera (confirmação, andamento, o XML guardado, a imagem), a desistência, a guia de
    repasse, o XML da CENPROT, a relação diária, a pendência da CENPROT, a intimação da Resolve e o
    instrumento.

COMO ELA CHEGA LÁ
    O título e os atos nascem pela tela (`/protesto/novo`, `/protesto/<id>/lancar`), com o selo
    digitado no formato do selo do TJMA, porque aqui não há selador. O que a tela não alcança, como
    a intimação de dezoito dias atrás, que dá o tríduo vencido, nasce pela função de domínio com a
    data que o ato teria. O que viria da rede (a desistência da CRA, a pendência da CENPROT, o lote
    da Resolve) entra pela mesma função que a tela chamaria, com a resposta da Central dada à mão.

SE UM PASSO FALHAR
    A semente segue e conta tudo no fim, de uma vez: com a primeira falha só, o erro seguinte
    ficava escondido, e cada rodada custa minutos.
"""
from __future__ import annotations

import hashlib
import io
import itertools
import traceback
import zipfile
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import layout_ensaio as E

#: Rota com número que não tem como abrir aqui: endpoint -> o motivo.
SEM_SEMENTE: dict[str, str] = {}

#: Um título para cada estado: `casa.ids["protesto_<chave>"]` e a situação em que ele fica.
#: `test_layout_fichas_protesto` lê esta tabela.
ESTADOS: dict[str, str] = {
    "recebido": "RECEBIDO",
    "apontado": "APONTADO",
    "intimado_no_prazo": "INTIMADO",
    "intimado_vencido": "INTIMADO",
    "protestado": "PROTESTADO",
    "pago": "PAGO",
    "desistido": "DESISTIDO",
    "cancelado": "CANCELADO",
    "devolvido": "DEVOLVIDO",
    "sustado": "APONTADO",
}

# O razão de selos não aceita o mesmo número duas vezes, e as outras áreas semeiam na mesma casa:
# o fim do selo é do Protesto («PT»), e não o que o pedido da semente sugere para todas.
SELO = "AVESVD000000PT{:014d}"
#: Os itens que o cancelamento e a desistência pagam no caixa (#373), na vigência das sementes
#: (a do RCPJ): (código interno, código TJ, descrição).
CANCELAMENTO_NO_CAIXA = (990703, "17.3", "Cancelamento do protesto (ensaio)")
DESISTENCIA_NO_CAIXA = (990704, "17.4.1", "Desistência após o apontamento (ensaio)")
VIGENCIA_DO_CAIXA = 10022
NOME = "Beatriz Exemplo"
CPF = "00000000191"
# Dois CNPJ fictícios, e nenhum é o da serventia (a base usa o 00.000.001/0000-55).
CNPJ = "00000010000127"
CNPJ_DA_ENTIDADE = "00000011000171"
PDF = b"%PDF-1.4\n% Ensaio do layout\n"
NOSSO_NUMERO = "10000000000{:04d}"

TITULO = {
    "especie": "NP", "numero_titulo": "", "data_emissao": "2026-08-10", "data_vencimento": "2026-09-10",
    "valor": "1.234,56", "saldo": "1.234,56", "praca_protesto": "CIDADE EXEMPLO", "tipo_protesto": "C",
    "motivo_protesto": "1", "tipo_moeda": "1", "aceite": "N",
    "apresentante_nome": "BANCO EXEMPLO", "apresentante_documento": CNPJ,
    "apresentante_endereco": "Avenida Exemplo, 1, Centro, Cidade Exemplo/MA",
    "cedente_nome": "CARLA EXEMPLO", "cedente_documento": "00000000272",
    "cedente_endereco": "Rua das Flores, 10", "cedente_cidade": "Cidade Exemplo", "cedente_uf": "MA",
    "devedor_nome": "MARIO EXEMPLO", "devedor_documento_tipo": "CPF", "devedor_documento": CPF,
    "devedor_endereco": "Rua Exemplo, 200", "devedor_bairro": "Centro", "devedor_cep": "65000000",
    "devedor_cidade": "Cidade Exemplo", "devedor_uf": "MA",
}


class _Semeador:
    def __init__(self, casa):
        self.casa = casa
        self.c = casa.cliente("ADMIN", "novo")
        self.falhas: list[str] = []
        self._selos = itertools.count(1)
        self.pasta = casa.app.extensions["archive_root"]()
        self.hoje = casa.hoje

    # ---------------------------------------------------------------- o que cada passo precisa

    @contextmanager
    def passo(self, nome: str):
        try:
            yield
        except Exception as erro:  # noqa: BLE001 - a semente conta tudo o que falhou, de uma vez
            quadros = traceback.extract_tb(erro.__traceback__)[-3:]
            onde = " <- ".join(f"{Path(q.filename).name}:{q.lineno}" for q in reversed(quadros))
            self.falhas.append(f"{nome}: {type(erro).__name__}: {str(erro)[:700]} [{onde}]")

    def selo(self) -> str:
        return SELO.format(next(self._selos))

    def dia(self, atras: int) -> str:
        return (date.fromisoformat(self.hoje) - timedelta(days=atras)).isoformat()

    def extenso(self, dia: str) -> str:
        from ri_web import data_por_extenso
        return data_por_extenso(date.fromisoformat(dia))

    def serventia(self) -> dict:
        from serventia import dados
        return dados(self.casa.db.get_settings)

    def recados(self, resposta) -> list[str]:
        """O que a tela disse depois do envio: no corpo, ou na página para onde ela mandou."""
        if resposta.status_code == 200:
            corpo = resposta.get_data(as_text=True)
        else:
            corpo = self.c.get(resposta.headers.get("Location", "/")).get_data(as_text=True)
        return [texto for _classe, texto in E.ler_pagina(corpo).flashes]

    # ---------------------------------------------------------------- o título e os atos, pela tela

    def titulo(self, numero: str, **mudar) -> int:
        resposta = self.casa.postar("/protesto/novo", _cliente=self.c, **{**TITULO, "numero_titulo": numero, **mudar})
        achado = self.casa.um("SELECT id, situacao FROM pt_titulos WHERE numero_titulo=%s", (numero,))
        if not achado or achado["situacao"] != "RECEBIDO":
            raise AssertionError(f"o título {numero} não nasceu pela tela: {self.recados(resposta)}")
        return int(achado["id"])

    def atos(self, titulo_id: int, tipo: str) -> list[int]:
        return [int(r["id"]) for r in self.casa.ler(
            "SELECT id FROM pt_atos WHERE titulo_id=%s AND tipo=%s AND cancelado=0 ORDER BY id", (titulo_id, tipo))]

    def lancar(self, titulo_id: int, ato: str, *, com_selo: bool = True, **campos) -> int:
        # A tela volta para a ficha até quando recusa: quem diz se o ato nasceu é o banco.
        antes = set(self.atos(titulo_id, ato))
        if com_selo:
            campos["selo"] = self.selo()
        resposta = self.casa.postar(f"/protesto/{titulo_id}/lancar", _cliente=self.c, ato=ato, **campos)
        novos = set(self.atos(titulo_id, ato)) - antes
        if not novos:
            raise AssertionError(f"{ato} não foi lançado no título {titulo_id}: {self.recados(resposta)}")
        return max(novos)

    def pago_no_caixa(self, servico: int, codigo_tj: str, descricao: str, interessado: str) -> dict:
        """O protocolo geral QUITADO, com o item do ato (17.3 do cancelamento, 17.4 da desistência).

        Desde o #373, desistência e cancelamento só se efetivam com o emolumento pago no caixa:
        a semente faz o que o balcão faz — abre o caixa, abre o protocolo, quita — e o ato se
        lança com o item marcado. Devolve os campos que a ficha manda junto.
        """
        casa = self.casa
        # A MESMA vigência que a semente do RCPJ cria (com início, que é a que `custas` prefere):
        # uma segunda vigência vigente faria a semente da gestão pôr os itens dela na errada.
        vigencia = VIGENCIA_DO_CAIXA
        casa.sql("INSERT INTO cx_vigencias (codigo, descricao, vigente, inicio, fim, importado_em) "
                 "VALUES (%s, '2026', 1, '2026-01-01', NULL, '2026-08-21') ON CONFLICT (codigo) DO NOTHING",
                 (vigencia,))
        casa.sql("INSERT INTO cx_servicos (codigo, codigo_tj, descricao, ativo) VALUES (%s, %s, %s, 1) "
                 "ON CONFLICT (codigo) DO NOTHING",
                 (servico, codigo_tj, descricao))
        casa.sql("INSERT INTO cx_servico_valores (servico, vigencia, emolumentos, ferc, fadep, femp, "
                 "ferrfis, total) VALUES (%s, %s, '40,00', '0,00', '0,00', '0,00', '0,00', '40,00') "
                 "ON CONFLICT (servico, vigencia) DO NOTHING", (servico, vigencia))
        if not casa.um("SELECT id FROM cx_caixas WHERE situacao = 'ABERTO' ORDER BY id LIMIT 1"):
            casa.postar("/caixa", _cliente=self.c, acao="abrir", saldo_inicial="0")
        casa.postar("/caixa/protocolos", _cliente=self.c, acao="novo", interessado=interessado,
                    telefone="(00) 90000-0000", atribuicao="PROTESTO")
        pid = int(casa.um("SELECT id FROM cx_protocolos ORDER BY id DESC LIMIT 1")["id"])
        ficha = f"/caixa/protocolos/{pid}/itens"
        casa.postar(ficha, _cliente=self.c, acao="acrescentar", servico=str(servico))
        casa.postar(ficha, _cliente=self.c, acao="quitar_todos", forma_pagamento="DINHEIRO")
        item = casa.um("SELECT id, quitado FROM cx_protocolo_atos WHERE protocolo_id = %s "
                       "ORDER BY id DESC LIMIT 1", (pid,))
        if not item or not item["quitado"]:
            raise AssertionError(f"o protocolo {pid} não ficou quitado com o item {codigo_tj}")
        return {"protocolo_id": str(pid), "protocolo_item_id": str(item["id"])}

    def apontado(self, numero: str, **mudar) -> int:
        titulo_id = self.titulo(numero, **mudar)
        self.lancar(titulo_id, "APONTAMENTO", com_selo=False)
        return titulo_id

    def aviso(self, titulo_id: int) -> int:
        resposta = self.casa.postar(f"/protesto/{titulo_id}/aviso", _cliente=self.c)
        achado = self.casa.um("SELECT id FROM pt_avisos WHERE titulo_id=%s ORDER BY id DESC LIMIT 1", (titulo_id,))
        if not achado:
            raise AssertionError(f"o aviso do título {titulo_id} não saiu: {self.recados(resposta)}")
        return int(achado["id"])

    def intimado_ha_tempo(self, numero: str, **mudar) -> int:
        """Apontado há vinte dias e intimado há dezoito: o tríduo já venceu. A tela só grava o ato
        com a data de hoje, e por isso estes dois passos vão pela função de domínio."""
        from prova_de_intimacao import entregar_com_comprovante
        import protesto as PT
        import protesto_aviso as AV
        titulo_id = self.titulo(numero, **mudar)
        d1, d2 = self.dia(20), self.dia(18)
        sv, extenso = self.serventia(), self.extenso(d1)    # `get_settings` abre a conexão dele: fora da transação
        with self.casa.transacao() as con:
            PT.lancar_apontamento(con, titulo_id, sv=sv, agora=f"{d1}T10:00:00", data_extenso=extenso, usuario=NOME)
            aviso = AV.emitir(con, titulo_id, hoje=d1, agora=f"{d1}T10:00:00", usuario=NOME)
            entregar_com_comprovante(con, aviso["aviso_id"], pasta=self.pasta, agora=f"{d2}T10:00:00",
                                     quando=d2, usuario=NOME)
        return titulo_id

    # ---------------------------------------------------------------- os passos

    def configurar(self) -> None:
        """O que as telas exigem e a base não traz. Só preenche o que está em branco: outra área
        pode ter posto o seu."""
        padrao = {"serventia_horario": "de segunda a sexta, das 8h às 17h",
                  "ibge_uf": "21", "ibge_municipio": "00001", "ibge_cartorio": "01"}
        faltando = {k: v for k, v in padrao.items() if not str(self.casa.db.get_setting(k, "") or "").strip()}
        if faltando:
            self.casa.db.set_settings(faltando)

    def a_certidao_da_base(self) -> None:
        """A carga de demonstração traz uma certidão negativa, pedida em nome de «SANDBOX»."""
        certidao = self.casa.um("SELECT id FROM pt_certidoes WHERE requerente LIKE %s ORDER BY id LIMIT 1",
                                ("SANDBOX%",))
        if not certidao:
            raise AssertionError("a certidão negativa da base não está lá")
        self.casa.ids["protesto_certidao_da_base"] = int(certidao["id"])

    def os_titulos_do_rito(self) -> None:
        casa = self.casa
        casa.ids["protesto_recebido"] = self.titulo("ENSAIO-01", devedor_nome="MARIO EXEMPLO")

        casa.ids["protesto_apontado"] = self.apontado("ENSAIO-02", devedor_nome="BEATRIZ EXEMPLO")
        casa.ids["protesto_aviso_emitido"] = self.aviso(casa.ids["protesto_apontado"])

        # Intimado agora, por edital: o tríduo ainda não começou, e o edital só se chega a ele pela
        # não-entrega do aviso.
        tid = self.apontado("ENSAIO-03", devedor_nome="CARLA EXEMPLO")
        aviso = self.aviso(tid)
        self.casa.postar(f"/protesto/avisos/{aviso}/entrega", _cliente=self.c,
                         entregue="0", motivo="1", quando=self.hoje)
        self.casa.postar(f"/protesto/avisos/{aviso}/edital", _cliente=self.c,
                         justificativa="Devedor mudou-se e não há outro endereço conhecido.")
        casa.ids["protesto_intimado_no_prazo"] = tid
        casa.ids["protesto_aviso_do_edital"] = aviso

        casa.ids["protesto_intimado_vencido"] = self.intimado_ha_tempo("ENSAIO-04", devedor_nome="ANA EXEMPLO")

        protestado = self.intimado_ha_tempo("ENSAIO-05", devedor_nome="MARIO EXEMPLO")
        casa.ids["protesto_ato_do_protesto"] = self.lancar(
            protestado, "PROTESTO",
            motivo_atraso="Comprovante da intimação devolvido pelo entregador depois do prazo.")
        casa.ids["protesto_protestado"] = protestado

        pago = self.apontado("ENSAIO-06", devedor_nome="MARIO EXEMPLO")
        casa.ids["protesto_ato_do_pagamento"] = self.lancar(
            pago, "PAGAMENTO", valor_pago="1234,56", forma_pagamento="ESPECIE", emolumentos="50,00")
        casa.ids["protesto_pago"] = pago

        cancelado = self.intimado_ha_tempo("ENSAIO-08", devedor_nome="JOÃO MODELO")
        self.lancar(cancelado, "PROTESTO", motivo_atraso="Comprovante da intimação devolvido depois do prazo.")
        self.lancar(cancelado, "CANCELAMENTO", **self.pago_no_caixa(*CANCELAMENTO_NO_CAIXA, "JOÃO MODELO"),
                    hipotese="ANUENCIA_CREDOR",
                    fundamento="Anuência do credor, com firma reconhecida, trazida ao balcão.")
        casa.ids["protesto_cancelado"] = cancelado

        # A ordem judicial não muda a situação, e muda o que a ficha oferece: sai o que a ordem
        # impede (protestar, pagar, desistir) e entra o de revogá-la.
        sustado = self.apontado("ENSAIO-10", devedor_nome="CARLA EXEMPLO")
        self.lancar(sustado, "SUSTACAO", com_selo=False, juizo="1ª Vara Cível de Cidade Exemplo",
                    processo="0000000-00.2026.8.10.0000", observacao="Ordem de sustação trazida ao balcão.")
        casa.ids["protesto_sustado"] = sustado

    def a_desistencia_da_cra(self) -> None:
        """O arquivo de desistência vem no clique do dia, que fala com a CRA. A função é a do
        clique; a CRA responde o que se põe na mão."""
        import protesto_cra_pedidos as PCP
        casa = self.casa
        desistido = self.apontado("ENSAIO-07", devedor_nome="BEATRIZ EXEMPLO")
        titulo = casa.um("SELECT protocolo, numero_titulo, saldo_centavos FROM pt_titulos WHERE id=%s", (desistido,))
        respostas = {
            "desistencias": _arquivo_de_desistencia(self.hoje, [titulo | {"nome": "BEATRIZ EXEMPLO"}]),
            "cancelamentos": "<relatorio><codigo>0007</codigo><ocorrencia>Nenhum cancelamento pendente."
                             "</ocorrencia></relatorio>",
            "autorizacoes": ""}
        PCP.trazer_do_dia(casa.db.transaction, lambda o_que, _nome, _com_imagem: respostas[o_que],
                          dia=self.hoje, agora=f"{self.hoje}T11:00:00", usuario=NOME, pasta_reserva=self.pasta)
        desistencia = casa.um("SELECT id FROM pt_desistencias ORDER BY id DESC LIMIT 1")
        if not desistencia:
            raise AssertionError("o arquivo de desistência não foi guardado")
        # Desde o #373 o arquivo só se guarda: a desistência se lança na ficha, paga no caixa.
        self.lancar(desistido, "DESISTENCIA",
                    **self.pago_no_caixa(*DESISTENCIA_NO_CAIXA, "BEATRIZ EXEMPLO"),
                    motivo="O apresentante desistiu pela CRA; o emolumento foi pago no caixa.")
        casa.ids["protesto_desistido"] = desistido
        casa.ids["protesto_desistencia"] = int(desistencia["id"])
        casa.ids["protesto_consultas_da_cra"] = [int(r["id"]) for r in casa.ler(
            "SELECT id FROM pt_cra_consultas ORDER BY id")]

    def o_titulo_devolvido(self) -> None:
        """DEVOLVIDO só entra pela fila de correções de ofício, e quem aprova é o oficial em pessoa."""
        import correcoes_de_oficio as CDO
        casa = self.casa
        titulo_id = self.apontado("ENSAIO-09", devedor_nome="ANA EXEMPLO")
        oficial = casa.db.get_user(casa.ids["admin"])
        agora = f"{self.hoje}T12:00:00"
        with casa.transacao() as con:
            proposta = CDO.propor(
                con, tipo=CDO.TituloDevolvido.chave, quem=oficial, agora=agora,
                parametros={"titulo_id": titulo_id, "data_ocorrencia": self.dia(3)},
                motivo="Título devolvido por irregularidade, código 5 da CRA, conforme o retorno do apresentante.")
            if not proposta["ok"]:
                raise AssertionError(f"a proposta de devolução foi recusada: {proposta['recusas']}")
            decisao = CDO.aprovar(con, proposta["id"], aprovador=oficial, afirmo=True, agora=agora,
                                  afirmacao="Afirmo, sob minha responsabilidade, que o título veio com irregularidade "
                                            "e que a devolução está de acordo com o retorno da CRA.")
            if not decisao["ok"]:
                raise AssertionError(f"a devolução não foi aprovada: {decisao}")
        casa.ids["protesto_devolvido"] = titulo_id

    def a_remessa_da_cra(self) -> None:
        """A remessa pelas telas de conferir e receber. Ela gera a confirmação e o andamento, que
        são os arquivos de retorno, e dois títulos que já saem apontados e com a chave da CENPROT."""
        casa = self.casa
        texto = _remessa_da_cra(self.hoje)
        self.casa.postar("/protesto/remessas/conferir", _cliente=self.c,
                         arquivo=(io.BytesIO(texto.encode("latin-1")), "B0001101.261"))
        resposta = self.casa.postar("/protesto/remessas/receber", _cliente=self.c,
                                    conteudo=texto.replace("\r\n", "\n"), nome_arquivo="B0001101.261", apontar="1")
        remessa = casa.um("SELECT id FROM pt_remessas ORDER BY id DESC LIMIT 1")
        if not remessa:
            raise AssertionError(f"a remessa não entrou: {self.recados(resposta)}")
        casa.ids["protesto_remessa"] = int(remessa["id"])
        casa.ids["protesto_retornos"] = [int(r["id"]) for r in casa.ler("SELECT id FROM pt_retornos ORDER BY id")]
        titulos = casa.ler("SELECT id FROM pt_titulos WHERE remessa_id=%s ORDER BY id", (remessa["id"],))
        if len(titulos) != 2:
            raise AssertionError(f"a remessa devia trazer 2 títulos e trouxe {len(titulos)}")
        casa.ids["protesto_cra_um"], casa.ids["protesto_cra_dois"] = (int(t["id"]) for t in titulos)

    def o_xml_da_remessa_guardado(self) -> None:
        """Conferir uma remessa em XML guarda a cópia local antes de ler: é ela que a rota serve."""
        xml = _remessa_em_xml(_remessa_da_cra(self.hoje, numero="0002"))
        self.casa.postar("/protesto/remessas/conferir", _cliente=self.c, arquivo=(io.BytesIO(xml), "remessa-cra.xml"))
        self.casa.ids["protesto_remessa_salva"] = hashlib.sha256(xml).hexdigest()

    def a_imagem_do_titulo(self) -> None:
        pacote = io.BytesIO()
        with zipfile.ZipFile(pacote, "w") as z:
            z.writestr(f"001/{NOSSO_NUMERO.format(2)}_{CPF}.pdf", PDF + b"imagem do titulo\n")
        resposta = self.casa.postar("/protesto/imagens", _cliente=self.c,
                                    arquivo=(io.BytesIO(pacote.getvalue()), "imagens.zip"))
        anexo = self.casa.um("SELECT id FROM attachments WHERE entity_type='PT_TITULO' AND entity_id=%s",
                             (self.casa.ids["protesto_cra_dois"],))
        if not anexo:
            raise AssertionError(f"a imagem não foi anexada: {self.recados(resposta)}")
        self.casa.ids["protesto_anexo"] = int(anexo["id"])

    def o_pagamento_e_a_guia_do_repasse(self) -> None:
        casa = self.casa
        ato = self.lancar(casa.ids["protesto_cra_um"], "PAGAMENTO", valor_pago="1000,00",
                          forma_pagamento="ESPECIE", emolumentos="40,00")
        casa.ids["protesto_pagamento_cra"] = ato
        resposta = self.casa.postar("/protesto/repasses/guias", _cliente=self.c, ato_id=str(ato))
        guia = casa.um("SELECT id FROM pt_repasse_guias ORDER BY id DESC LIMIT 1")
        if not guia:
            raise AssertionError(f"a guia de repasse não saiu: {self.recados(resposta)}")
        casa.ids["protesto_guia"] = int(guia["id"])

    def o_xml_da_cenprot(self) -> None:
        """O pagamento do título da CRA vai no XML «D» do dia, e o apresentante dele tem de estar cadastrado."""
        casa = self.casa
        # `Casa.postar` tem um parâmetro `endereco`, e este formulário, um campo com o mesmo nome.
        self.c.post("/protesto/cenprot-xml/apresentantes", data={
            "csrf_token": casa.token(self.c), "codigo": "001", "nome": "BANCO EXEMPLO", "documento": CNPJ,
            "tipo_apresentante": "1", "endereco": "Avenida Exemplo, 1, Centro, Cidade Exemplo/MA"})
        resposta = self.casa.postar("/protesto/cenprot-xml/gerar", _cliente=self.c, letra="D")
        arquivo = casa.um("SELECT id FROM pt_cenprot_xml ORDER BY id DESC LIMIT 1")
        if not arquivo:
            raise AssertionError(f"o XML do dia não foi gerado: {self.recados(resposta)}")
        casa.ids["protesto_xml"] = int(arquivo["id"])

    def a_relacao_diaria(self) -> None:
        casa = self.casa
        self.casa.postar("/protesto/relacao-diaria/entidades", _cliente=self.c, nome="ENTIDADE EXEMPLO",
                         documento=CNPJ_DA_ENTIDADE, canal="DIRETO", habilitacao="Pedido de habilitação n. 1/2026",
                         habilitada_em=self.dia(40))
        entidade = casa.um("SELECT id FROM pt_relacao_entidades ORDER BY id DESC LIMIT 1")
        if not entidade:
            raise AssertionError("a entidade não foi habilitada")
        resposta = self.casa.postar("/protesto/relacao-diaria/gerar", _cliente=self.c,
                                    entidade_id=str(entidade["id"]), dia=self.dia(1))
        relacao = casa.um("SELECT id FROM pt_relacoes_diarias ORDER BY id DESC LIMIT 1")
        if not relacao:
            raise AssertionError(f"a relação do dia não saiu: {self.recados(resposta)}")
        casa.ids["protesto_relacao"] = int(relacao["id"])

    def o_instrumento(self) -> None:
        casa = self.casa
        titulo_id = casa.ids["protesto_protestado"]
        resposta = self.casa.postar(f"/protesto/{titulo_id}/instrumento", _cliente=self.c)
        instrumento = casa.um("SELECT id FROM pt_instrumentos WHERE titulo_id=%s ORDER BY id DESC LIMIT 1",
                              (titulo_id,))
        if not instrumento:
            raise AssertionError(f"o instrumento não foi emitido: {self.recados(resposta)}")
        casa.ids["protesto_instrumento"] = int(instrumento["id"])

    def o_maco_de_avisos(self) -> None:
        """O PDF com várias intimações, separado pelo QR do aviso emitido do título apontado."""
        import protesto_intimacoes_lote as LOTE
        casa = self.casa
        aviso = casa.um("SELECT id, numero, ano, titulo_id FROM pt_avisos WHERE id=%s",
                        (casa.ids["protesto_aviso_emitido"],))
        protocolo = casa.um("SELECT protocolo FROM pt_titulos WHERE id=%s", (aviso["titulo_id"],))["protocolo"]
        pdf = _maco_escaneado(LOTE.conteudo_do_qr(aviso, protocolo))
        resposta = self.casa.postar("/protesto/avisos/lote", _cliente=self.c, pdf=(io.BytesIO(pdf), "maco.pdf"))
        sha = hashlib.sha256(pdf).hexdigest()
        if not (Path(self.pasta) / "Protesto" / "Intimacoes" / "lotes" / f"{sha}.pdf").exists():
            raise AssertionError(f"o maço de avisos não foi guardado: {self.recados(resposta)}")
        casa.ids["protesto_maco_de_avisos"] = sha

    def a_pendencia_da_cenprot(self) -> None:
        """A anuência que a CENPROT mandou, casada pelo protocolo com o título protestado."""
        import cenprot_pendencias as PEND
        import cn_schema as CN
        casa = self.casa
        titulo = casa.um("SELECT protocolo, numero_titulo FROM pt_titulos WHERE id=%s",
                         (casa.ids["protesto_protestado"],))
        item = {"cd_anuencia": 9001, "nm_nr_protocolo": titulo["protocolo"], "nm_devedor": "MARIO EXEMPLO",
                "nm_nr_titulo": titulo["numero_titulo"], "vl_protesto": 1234.56,
                "dt_solicitacao_anuencia": self.dia(1)}
        with mock.patch.dict(PEND.BAIXA_DA_ESPECIE, {CN.ANUENCIA: lambda _onde, pasta=None, **_filtros: [item]}):
            PEND.baixar(casa.db, CN.ANUENCIA, ambiente="PRODUCAO", quem=NOME)
        pendencia = casa.um("SELECT id FROM cn_pendencias WHERE especie=%s ORDER BY id DESC LIMIT 1", (CN.ANUENCIA,))
        if not pendencia:
            raise AssertionError("a pendência da CENPROT não entrou")
        casa.ids["protesto_pendencia"] = int(pendencia["id"])

    def a_intimacao_da_resolve(self) -> None:
        import resolve_api as API
        import resolve_intimacao as RI

        def criar_lote(lote, _ambiente=None, *, pasta=None):
            return {"message": "ok", "id": "LOTE-ENSAIO-1",
                    "intimacoes": [{"_id": f"INT-ENSAIO-{i}", "identificador": x["identificador"]}
                                   for i, x in enumerate(lote, 1)]}

        casa = self.casa
        with mock.patch.object(API, "criar_lote", criar_lote):
            RI.enviar(casa.db, [casa.ids["protesto_cra_dois"]], ambiente="PRODUCAO", quem=NOME)
        intimacao = casa.um("SELECT id FROM rs_intimacoes ORDER BY id DESC LIMIT 1")
        if not intimacao:
            raise AssertionError("a intimação digital não foi gravada")
        casa.ids["protesto_intimacao_digital"] = int(intimacao["id"])

    # ---------------------------------------------------------------- os endereços

    def anotar(self) -> None:
        casa = self.casa
        ids = casa.ids
        for chave in (*(f"protesto_{estado}" for estado in ESTADOS), "protesto_cra_um", "protesto_cra_dois"):
            if chave in ids:
                casa.pagina("protesto_titulo", titulo_id=ids[chave])
        # Sem o `formato`, o papel sai em PDF e chama o LibreOffice, que a trava barra e a rota
        # responde com um redirecionamento. O `.odt` é o papel de verdade.
        odt = {"formato": "odt"}
        para_anotar = (
            ("protesto_aviso_odt", "aviso_id", ids.get("protesto_aviso_emitido"), odt),
            ("protesto_aviso_odt", "aviso_id", ids.get("protesto_aviso_do_edital"), odt),
            ("protesto_instrumento_odt", "instrumento_id", ids.get("protesto_instrumento"), odt),
            ("protesto_quitacao_odt", "ato_id", ids.get("protesto_ato_do_pagamento"), odt),
            ("protesto_quitacao_odt", "ato_id", ids.get("protesto_pagamento_cra"), odt),
            ("protesto_certidao", "certidao_id", ids.get("protesto_certidao_da_base"), None),
            ("protesto_certidao_odt", "certidao_id", ids.get("protesto_certidao_da_base"), odt),
            ("protesto_cenprot_xml_baixar", "xml_id", ids.get("protesto_xml"), None),
            ("protesto_pendencia", "pendencia_id", ids.get("protesto_pendencia"), None),
            ("protesto_pendencia_arquivos", "pendencia_id", ids.get("protesto_pendencia"), None),
            ("protesto_desistencia", "desistencia_id", ids.get("protesto_desistencia"), None),
            ("protesto_desistencia_arquivo", "desistencia_id", ids.get("protesto_desistencia"), None),
            ("protesto_remessa", "remessa_id", ids.get("protesto_remessa"), None),
            ("protesto_remessa_arquivo", "remessa_id", ids.get("protesto_remessa"), None),
            ("protesto_remessa_salva", "token", ids.get("protesto_remessa_salva"), None),
            ("protesto_imagem", "anexo_id", ids.get("protesto_anexo"), None),
            ("protesto_repasse_guia", "guia_id", ids.get("protesto_guia"), None),
            ("protesto_repasse_guia_relacao", "guia_id", ids.get("protesto_guia"), None),
            ("protesto_relacao_arquivo", "relacao_id", ids.get("protesto_relacao"), None),
            ("protesto_resolve_ficha", "intimacao_id", ids.get("protesto_intimacao_digital"), None),
            ("protesto_avisos_lote_folhas", "sha", ids.get("protesto_maco_de_avisos"), {"p": "1"}),
        )
        for endpoint, argumento, valor, consulta in para_anotar:
            if valor is not None:
                casa.pagina(endpoint, _consulta=consulta, **{argumento: valor})
        for retorno in ids.get("protesto_retornos", []):
            casa.pagina("protesto_retorno_arquivo", retorno_id=retorno)
        for consulta in ids.get("protesto_consultas_da_cra", []):
            casa.pagina("protesto_cra_consulta_arquivo", consulta_id=consulta)
        periodo = {"de": "2026-01-01", "ate": self.hoje}
        for qual in ("protocolo", "pagamentos"):
            casa.pagina("protesto_livro", _consulta=periodo, qual=qual)
            casa.pagina("protesto_livro", _consulta={**periodo, **odt}, qual=qual)
        # Os títulos do ensaio têm todos o mesmo CPF, e o painel do devedor os junta: um abre todos.
        devedor = casa.um("SELECT min(id) AS id FROM pt_devedores")
        if devedor and devedor["id"]:
            casa.pagina("protesto_devedor", devedor_id=int(devedor["id"]))
        edital = casa.um("SELECT id FROM pt_editais ORDER BY id DESC LIMIT 1")
        if edital:
            casa.pagina("protesto_edital_odt", edital_id=int(edital["id"]))


# -------------------------------------------------------------------- os arquivos da CRA

def _remessa_da_cra(dia: str, *, numero: str = "0001") -> str:
    """A remessa de dois títulos do apresentante 001, de 600 posições, pelo escritor da casa."""
    import protesto_arquivo as PA
    titulos = [{
        "tipo_registro": "1", "codigo_do_apresentante": "001", "identificacao_do_apresentante": "",
        "cedente_nome": "LOJA EXEMPLO LTDA", "cedente_nome_2": "LOJA EXEMPLO LTDA",
        "cedente_documento": CNPJ, "cedente_endereco": "Rua das Flores, 10", "cedente_cep": "65000000",
        "cedente_cidade": "Cidade Exemplo", "cedente_uf": "MA", "nosso_numero": NOSSO_NUMERO.format(i),
        "especie": "DMI", "numero_do_titulo": f"CRA-0{i}", "data_de_emissao": "2026-09-01",
        "data_de_vencimento": "2026-09-30", "tipo_de_moeda": 1, "valor_do_titulo": 100000 + i,
        "saldo_a_protestar": 100000 + i, "praca_de_protesto": "CIDADE EXEMPLO", "tipo_de_endosso": "M",
        "aceite": "N", "motivo_do_protesto": "1", "devedor_nome": "ANA EXEMPLO",
        "devedor_tipo_de_documento": 2, "devedor_documento": CPF, "devedor_endereco": "Rua Exemplo, 300",
        "devedor_cep": "65000000", "devedor_cidade": "Cidade Exemplo", "devedor_uf": "MA",
        "devedor_bairro": "Centro", "sequencial": i + 1} for i in (1, 2)]
    soma = sum(t["saldo_a_protestar"] for t in titulos)
    arquivo = PA.Arquivo(
        tipo="BFOSDTTPR", sentido="ENTRADA", nome_do_tipo=PA.TIPOS["BFOSDTTPR"]["nome"],
        cabecalho={"tipo_registro": "0", "codigo_do_apresentante": "001", "nome_do_apresentante": "BANCO EXEMPLO",
                   "data_do_movimento": dia, "tipo_do_arquivo": "BFOSDTTPR", "numero_da_remessa": int(numero),
                   # Os contadores que a remessa em XML confere: títulos, indicações e originais.
                   "reservado_68": "0000" "0002" "0002" "0000" "000000", "codigo_do_portador": "", "sequencial": 1},
        titulos=titulos,
        rodape={"tipo_registro": "9", "codigo_do_apresentante": "001", "nome_do_apresentante": "BANCO EXEMPLO",
                "data_do_movimento": dia, "quantidade_de_registros": len(titulos) + 2, "soma_dos_valores": soma,
                "sequencial": len(titulos) + 2})
    return PA.escrever(arquivo, renumerar_sequencial=True)


def _remessa_em_xml(texto: str) -> bytes:
    """A mesma remessa no XML da CRA21: um atributo por campo do layout."""
    import html
    import protesto_cra_xml as XML
    linhas = [x for x in texto.replace("\r", "").split("\n") if x.strip()]
    partes = ['<?xml version="1.0" encoding="utf-8"?><remessa>',
              '<nome_arquivo>remessa-ensaio.xml</nome_arquivo><comarca CodMun="000001">']
    for tag, linha in zip(("hd",) + ("tr",) * (len(linhas) - 2) + ("tl",), linhas):
        inicio, atributos = 0, []
        prefixo = "h" if tag == "hd" else "t"
        for i, largura in enumerate(XML.LARGURAS[tag], 1):
            atributos.append(f'{prefixo}{i:02}="{html.escape(linha[inicio:inicio + largura].rstrip(), quote=True)}"')
            inicio += largura
        partes.append(f"<{tag} {' '.join(atributos)}/>")
    partes.append("</comarca></remessa>")
    return "".join(partes).encode("utf-8")


def _arquivo_de_desistencia(dia: str, titulos: list[dict]) -> str:
    """O arquivo DP da CRA: 127 posições, cinco tipos de registro e o sequencial no fim."""
    ddmmaaaa = f"{dia[8:10]}{dia[5:7]}{dia[:4]}"
    apresentante = "BANCO EXEMPLO".ljust(45)

    def linha(corpo: str, sequencial: int) -> str:
        return corpo.ljust(122)[:122] + f"{sequencial:05d}"

    n = len(titulos)
    soma = sum(int(t["saldo_centavos"]) for t in titulos)
    linhas = [linha(f"0001{apresentante}{ddmmaaaa}{n:05d}00001", 1), linha(f"103{n:05d}0000001", 2)]
    for i, t in enumerate(titulos, start=3):
        protocolo = t["protocolo"]
        # O protocolo da casa é AAMMDD e o sequencial do dia: a data do arquivo é a do apontamento.
        data_do_protocolo = f"{protocolo[4:6]}{protocolo[2:4]}20{protocolo[:2]}"
        linhas.append(linha("2" + protocolo.ljust(10)[:10] + data_do_protocolo + t["numero_titulo"].ljust(11)[:11]
                            + t["nome"].ljust(45)[:45] + f"{int(t['saldo_centavos']):014d}" + "S" + "0" * 12, i))
    linhas.append(linha(f"803{n:05d}", n + 3))
    linhas.append(linha(f"9001{apresentante}{ddmmaaaa}{2 * n:05d}{soma:014d}", n + 4))
    return "\r\n".join(linhas) + "\r\n"


def _maco_escaneado(qr: str) -> bytes:
    """Uma folha de aviso com o QR, virada imagem como sai do scanner: o QR se lê da imagem, e não
    de um objeto vetorial que nenhum scanner produz."""
    import protesto_intimacoes_lote as LOTE
    try:
        import pymupdf as fitz
    except ImportError:  # pragma: no cover
        import fitz
    doc = fitz.open()
    pagina = doc.new_page()
    pagina.insert_text((72, 140), "AVISO DE INTIMACAO - folha de ensaio")
    pagina.insert_image(fitz.Rect(260, 30, 331, 101), stream=LOTE.png_do_qr(qr))
    escaneado = fitz.open()
    png = doc[0].get_pixmap(dpi=150, colorspace="gray").tobytes("png")
    nova = escaneado.new_page(width=doc[0].rect.width, height=doc[0].rect.height)
    nova.insert_image(nova.rect, stream=png)
    return escaneado.tobytes()


# -------------------------------------------------------------------- a semente

def semear(casa) -> None:
    s = _Semeador(casa)
    for nome, passo in (
            ("configuração", s.configurar),
            ("a certidão da base", s.a_certidao_da_base),
            ("os títulos do rito", s.os_titulos_do_rito),
            ("a desistência da CRA", s.a_desistencia_da_cra),
            ("o título devolvido", s.o_titulo_devolvido),
            ("a remessa da CRA", s.a_remessa_da_cra),
            ("o XML da remessa guardado", s.o_xml_da_remessa_guardado),
            ("a imagem do título", s.a_imagem_do_titulo),
            ("o pagamento e a guia do repasse", s.o_pagamento_e_a_guia_do_repasse),
            ("o XML da CENPROT", s.o_xml_da_cenprot),
            ("a relação diária", s.a_relacao_diaria),
            ("o instrumento", s.o_instrumento),
            ("o maço de avisos", s.o_maco_de_avisos),
            ("a pendência da CENPROT", s.a_pendencia_da_cenprot),
            ("a intimação da Resolve", s.a_intimacao_da_resolve)):
        with s.passo(nome):
            passo()
    s.anotar()
    assert not s.falhas, "a semente do protesto não fechou:\n  " + "\n  ".join(s.falhas)
