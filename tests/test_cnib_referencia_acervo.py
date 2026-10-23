import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date
from contextlib import closing
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import banco_pg
import cnib_atualizador as A
from banco_de_teste import conexao_de_teste


class ReferenciaAcervoTests(unittest.TestCase):
    def banco(self, path=None):
        # cnib_atualizador é PostgreSQL nativo: o banco do teste é o da casa
        # (na pasta pedida, quando o teste precisa do acervo ao lado dele).
        if path is None:
            con=conexao_de_teste()
        else:
            banco_pg.registrar_banco(path);con=sqlite3.connect(path)
        con.row_factory=sqlite3.Row
        con.executescript('''
          CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);
          CREATE TABLE ri_cnib_ordens(id INTEGER PRIMARY KEY,protocolo_cnib TEXT UNIQUE,
            data_pedido TEXT,processo TEXT,instituicao TEXT,forum_vara TEXT,solicitante TEXT,
            cancelamento_protocolo TEXT,cancelamento_data TEXT,ativa INTEGER,
            origem_chave TEXT,origem TEXT);
          CREATE TABLE ri_cnib_pessoas(ordem_id INTEGER,nome TEXT,documento TEXT,origem_chave TEXT);
          CREATE TABLE ri_cnib_leituras(id INTEGER PRIMARY KEY,de TEXT,ate TEXT,pedida_em TEXT,
            terminada_em TEXT,situacao TEXT,lidas INTEGER,novas INTEGER,atualizadas INTEGER,
            canceladas INTEGER,paginas INTEGER,parou_no_teto INTEGER,mensagem TEXT,
            automatica INTEGER,pedida_por INTEGER);
        ''')
        return con

    def test_acervo_original_recupera_referencia_apos_troca_de_todas_as_origens(self):
        with TemporaryDirectory() as td:
            with closing(sqlite3.connect(str(Path(td)/'acervo_eoficio.sqlite3'))) as fonte:
                fonte.execute('CREATE TABLE tbCNIB_Registro(DATAPEDIDO TEXT)')
                fonte.execute("INSERT INTO tbCNIB_Registro VALUES ('2023-03-19 23:28:45')")
                fonte.commit()
            with closing(self.banco(str(Path(td)/'cartorio.sqlite3'))) as con:
                con.execute("INSERT INTO ri_cnib_ordens(protocolo_cnib,data_pedido,ativa,origem) VALUES ('antiga','2016-11-11',1,'EOFICIO')")
                self.assertEqual(A.resumo_do_espelho(con)['retrato_do_acervo'],'2023-03-19')
                con.execute("UPDATE ri_cnib_ordens SET origem='CNIB'")
                self.assertEqual(A.janelas_da_posta_em_dia(con,hoje=date(2026,10,4))[0]['de'],'2023-03-01')

    def test_gravacao_congela_referencia_antes_de_mudar_origem(self):
        with self.banco() as con:
            con.execute("INSERT INTO ri_cnib_ordens(protocolo_cnib,data_pedido,ativa,origem) VALUES ('P','2023-03-19',1,'EOFICIO')")
            A.gravar(con,de='2023-03-01',ate='2023-03-31',agora='2026-10-04',
                leitura={'ordens':[{'protocoloindisponibilidade':'P','datapedido':'19/03/2023'}],'lidas':1})
            self.assertEqual(A.retrato_do_acervo(con),'2023-03-19')
            self.assertEqual(con.execute('SELECT origem FROM ri_cnib_ordens').fetchone()[0],'CNIB')

    def test_leitura_parcial_nao_conclui_mes_nem_avanca_ultima(self):
        with self.banco() as con:
            con.execute("INSERT INTO settings VALUES (?,?)",(A.CHAVE_DO_RETRATO,'2023-03-19'))
            A.anotar(con,de='2023-03-01',ate='2023-03-31',situacao=A.OK,agora='2026-10-04',parou_no_teto=True)
            self.assertFalse(A.janelas_da_posta_em_dia(con,hoje=date(2023,3,31))[0]['feita'])
            self.assertIsNone(A.ultima_leitura(con))

    def test_janela_completa_que_cobre_mes_e_reconhecida(self):
        with self.banco() as con:
            con.execute("INSERT INTO settings VALUES (?,?)",(A.CHAVE_DO_RETRATO,'2023-03-19'))
            A.anotar(con,de='2023-03-01',ate='2023-04-30',situacao=A.OK,agora='2026-10-04')
            self.assertTrue(all(p['feita'] for p in A.janelas_da_posta_em_dia(con,hoje=date(2023,4,30))))

    def test_download_historico_nao_substitui_consulta_do_dia(self):
        with self.banco() as con:
            A.anotar(con,de='2023-03-01',ate='2023-03-31',situacao=A.OK,agora='2026-10-04T12:00:00')
            self.assertFalse(A.ja_leu_hoje(con,hoje=date(2026,10,4)))
            A.anotar(con,de='2026-10-01',ate='2026-10-04',situacao=A.VAZIA,agora='2026-10-04T12:01:00')
            self.assertTrue(A.ja_leu_hoje(con,hoje=date(2026,10,4)))

    def test_rotina_volta_a_rodar_no_dia_seguinte_sem_reiniciar_servidor(self):
        import cnib_web as W
        app=SimpleNamespace(extensions={'usuario_id':lambda:None},route=lambda *a,**k:lambda f:f)
        W.registrar_rotas(app,MagicMock(),lambda f:f,lambda *a:lambda f:f,MagicMock())
        with patch.object(W,'date') as relogio, patch.object(W.threading,'Thread') as thread, \
             patch.object(A,'rotina_ligada',return_value=True), \
             patch.object(A,'ja_leu_hoje',return_value=False), \
             patch.object(A,'esta_pronto',return_value={'pronto':True}), \
             patch.object(A,'janela_do_dia',return_value=('2026-10-01','2026-10-04')):
            relogio.today.return_value=date(2026,10,4)
            app.extensions['cnib_uma_vez_por_dia']()
            app.extensions['cnib_uma_vez_por_dia']()
            self.assertEqual(thread.call_count,1)
            relogio.today.return_value=date(2026,10,5)
            app.extensions['cnib_uma_vez_por_dia']()
            self.assertEqual(thread.call_count,2)

if __name__=='__main__': unittest.main()
