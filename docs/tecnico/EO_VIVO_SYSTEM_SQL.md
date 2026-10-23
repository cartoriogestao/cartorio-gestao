# Liberar E-Ofício ao vivo para o CartorioGestao (SYSTEM)

## Causa
O CartorioGestao sobe pela tarefa agendada `CartorioGestaoServidor` como
`AUTORIDADE NT\SISTEMA` (SYSTEM). A instancia `MSSQL$SERVER` esta no ar e
`SERVIDOR\usuario` (sysadmin) abre `bdCartorio`, mas SYSTEM tem login no SQL
Server sem usuario no banco `bdCartorio` — Integrated Security falha.

## O que o Admin executa (sqlcmd ou SSMS), logado como monte/sysadmin

```sql
USE [bdCartorio];
IF NOT EXISTS (
  SELECT 1 FROM sys.database_principals WHERE name = N'AUTORIDADE NT\SISTEMA'
)
  CREATE USER [AUTORIDADE NT\SISTEMA] FOR LOGIN [AUTORIDADE NT\SISTEMA];
ALTER ROLE db_datareader ADD MEMBER [AUTORIDADE NT\SISTEMA];
```

Conferir:

```sql
EXECUTE AS LOGIN = N'AUTORIDADE NT\SISTEMA';
SELECT SUSER_SNAME(), DB_NAME(), HAS_DBACCESS('bdCartorio');
SELECT TOP 1 intChave FROM tbAvisoProtesto;
REVERT;
```

Depois: so repetir a importacao em `/protesto/importar-eoficio`.
Nao precisa ATUALIZAR o programa so por causa desta permissao.
