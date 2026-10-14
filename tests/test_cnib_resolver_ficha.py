import re,unittest
from test_cnib_aviso_pendente import AvisoCnibTests
import ri_cnib as C
import ri_minuta as M
from ri_schema import consultar_cnib

class ResolverFichaTests(AvisoCnibTests):
 def _post(self,decisao='NAO_E_A_PESSOA',motivo='Documento conferido: trata-se de outra pessoa.',protocolo=None,token=True):
  with self.app.test_client() as client:
   with client.session_transaction() as s:s['user_id']=self.uid
   h=client.get(f'/registro-imoveis/{self.mid}').get_data(as_text=True)
   if 'id="cnib-pendente"' in h:
    self.assertIn('Não é a mesma pessoa',h);self.assertIn('Ordem já baixada',h)
   csrf=re.search(r'name="csrf_token"\s+value="([^"]+)"',h).group(1)
   o=self.ordens[0]
   data={'decisao':decisao,'motivo':motivo,'protocolo_cnib':protocolo or o['protocolo_cnib'],'pessoa_nome':o['nome'],'pessoa_documento':o['documento']}
   if token:data['csrf_token']=csrf
   return client.post(f'/registro-imoveis/{self.mid}/cnib/resolver',data=data,follow_redirects=True)
 def test_botoes_decisao_historico_e_outra_matricula_preservada(self):
  outro=self.con.execute("INSERT INTO ri_matriculas(numero,livro,livro_norm,criado_em) VALUES ('4100','2','2','2026-10-05')").lastrowid
  self.con.execute('INSERT INTO ri_partes(matricula_id,nome,papel) VALUES (?, ?, ?)',(outro,'José da Silva','proprietario'));self.con.commit()
  resp=self._post();self.assertEqual(resp.status_code,200)
  h=resp.get_data(as_text=True)
  self.assertNotIn('id="cnib-pendente"',h)
  self.assertIn('Conferências da CNIB registradas',h)
  self.assertIn('Documento conferido: trata-se de outra pessoa.',h)
  d=self.con.execute('SELECT * FROM ri_cnib_decisoes').fetchone()
  self.assertEqual(d['decisao'],'NAO_E_A_PESSOA');self.assertTrue(d['decidido_por'])
  self.assertEqual(len(C.filtrar_pendentes(self.con,outro,self.ordens)),1)
  self.assertEqual(self.con.execute('SELECT ativa FROM ri_cnib_ordens').fetchone()[0],1)
 def test_baixa_requer_evidencia_e_descarta_somente_minuta_vinculada(self):
  k=C.chave_da_minuta(self.mid,self.ordens[0])
  ligada=M.criar(self.con,matricula_id=self.mid,tipo='AV',teor='Minuta de indisponibilidade para revisao.',agora='2026-10-05',origem_chave=k)
  outra=M.criar(self.con,matricula_id=self.mid,tipo='AV',teor='Outra minuta sem relacao com esta ordem.',agora='2026-10-05');self.con.commit()
  self._post(decisao='ORDEM_BAIXADA',motivo='ok')
  self.assertEqual(self.con.execute('SELECT COUNT(*) FROM ri_cnib_decisoes').fetchone()[0],0)
  self.assertEqual(M.uma(self.con,ligada)['situacao'],'A_REVISAR')
  resp=self._post(decisao='ORDEM_BAIXADA',motivo='Baixa conferida na Central, protocolo CANCEL-123 de 05/10/2026.')
  self.assertIn('Ordem confirmada como baixada',resp.get_data(as_text=True))
  self.assertEqual(M.uma(self.con,ligada)['situacao'],'DESCARTADA')
  self.assertEqual(M.uma(self.con,outra)['situacao'],'A_REVISAR')
  self.assertEqual(len(consultar_cnib(self.con,[],['José da Silva'])),1)
 def test_rejeita_post_sem_csrf_ordem_fabricada_e_decisao_invalida(self):
  self.assertEqual(self._post(token=False).status_code,400)
  self._post(protocolo='ORDEM-INEXISTENTE')
  self._post(decisao='AVERBADA')
  self.assertEqual(self.con.execute('SELECT COUNT(*) FROM ri_cnib_decisoes').fetchone()[0],0)
 def test_duplo_clique_idempotente_e_motivo_escapado(self):
  motivo='Documento e CPF diferentes. <script>alert(1)</script>'
  self._post(motivo=motivo);resp=self._post(motivo=motivo)
  self.assertEqual(self.con.execute('SELECT COUNT(*) FROM ri_cnib_decisoes').fetchone()[0],1)
  h=resp.get_data(as_text=True)
  self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;',h)
  self.assertNotIn('<script>alert(1)</script>',h)
  self._post(decisao='ORDEM_BAIXADA',motivo='Outra conferencia posterior enviada por engano.')
  self.assertEqual(self.con.execute('SELECT decisao FROM ri_cnib_decisoes').fetchone()[0],'NAO_E_A_PESSOA')

if __name__=='__main__':unittest.main()
