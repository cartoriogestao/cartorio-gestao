# ROTEIRO DA 3.6.68 — nova organização visual

## Objetivo

Reorganizar a navegação de um sistema com muitos módulos sem alterar rotas,
permissões ou regras de negócio. A interface passa a usar uma linguagem visual
clara inspirada em aplicativos nativos do macOS e iOS.

## O que muda

- navegação lateral dividida em Atalhos, Atribuições, Operação e Gestão;
- busca instantânea por módulo ou ferramenta;
- um módulo expandido por vez, mantendo o módulo da página aberto;
- tela atual marcada automaticamente;
- menu recolhível em celular e tablet;
- tipografia nativa, superfícies claras, cartões arredondados e controles mais
  legíveis;
- cores das atribuições preservadas como identificação discreta.

## Compatibilidade e segurança

- nenhuma rota ou permissão foi removida;
- os links e os módulos continuam funcionando sem JavaScript;
- a busca e o menu móvel são melhorias progressivas;
- o pacote usa o canal `.cgu`, com backup e rollback automáticos.

## Validação

- testes direcionados de menu, cores, cabeçalho, habilitação e telas afetadas;
- verificação sintática do JavaScript;
- conferência estrutural de oito módulos e oito marcas de cor.
