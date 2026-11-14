## Clear Windows 0.1.0 — prévia

Primeira distribuição Windows x64 da aplicação desktop Clear Windows.

### Downloads

- **ClearWindows-0.1.0-Setup-x64.exe**: instalador por usuário, com atalhos e desinstalador. Não requer Python instalado.
- **ClearWindows-0.1.0-Portable-x64.zip**: extraia a pasta inteira e abra `ClearWindows.exe`. Mantenha a pasta `_internal` junto ao executável.
- **SHA256SUMS.txt**: hashes SHA-256 para verificar os downloads.

Inclui Fresh Windows, catálogo controlado de aplicativos opcionais, fila de alterações com confirmação, backups do Registro e histórico, monitoramento de recursos e análise de armazenamento com treemap.

Os arquivos não possuem assinatura digital. Esta é uma prévia de desenvolvimento: funções que modificam o Windows ainda precisam da validação destrutiva em VM descrita na documentação. Os testes de empacotamento verificam abertura da interface, navegação, varredura real de arquivos, instalação e desinstalação; não aplicam otimizações.

Desinstalar o programa preserva o histórico e os backups locais. Pontos de restauração não substituem backup de arquivos pessoais. Consulte `README.md`, `docs/STATUS.md` e `docs/WINDOWS-VALIDATION.md` incluídos nos pacotes.
