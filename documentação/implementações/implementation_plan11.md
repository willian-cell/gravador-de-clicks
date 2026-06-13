# Plano de Implementação: Recriação Completa e Aprimoramento do Click Recorder RPA

Este documento descreve a análise do atual funcionamento do sistema, identifica os pontos fracos e possíveis falhas e propõe um plano detalhado para recriar o sistema em uma arquitetura moderna, modular, robusta e com recursos avançados de auto-suficiência e precisão cirúrgica.

---

## Análise de Falhas e Oportunidades de Melhoria

1. **Monolito de Código (`app.py`)**: Atualmente, todo o sistema (banco de dados, gravação pynput, controle Selenium, consolidação Excel, execução de IA e interface gráfica Tkinter) está espremido em um único arquivo de 2.730 linhas. Isso torna a depuração extremamente difícil, impede testes automatizados e dificulta a evolução do sistema.
2. **Incompatibilidade Crítica de DPI (Escala do Windows)**: O robô de visão (`ocr`) usa as coordenadas da tela lógica do Windows, mas a captura de tela (`ImageGrab.grab`) retorna pixels físicos. Quando o Windows está com escala ativa (ex: 125%, 150%, 200%), os cliques retornados pelo LLM falham miseravelmente devido a esse descompasso.
3. **Interface Gráfica (UI/UX) Muito Simples**: A interface atual usa elementos padrão e datados do Tkinter. Não há suporte a um tema dark moderno de alta qualidade, cartões visuais para os passos gravados, badges dinâmicos de status, nem um painel de chat com balões de mensagem formatados.
4. **Sem Auto-Suficiência ou Auto-Correção**: Se o agente cometer um pequeno erro de clique ou se a página web demorar a carregar, o agente falha. Não há um ciclo de reflexão pós-ação para validar se o clique surtiu efeito, se uma janela abriu ou se é necessário tentar outra estratégia.
5. **Selenium Web Cego**: No modo Selenium, o agente recebe apenas uma lista textual de elementos interativos e fica "cego". Ele não tem acesso ao print do navegador para validar visualmente o layout, e se um clique disparado via Selenium falhar (ex: elemento interceptado), ele não tenta executar via JavaScript (JS fallback).
6. **Thread Safety do Tkinter**: O loop do agente executa em uma thread separada e atualiza widgets do Tkinter diretamente (como o Chat e labels de status). Isso pode causar travamentos aleatórios no Windows (deadlocks do Tkinter). Toda alteração de GUI vinda de outras threads deve ser enfileirada e atualizada na thread principal.
7. **Configurações Rígidas de Modelo e API**: O sistema força o uso exclusivo da OpenAI (`gpt-4o`/`gpt-4o-mini`). Não há flexibilidade para alterar a URL base da API ou escolher outros modelos (como Gemini, Claude, DeepSeek ou modelos locais rodando no Ollama).

---

## Proposta de Nova Arquitetura

Dividiremos o monolito atual em uma estrutura modular organizada dentro da pasta `src/`:

```
c:\Users\willi\Documents\danilo\
├── app.py                     # Ponto de entrada do aplicativo (chama src.gui)
├── requirements.txt           # Dependências do projeto (pynput, pillow, requests, selenium, openpyxl)
├── wbo-tecnologia.png         # Logo da empresa
├── run.bat                    # Script batch para rodar no ambiente virtual (.venv)
└── src/
    ├── __init__.py
    ├── config.py              # Configurações globais, constantes e mapeamento de chaves
    ├── database.py            # SQLite Manager robusto (com WAL mode, backups automáticos e migrações limpas)
    ├── recorder.py            # Captura inteligente de mouse/teclado via pynput com agrupamento de teclas
    ├── playback.py            # Executor de macros gravadas com controle de velocidade (Turbo, Padrão, Seguro)
    ├── agent_ocr.py           # Agente Autônomo Visual (corrige DPI redimensionando imagens e mapeando coordenadas 1:1)
    ├── agent_selenium.py      # Agente Selenium Multimodal (envia HTML + Print da página e implementa JS-click fallback)
    ├── agent_merge.py         # Módulo de mesclagem e formatação profissional de planilhas Excel via openpyxl
    └── gui.py                 # Interface Gráfica moderna de alta fidelidade (Dark Mode, balões de chat, badges e logs)
```

---

## Detalhes das Melhorias Propostas

### 1. Interface Gráfica Moderna e Premium (`src/gui.py`)
* **Design System Customizado**: Criaremos um visual moderno no Tkinter utilizando paletas de cores escuras premium (Slate Dark `#1E1E2E`, Teal `#00B4D8`, Emerald `#2EC4B6` e Coral `#FF5A5F`).
* **Balões de Conversa**: O chat exibirá balões de mensagens visualmente separados (usuário alinhado à direita em azul/ciano, agente à esquerda em cinza escuro, logs do sistema formatados no centro).
* **Badges de Status Dinâmicos**: Indicadores coloridos no topo da tela mostrando o estado atual (`[GRAVANDO]`, `[EXECUTANDO]`, `[IA PENSANDO]`, `[INATIVO]`).
* **Seletor de Velocidade (Turbo RPA)**: Controle de playback para executar passos gravados instantaneamente (sem pausas humanas) ou respeitando os tempos reais.
* **Seletor de Provedor e Modelos**: Permite configurar qualquer Endpoint compatível com OpenAI (possibilitando usar chaves da Gemini, DeepSeek, Local LLMs, etc.) e definir o modelo de preferência.
* **Thread-Safe Queue**: Todas as atualizações visuais das threads de gravação e do agente serão enviadas a uma fila thread-safe (`queue.Queue`) e processadas na thread principal através de um loop periódico (`root.after`).

### 2. Resolução Definitiva de DPI e Múltiplos Monitores (`src/agent_ocr.py`)
* Obteremos as dimensões lógicas dos monitores via Windows API.
* Faremos a captura com `ImageGrab.grab(all_screens=True)` em pixels físicos.
* **Redimensionamento Cirúrgico**: Para cada monitor, recortaremos o print físico e faremos o redimensionamento exato (`LANCZOS`) para a sua resolução lógica antes de enviar para o LLM.
* Dessa forma, se a tela lógica do monitor é `1920x1080` mas o print físico é `2880x1620` (150% de DPI), a imagem enviada ao LLM terá exatamente `1920x1080`. Qualquer coordenada `(x, y)` retornada pelo LLM corresponderá 1:1 ao pixel lógico usado pelo movimentador de mouse do Windows, zerando erros de mira!

### 3. Agente com Auto-Suficiência e Reflexão (`src/playback.py` e `src/agent_ocr.py`)
* **Ciclo de Verificação Pós-Ação**: Após enviar cliques ou textos, o agente aguardará a transição da tela, capturará um novo print e analisará: *"A ação anterior surtiu o efeito desejado? A janela abriu? O campo foi preenchido?"*
* **Auto-Correção**: Caso detecte que o clique falhou (ex: clicou levemente fora do botão ou a página não carregou), o agente tentará clicar em uma coordenada ligeiramente ajustada ou aguardará mais tempo.
* **Recuperação de Popups**: Se surgir um banner, anúncio ou popup inesperado cobrindo o alvo, o agente tentará localizar o botão de fechar (`X`) ou pressionar a tecla `Esc` para remover a obstrução antes de prosseguir com a tarefa original.

### 4. Selenium Web Híbrido e Multimodal (`src/agent_selenium.py`)
* O agente receberá o código HTML estruturado da página web **E** uma captura de tela do navegador.
* **JS Click Fallback**: Se o comando de clique padrão do Selenium falhar por bloqueio de outro elemento ou incompatibilidade, o agente disparará um script JavaScript (`arguments[0].click()`) diretamente no console do navegador para forçar a ação.
* **Auto-Wait**: Uso de waits explícitos no driver para que os elementos carreguem completamente antes de tentar interagir.

### 5. Banco de Dados SQLite Resiliente (`src/database.py`)
* Configuração do banco em modo **WAL (Write-Ahead Logging)** para permitir leituras e escritas simultâneas de threads diferentes sem bloqueios.
* Criação de uma cópia de segurança automática (`recordings.db.bak`) ao iniciar o app para prevenir corrupção de dados.
* Verificação estrutural do schema no startup, garantindo auto-migração se novas colunas forem necessárias no futuro.

---

## Plano de Alterações Propostas

### [NEW] [config.py](file:///c:/Users/willi/Documents/danilo/src/config.py)
Contém todas as constantes do sistema, mapeamentos e configurações que o usuário salvar (carregadas dinamicamente).

### [NEW] [database.py](file:///c:/Users/willi/Documents/danilo/src/database.py)
Classe `DatabaseManager` atualizada com transações seguras, WAL mode, backups automáticos e sanitização de dados.

### [NEW] [recorder.py](file:///c:/Users/willi/Documents/danilo/src/recorder.py)
Mapeamento de eventos de teclado/mouse do `pynput` em objetos `Action`, agrupamento inteligente de strings e hotkeys.

### [NEW] [playback.py](file:///c:/Users/willi/Documents/danilo/src/playback.py)
Lógica de execução das gravações, tratamento de delays dinâmicos (modo Turbo/Real/Seguro) e interrupção imediata controlada por flags.

### [NEW] [agent_ocr.py](file:///c:/Users/willi/Documents/danilo/src/agent_ocr.py)
Ciclo de vida do agente autônomo visual, cálculo preciso de escala de DPI e algoritmos de reflexão pós-ação.

### [NEW] [agent_selenium.py](file:///c:/Users/willi/Documents/danilo/src/agent_selenium.py)
Robô Selenium aprimorado com visão multimodal (Screenshot + HTML) e JS Click Fallback.

### [NEW] [agent_merge.py](file:///c:/Users/willi/Documents/danilo/src/agent_merge.py)
Módulo isolado de processamento de mesclagem de arquivos estruturados e geração de relatórios formatados em Excel.

### [NEW] [gui.py](file:///c:/Users/willi/Documents/danilo/src/gui.py)
Interface gráfica totalmente reestilizada com tema escuro elegante, widgets thread-safe, listagem animada e chat premium.

### [MODIFY] [app.py](file:///c:/Users/willi/Documents/danilo/app.py)
Será esvaziado e passará a ser apenas a ponte de carregamento inicial:
```python
import sys
import os

# Garante que a pasta src está no path de importação
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    import tkinter as tk
    from src.gui import ClickRecorderApp
    
    root = tk.Tk()
    app = ClickRecorderApp(root)
    root.mainloop()
```

---

## Perguntas em Aberto para o Usuário

> [!IMPORTANT]
> **Por favor, revise os itens abaixo no plano antes de dar sua aprovação:**
>
> 1. **Múltiplos Provedores de IA**: Você gostaria de usar a API da Gemini ou outra API (ex: DeepSeek) além da OpenAI? Nossa solução configurável permite usar qualquer provedor compatível com OpenAI (incluindo Gemini via endpoint de compatibilidade). Gostaria de manter este design genérico e flexível?
> 2. **Tema Visual Escuro (Dark Mode)**: O novo design visual usará um estilo Dark Slate moderno por padrão. Deseja que adicionemos um botão de alternar entre Modo Claro (Light Mode) e Modo Escuro (Dark Mode) na interface gráfica?
> 3. **Instalação de Dependências**: O projeto atualmente utiliza `pillow`, `pynput`, `requests`, `selenium` e `openpyxl`. Nenhuma biblioteca adicional pesada (como PyQt) será necessária, mantendo o ambiente limpo. Está de acordo?

---

## Plano de Verificação

### Testes Manuais de Execução
1. **Calibração de Escala**: Executar um comando visual em telas com escala de DPI ativa (ex: 125% ou 150%) para confirmar que a mira do ponteiro atinge exatamente o alvo.
2. **Auto-Correção**: Provocar um popup ou atrasar o carregamento de uma página para testar se o agente detecta e recupera a execução automaticamente.
3. **Migração do Banco de Dados**: Rodar o novo sistema sobre o banco `recordings.db` atual para garantir que os dados antigos do usuário não sejam perdidos e as novas tabelas/colunas sejam migradas com segurança.
4. **Isolamento de Erros de Thread**: Iniciar e parar gravações/playbacks sucessivamente para verificar se a interface permanece 100% responsiva sem travar.
