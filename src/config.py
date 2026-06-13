import os
import time
from pathlib import Path

# Caminhos básicos do projeto
BASE_DIR = Path(__file__).parent.parent.resolve()
DEFAULT_DB_PATH = str(BASE_DIR / "recordings.db")
DEFAULT_LOGO_PATH = str(BASE_DIR / "wbo-tecnologia.png")
LOG_FILE_PATH = str(BASE_DIR / "app.log")

# Configurações de API e Modelos Padrão
DEFAULT_API_URL = "https://api.openai.com/v1"
DEFAULT_OCR_MODEL = "gpt-4o"
DEFAULT_SELENIUM_MODEL = "gpt-4o-mini"
DEFAULT_CONVERSATIONAL_MODEL = "gpt-4o-mini"

# Limites e Timeouts
MAX_LOG_SIZE = 1_000_000 # 1 MB
MAX_TEXT_FILE_READ = 2000 # Caracteres
SELENIUM_WAIT_TIMEOUT = 10 # Segundos
AGENT_MAX_ITERATIONS = 12

# Prompt de Sistema Padrão do Agente
DEFAULT_SYSTEM_PROMPT = (
    "Você é um agente de computador autônomo inteligente. A janela do aplicativo "
    "'Click Recorder com Agente IA' é a sua interface de controle. Se ela ou qualquer "
    "outra janela estiver cobrindo o aplicativo ou botão que você precisa interagir, "
    "você pode minimizá-la (clicando no botão '-' no canto superior direito) ou arrastá-la. "
    "Seja extremamente preciso em suas coordenadas."
)

class Action:
    """Representa uma ação gravada ou gerada pelo agente (clique, digitação, espera, etc)."""
    
    TYPE_CLICK = "CLICK"
    TYPE_TYPE = "TYPE"
    TYPE_WAIT = "WAIT"
    TYPE_READ_FILE = "READ_FILE"
    TYPE_SCROLL = "SCROLL"
    TYPE_AI = "IA"
    
    def __init__(self, action_type, **kwargs):
        self.type = action_type
        self.timestamp = kwargs.get('timestamp', time.time())
        self.x = kwargs.get('x', 0)
        self.y = kwargs.get('y', 0)
        self.button = kwargs.get('button', 'Button.left')
        self.text = kwargs.get('text', '')
        self.duration = kwargs.get('duration', 0.0)
        self.file_path = kwargs.get('file_path', '')
        self.read_mode = kwargs.get('read_mode', 'complete')
        self.file_selector = kwargs.get('file_selector', '')
        self.dx = kwargs.get('dx', 0)
        self.dy = kwargs.get('dy', 0)
        self.ai_task = kwargs.get('ai_task', '')
        self.ai_mode = kwargs.get('ai_mode', 'ocr')
        self.file_path_2 = kwargs.get('file_path_2', '')
        self.file_path_3 = kwargs.get('file_path_3', '')
        self.output_path = kwargs.get('output_path', '')
    
    def to_dict(self):
        """Converte ação para dicionário."""
        return {
            'type': self.type,
            'timestamp': self.timestamp,
            'x': self.x,
            'y': self.y,
            'button': self.button,
            'text': self.text,
            'duration': self.duration,
            'file_path': self.file_path,
            'read_mode': self.read_mode,
            'file_selector': self.file_selector,
            'dx': self.dx,
            'dy': self.dy,
            'ai_task': self.ai_task,
            'ai_mode': self.ai_mode,
            'file_path_2': self.file_path_2,
            'file_path_3': self.file_path_3,
            'output_path': self.output_path
        }
    
    @staticmethod
    def from_dict(data):
        """Cria ação a partir de dicionário."""
        action_type = data.get('type', Action.TYPE_CLICK)
        action = Action(action_type)
        action.timestamp = data.get('timestamp', time.time())
        action.x = data.get('x', 0)
        action.y = data.get('y', 0)
        action.button = data.get('button', 'Button.left')
        action.text = data.get('text', '')
        action.duration = data.get('duration', 0.0)
        action.file_path = data.get('file_path', '')
        action.read_mode = data.get('read_mode', 'complete')
        action.file_selector = data.get('file_selector', '')
        action.dx = data.get('dx', 0)
        action.dy = data.get('dy', 0)
        action.ai_task = data.get('ai_task', '')
        action.ai_mode = data.get('ai_mode', 'ocr')
        action.file_path_2 = data.get('file_path_2', '')
        action.file_path_3 = data.get('file_path_3', '')
        action.output_path = data.get('output_path', '')
        return action
    
    def __str__(self):
        """Representação amigável da ação."""
        if self.type == Action.TYPE_CLICK:
            btn_name = "Esquerdo" if "left" in self.button.lower() else "Direito" if "right" in self.button.lower() else "Médio"
            return f"Clique em ({self.x}, {self.y}) - Botão {btn_name}"
        elif self.type == Action.TYPE_TYPE:
            text_preview = self.text[:30] + "..." if len(self.text) > 30 else self.text
            text_preview = text_preview.replace("\n", "\\n")
            return f"Digitar: \"{text_preview}\""
        elif self.type == Action.TYPE_WAIT:
            return f"Aguardar {self.duration}s"
        elif self.type == Action.TYPE_READ_FILE:
            mode_desc = {
                'complete': 'Conteúdo Completo',
                'line': f'Linha {self.file_selector}',
                'json': f'Chave JSON: {self.file_selector}',
                'csv': f'CSV: {self.file_selector}'
            }.get(self.read_mode, self.read_mode)
            filename = os.path.basename(self.file_path) if self.file_path else "Não selecionado"
            return f"Ler arquivo ({mode_desc}): {filename}"
        elif self.type == Action.TYPE_SCROLL:
            direction = "baixo" if self.dy < 0 else "cima"
            return f"Rolar mouse: {direction} (dy: {self.dy}, dx: {self.dx})"
        elif self.type == Action.TYPE_AI:
            mode_desc = {
                'ocr': 'Visão/OCR (Desktop)',
                'selenium': 'Selenium Web',
                'excel_merge': 'Mesclar Arquivos'
            }.get(self.ai_mode, self.ai_mode)
            task_desc = self.ai_task[:25] + "..." if len(self.ai_task) > 25 else self.ai_task
            return f"IA ({mode_desc}): {task_desc or 'Sem instrução'}"
        return "Ação desconhecida"
