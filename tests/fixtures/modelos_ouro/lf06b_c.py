"""O OURO DO LF06B, GRUPO C — as frases dos atos que vão direto ao livro.

Cancelamento nos Indicadores (Livros 4 e 5), cancelamento do registro do
Livro 3, as duas atas de expurgo (Livro 2 e Livro 3) e a parte fixa da
averbação de indisponibilidade da CNIB. Tudo com nomes «DE EXEMPLO», CPF de
teste e datas fixas.

AS QUE GRAVAM SÃO CHAMADAS COM UM DUBLÊ DE BANCO (`_Dubla`): um `Banco` cuja
conexão só anota o SQL e os parâmetros e devolve linhas de exemplo para os
SELECT de que a função precisa. O texto do ato aparece nos parâmetros do
INSERT/UPDATE, e é isso que se grava — a escrita INTEIRA (SQL e parâmetros),
não só a frase, para o ouro pegar também uma regra que mudasse de lugar.
Leitura que não é das tabelas do ato (a busca do modelo da casa, depois da
mudança) devolve nada, e a frase cai no padrão da pasta.
"""
from __future__ import annotations


def chamadas() -> dict:
    import bd_nativo
    import ra_expurgo as RAX
    import ra_registro as RA
    import ri_cnib as CNIB
    import ri_expurgo as RIX
    import ri_indicador_lancamentos as LANC

    agora = "2026-10-19 10:30:00"

    class _Cursor:
        def __init__(self, dubla):
            self.dubla = dubla
            self.description = None
            self.rowcount = 0
            self._linhas: list = []

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, sql, parametros=None):
            linhas = self.dubla.responder(" ".join(str(sql).split()), parametros)
            self._linhas = linhas
            self.description = [("coluna",)] if linhas else None
            self.rowcount = len(linhas)

        def fetchall(self):
            return list(self._linhas)

    class _Conexao:
        def __init__(self, dubla):
            self.dubla = dubla

        def cursor(self, **_):
            return _Cursor(self.dubla)

    class _Dubla:
        """Um banco de mentira: anota as escritas, responde os SELECT do ato."""

        def __init__(self, respostas: dict):
            self.respostas = respostas      # pedaço do SQL -> linhas
            self.escritas: list = []
            self._id = 100

        def responder(self, sql, parametros):
            if sql.split(" ", 1)[0].upper() in ("INSERT", "UPDATE", "DELETE"):
                self.escritas.append({"sql": sql, "parametros": list(parametros or ())})
                if "RETURNING" in sql.upper():
                    self._id += 1
                    return [{"id": self._id}]
                return []
            for pedaco, linhas in self.respostas.items():
                if pedaco in sql:
                    return [dict(x) for x in linhas]
            return []

        def con(self):
            b = bd_nativo.Banco.__new__(bd_nativo.Banco)
            b._pg, b._ponte = _Conexao(self), None
            return b

    def _rodar(funcao, respostas: dict, **kw):
        d = _Dubla(respostas)
        devolveu = funcao(d.con(), **kw)
        return {"devolveu": devolveu, "escritas": d.escritas}

    # -- 1. Indicadores (Livros 4 e 5), cancelamento de ato do Livro 2
    matricula = {"id": 7, "numero": "1840", "logradouro": "Rua de Exemplo, 10",
                 "bairro": "Centro", "descricao_perimetro": None}
    matricula_sem_end = {"id": 8, "numero": "1841", "logradouro": None,
                         "bairro": None, "descricao_perimetro": None}
    ato = {"id": 70, "tipo": "R", "numero": 3}
    parte1 = {"id": 501, "nome": "FULANO DE EXEMPLO", "documento_tipo": "CPF",
              "documento_numero": "00000000191", "papel": "PROPRIETARIO"}
    parte2 = {"id": 502, "nome": "BELTRANA DE EXEMPLO", "documento_tipo": "CPF",
              "documento_numero": "00000000191", "papel": "PROPRIETARIA"}
    motivo = "Mandado judicial do processo 0000000-00.2026.8.10.0000, Cidade Exemplo."

    f: dict = {}
    for nome_caso, mat, partes in (
            ("com_partes", matricula, [parte1, parte2]),
            ("sem_partes", matricula_sem_end, [])):
        f[f"ri_indicador_lancamentos.registrar_cancelamento_livro2({nome_caso})"] = (
            lambda m=mat, p=partes: _rodar(
                LANC.registrar_cancelamento_livro2,
                {"FROM ri_partes": p},
                matricula=m, ato_alvo=ato, averbacao_id=90, averbacao_numero=4,
                motivo=motivo, usuario="escrevente.exemplo", agora=agora))

    # -- 1b. Indicadores, cancelamento do registro do Livro 3
    reg_cheio = {"id": 30, "numero": 12, "natureza": "CEDULA_CREDITO_RURAL",
                 "titulo_tipo": "Cédula Rural Pignoratícia",
                 "titulo_numero": "40/01800-8", "situacao": "ATIVO"}
    reg_vazio = {"id": 31, "numero": 13, "natureza": None, "titulo_tipo": None,
                 "titulo_numero": None, "situacao": "ATIVO"}
    for nome_caso, reg, partes in (
            ("com_partes", reg_cheio, [parte1]),
            ("sem_partes", reg_vazio, [])):
        f[f"ri_indicador_lancamentos.registrar_cancelamento_livro3({nome_caso})"] = (
            lambda r=reg, p=partes: _rodar(
                LANC.registrar_cancelamento_livro3,
                {"FROM ra_partes": p},
                registro=r, averbacao_id=91, averbacao_numero=2,
                motivo=motivo, usuario=None, agora=agora,
                data_lancamento="2026-10-18 09:00:00"))

    # -- 2. Cancelamento do registro do Livro 3 (a averbação + os Indicadores)
    def _cancelar(reg, partes, motivo_dado):
        return _rodar(
            lambda con, **kw: RA.cancelar(con, reg["id"], **kw),
            {"FROM ra_registros": [reg], "MAX(numero)": [{"n": 1}],
             "FROM ra_partes": partes},
            motivo=motivo_dado, agora=agora, usuario="escrevente.exemplo")
    f["ra_registro.cancelar(com_partes)"] = lambda: _cancelar(
        reg_cheio, [parte1], "  Quitação da cédula apresentada em Cidade Exemplo.  ")
    f["ra_registro.cancelar(sem_partes)"] = lambda: _cancelar(
        reg_vazio, [], "Pedido do credor, por instrumento particular.")

    # -- 3. Ata do expurgo do Livro 2
    ato_cheio = {"data_ato": "2026-08-18", "natureza_titulo": "Compra e venda",
                 "prenotacao": 4321, "lavrado_em": "2026-08-18 15:00:00",
                 "lavrado_nome": "FULANO DE EXEMPLO",
                 "lavrado_titulo": "Escrevente Autorizado",
                 "emolumentos": "R$ 123,45", "selo_texto": "SELO-EXEMPLO-0001",
                 "hash_ato": "0" * 64,
                 "teor": "R-3/1840 — Compra e venda.\nComprador: FULANO DE EXEMPLO.\n\nValor: R$ 1,00."}
    sv_cheio = {"unit_name": "Ofício Único de Exemplo", "ri_cns": "000000",
                "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
    f["ri_expurgo.texto_da_ata(cheia)"] = lambda: RIX.texto_da_ata(
        rotulo="R-3/1840", ato=ato_cheio,
        matricula={"numero": "1840", "livro": "2", "cidade": "Outra", "uf": "PI"},
        sv=sv_cheio, data_extenso="19 de outubro de 2026",
        motivo="Ato lavrado em teste; selo cancelado no Tribunal.",
        selo_cancelado="SELO-EXEMPLO-0001", usuario="oficial.exemplo",
        partes=[parte1, {"id": 503, "nome": "BELTRANA DE EXEMPLO",
                         "documento_tipo": None, "documento_numero": None,
                         "papel": None}])
    f["ri_expurgo.texto_da_ata(vazia)"] = lambda: RIX.texto_da_ata(
        rotulo="AV-2/1841", ato={"protocolo": 99, "teor": ""},
        matricula={"numero": "1841", "cidade": "Cidade Exemplo"},
        sv={}, data_extenso="19 de outubro de 2026",
        motivo="Selo cancelado.", selo_cancelado=None, usuario=None,
        partes=None)
    f["ri_expurgo.texto_da_ata(sem_cidade)"] = lambda: RIX.texto_da_ata(
        rotulo="R-1/1", ato={"teor": None, "emolumentos": 0},
        matricula={"numero": None, "livro": None},
        sv={"unit_name": "", "ri_cns": None}, data_extenso="1º de janeiro de 2026",
        motivo="", selo_cancelado="", usuario="", partes=[])

    # -- 4. Ata do expurgo do Livro 3
    ato3 = {"tipo": "AV", "numero": 2, "data_ato": "2026-10-01",
            "teor": "  AV-2 — Averbação de exemplo, FULANO DE EXEMPLO.  "}
    f["ra_expurgo.compor_ata(cheia)"] = lambda: RAX.compor_ata(
        registro_numero=12, ato=ato3, motivo="Lançado na ficha errada",
        agora="19/10/2026 10:30", usuario="escrevente.exemplo", minuta_id=55)
    f["ra_expurgo.compor_ata(vazia)"] = lambda: RAX.compor_ata(
        registro_numero=13, ato={"tipo": None, "numero": None, "data_ato": None,
                                 "teor": None, "motivo_cancelamento": None},
        motivo=None, agora="19/10/2026 10:30", usuario=None)
    f["ra_expurgo.compor_ata(motivo_cancelamento)"] = lambda: RAX.compor_ata(
        registro_numero="13", ato={"tipo": "AV", "numero": "3", "data_ato": "",
                                   "teor": "", "motivo_cancelamento": "Cancelado a pedido."},
        motivo="  ", agora="19/10/2026 10:30", usuario="  ", minuta_id=0)
    f["ra_expurgo.registrar"] = lambda: _rodar(
        lambda con, **kw: RAX.registrar(con, **kw), {},
        registro_id=30, registro_numero=12, ato=ato3, motivo="Lançado na ficha errada",
        agora="19/10/2026 10:30", usuario="escrevente.exemplo", minuta_id=55)

    # -- 5. CNIB: a parte fixa e o teor preparado
    mat_estr = {"id": 7, "numero": "1840", "tipo_ficha": "ESTRUTURADA"}
    mat_acervo = {"id": 9, "numero": "1842", "tipo_ficha": "ACERVO"}
    protocolo = {"numero": 4321, "data_prenotacao": "2026-10-01 08:00:00"}

    def _fixa(mat, prot, **kw):
        d = _Dubla({"FROM ri_matriculas": [mat] if mat else [],
                    "FROM ri_protocolos": [prot] if prot else []})
        return CNIB.parte_fixa(d.con(), 7, **kw)
    f["ri_cnib.parte_fixa(sem_con)"] = lambda: CNIB.parte_fixa()
    f["ri_cnib.parte_fixa(matricula_inexistente)"] = lambda: _fixa(None, None, numero=5)
    f["ri_cnib.parte_fixa(com_protocolo)"] = lambda: _fixa(mat_estr, protocolo, numero=5)
    f["ri_cnib.parte_fixa(sem_protocolo)"] = lambda: _fixa(mat_estr, None, numero=12)
    f["ri_cnib.parte_fixa(acervo_sem_numero)"] = lambda: _fixa(mat_acervo, protocolo)
    f["ri_cnib.parte_fixa(protocolo_data_ruim)"] = lambda: _fixa(
        mat_estr, {"numero": 1, "data_prenotacao": "ontem"}, numero=5)

    ordem = {"protocolo_cnib": " 202610190000001 ", "data_pedido": "2026-10-18",
             "instituicao": " Tribunal de Justiça de Exemplo ",
             "forum_vara": " 1ª Vara de Cidade Exemplo ",
             "processo": "0000000-00.2026.8.10.0000",
             "nome": "FULANO DE EXEMPLO", "documento": "00000000191"}
    ordem_vazia = {"instituicao": "", "forum_vara": None}

    def _teor(o, mat, prot, **kw):
        d = _Dubla({"FROM ri_matriculas": [mat] if mat else [],
                    "FROM ri_protocolos": [prot] if prot else []})
        return CNIB.teor_preparado(o, d.con(), 7, **kw)
    f["ri_cnib.teor_preparado(cheia)"] = lambda: _teor(ordem, mat_estr, protocolo, numero=5)
    f["ri_cnib.teor_preparado(vazia)"] = lambda: _teor(ordem_vazia, mat_acervo, None)
    f["ri_cnib.teor_preparado(so_orgao)"] = lambda: _teor(
        dict(ordem, forum_vara=""), mat_estr, protocolo, numero=5)
    f["ri_cnib.teor_preparado(so_vara)"] = lambda: _teor(
        dict(ordem, instituicao=None), mat_estr, protocolo, numero=5)
    f["ri_cnib.teor_preparado(sem_con)"] = lambda: CNIB.teor_preparado(ordem)
    return f
