# Sistema de Análise Inteligente de Vídeos

## Objetivo
Desenvolver uma aplicação capaz de processar automaticamente vídeos MP4, detectar objetos através de IA, extrair evidências visuais, gerar clipes dos eventos encontrados e produzir relatórios completos para auditoria e investigação.

## Público-Alvo
- Investigadores
- Empresas de monitoramento
- Auditorias internas
- Segurança patrimonial
- Análise forense
- Operações de logística

## Objetivos do MVP
- Processar múltiplos vídeos MP4
- Detectar pessoas
- Detectar veículos
- Detectar mochilas
- Gerar capturas (snapshots)
- Extrair clipes dos eventos
- Gerar supercuts
- Armazenar eventos em banco SQLite
- Disponibilizar interface web simples
- Exportar relatórios PDF, CSV e JSON

## Classes de Detecção
### Obrigatórias
- person
- car
- motorcycle
- truck
- bus
- bicycle
- backpack

### Futuras
- suitcase
- cellphone
- animal
- custom classes
