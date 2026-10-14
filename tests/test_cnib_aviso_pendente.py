import sqlite3,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import cnib_atualizador as A
import ri_cnib as C
import ri_minuta as M
from ri_schema import normalizar_busca,consultar_cnib

class AvisoCnibTests(unittest.TestCase):
 def setUp(self):
  from app import create_app
  self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.app=create_app({'TESTING':True,'DATA_DIR':Path(self.tmp.name)})
  self.app.extensions['backup_checked']=True;self.app.extensions['cnib_verificado']=True
  self.db=self.app.extensions['db']
  self.uid=self.db.create_user('teste_cnib','Teste CNIB','Senha#12345','ADMIN')
  self.con=self.db.connect();self.addCleanup(self.con.close);self.con.row_factory=sqlite3.Row
  self.mid=self.con.execute("INSERT INTO ri_matriculas(numero,livro,livro_norm,criado_em) VALUES ('4099','2','2','2026-10-04')").lastrowid
  self.con.execute('INSERT INTO ri_partes(matricula_id,nome,documento_numero,papel) VALUES (?,?,?,?)',(self.mid,'José da Silva','11111111111','proprietario'))
  A._gravar_ordem(self.con,{'protocoloindisponibilidade':'202610.0000.00000001-IA-001','datapedido':'2026-10-04','numeroprocesso':'PROCESSO1','partes':[{'nomerazao':'JOSÉ DA SILVA','cpfcnpj':'22222222222'}]})
  self.con.commit()
  self.ordens=consultar_cnib(self.con,['11111111111'],['José da Silva'])
 def test_importacao_normaliza_nome_e_busca_com_documento_diferente(self):
  self.assertEqual(len(self.ordens),1);self.assertEqual(self.ordens[0]['criterio'],'nome')
  self.assertEqual(self.con.execute('SELECT nome_norm FROM ri_cnib_pessoas').fetchone()[0],normalizar_busca('José da Silva'))
 def test_minuta_preparada_nao_retira_alerta_e_lavrada_retira(self):
  k=C.chave_da_minuta(self.mid,self.ordens[0])
  minuta=M.criar(self.con,matricula_id=self.mid,tipo='AV',teor='Minuta de indisponibilidade para revisar.',agora='2026-10-04',origem_chave=k)
  self.assertEqual(len(C.filtrar_pendentes(self.con,self.mid,self.ordens)),1)
  ato=self.con.execute("INSERT INTO ri_atos(matricula_id,tipo,numero,lavrado_em,hash_ato) VALUES (?,'AV',1,'2026-10-04','teste')",(self.mid,)).lastrowid
  M.marcar_lavrada(self.con,minuta,ato_id=ato,agora='2026-10-04')
  self.assertEqual(C.filtrar_pendentes(self.con,self.mid,self.ordens),[])
 def test_decisao_de_homonimo_e_cancelamento_retiram_alerta(self):
  C.decidir(self.con,matricula_id=self.mid,ordem=self.ordens[0],decisao=C.NAO_E_A_PESSOA,motivo='CPF conferido e diferente',ato_id=None,quem='Teste',agora='2026-10-04')
  self.assertEqual(C.filtrar_pendentes(self.con,self.mid,self.ordens),[])
  self.con.execute('UPDATE ri_cnib_ordens SET ativa=0')
  self.assertEqual(consultar_cnib(self.con,[],['José da Silva']),[])
 def test_ficha_mostra_alerta_vermelho_no_alto_por_nome(self):
  with self.app.test_client() as client:
   with client.session_transaction() as s:s['user_id']=self.uid
   r=client.get(f'/registro-imoveis/{self.mid}')
   self.assertEqual(r.status_code,200)
   h=r.get_data(as_text=True)
   self.assertIn('ATENÇÃO — POSSÍVEL INDISPONIBILIDADE PENDENTE',h)
   self.assertIn('background:#a40016;color:#fff',h)
   self.assertIn('conferir possível homônimo',h)
   self.assertLess(h.index('id="cnib-pendente"'),h.index('id="novo-ato"'))

if __name__=='__main__':unittest.main()
