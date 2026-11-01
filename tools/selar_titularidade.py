"""NA TROCA DE DELEGATÁRIO: fecha o livro-caixa e as despesas do titular que sai.

    «em caso de transferência de delegatário, o livro-caixa não ficaria aberto para o novo»
    — o oficial, 31/10/2026

SÓ MEDE POR PADRÃO. Com `--confirmar`, e nesta ordem, sem pular:
  1. copia as tabelas de `cofre_do_titular.TABELAS` e os anexos das despesas;
  2. fecha com a chave do titular, numa pasta que ELE escolhe, fora dos backups;
  3. ABRE DE VOLTA com a senha digitada e confere o SHA-256 e os anexos: sem provar que abre,
     nada se apaga;
  4. pede que digite SELAR, e só então apaga as linhas, os anexos e a chave do banco.

O QUE FICA: o Livro Diário Auxiliar, as receitas e os selos, que são da serventia.

O QUE NÃO ALCANÇA: os backups antigos feitos sem chave continuam abertos onde estiverem, e
as linhas de auditoria continuam no banco. Quem sai precisa estar presente para digitar a
senha: sem isso, não há o que este script faça.

Uso: python tools/selar_titularidade.py --dados <pasta de dados> --saida <pasta> [--confirmar]
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.stdout.reconfigure(encoding="utf-8")

import banco_pg  # noqa: E402
import cofre_do_titular as COT  # noqa: E402
import identidade_do_robo as IDR  # noqa: E402
from bd_nativo import banco  # noqa: E402
from database import Database  # noqa: E402


def _sha(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def main() -> int:
    leitor = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    leitor.add_argument("--dados", required=True, help="a pasta de dados da instalação")
    leitor.add_argument("--saida", required=True, help="onde gravar o arquivo fechado, fora dos backups")
    leitor.add_argument("--confirmar", action="store_true")
    args = leitor.parse_args()
    dados, saida = Path(args.dados), Path(args.saida)
    db = Database(dados / "cartorio_gestao.sqlite3")
    chave = COT.dados_da_chave(db)
    with db.connect() as con:
        bd = banco(con)
        contagens = {t: int(bd.valor(f"SELECT count(*) FROM {t}")) for t in COT.TABELAS}
        anexos = bd.ler("SELECT id, stored_path FROM attachments WHERE entity_type = 'DESPESA'")
    print("Linhas a fechar:", json.dumps(contagens))
    print("Anexos a fechar:", len(anexos))
    print("Chave:", f"de {chave[COT.CHAVE_DE_QUEM]}, impressão {COT.impressao(chave[COT.CHAVE_PUBLICA])}"
          if chave else "NÃO HÁ")
    if not chave:
        print("Sem a chave do titular não há como fechar. Crie-a em Despesas → Configuração.")
        return 1
    if not args.confirmar:
        print("Só medi. Nada foi gravado nem apagado.")
        return 0
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    saida.mkdir(parents=True, exist_ok=True)
    senha = getpass.getpass("Senha do titular: ")
    with TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        dump, vazio = tmp / "tabelas.dump", tmp / "sem_privado.dump"
        banco_pg.copiar_para_arquivo(db.db_path, vazio, contagens={}, tabelas_privadas=COT.TABELAS, privado_em=dump)
        fechado = COT.fechar(dump, saida / f"titularidade_{carimbo}_tabelas.cgt", chave)
        volta = tmp / "volta.dump"
        COT.abrir(fechado, volta, senha)
        if _sha(volta) != _sha(dump):
            print("O arquivo não voltou igual. Nada foi apagado.")
            return 1
        arquivos = tmp / "anexos.zip"
        with zipfile.ZipFile(arquivos, "w") as zf:
            for a in anexos:
                caminho = Path(a["stored_path"])
                if caminho.is_file():
                    zf.write(caminho, caminho.name)
        fechado_anexos = COT.fechar(arquivos, saida / f"titularidade_{carimbo}_anexos.cgt", chave)
        COT.abrir(fechado_anexos, tmp / "volta.zip", senha)
        if _sha(tmp / "volta.zip") != _sha(arquivos):
            print("Os anexos não voltaram iguais. Nada foi apagado.")
            return 1
    print(f"Fechado e conferido em {saida}.")
    print("A partir daqui é irreversível: só esses arquivos, com a sua senha, trazem de volta.")
    if input("Digite SELAR para apagar do banco: ").strip() != "SELAR":
        print("Nada foi apagado. Os arquivos fechados ficaram na pasta.")
        return 0
    with db.transaction() as con:
        bd = banco(con)
        for tabela in COT.NA_ORDEM_DE_APAGAR:
            bd.escrever(f"DELETE FROM {tabela}")
        bd.escrever("DELETE FROM attachments WHERE entity_type = 'DESPESA'")
        bd.escrever("DELETE FROM settings WHERE key = ANY(%s)", (list(COT.AS_QUATRO),))
        IDR.registrar(bd, ts=datetime.now().isoformat(timespec="seconds"), user_id=None, username="agente",
                      action="TITULARIDADE_SELADA", entity_type="settings", entity_id=None,
                      details=json.dumps({"linhas": contagens, "anexos": len(anexos)}),
                      agente="tools/selar_titularidade.py", a_mando_de="titular que digitou a senha")
    for a in anexos:
        COT.apagar_arquivo(Path(a["stored_path"]))
    print("Selado. O Livro Diário Auxiliar continua no sistema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
