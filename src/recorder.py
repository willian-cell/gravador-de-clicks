import time
from pynput import mouse, keyboard
from src.config import Action

class ClickRecorder:
    """Orquestra a escuta global do teclado e mouse para gravação de RPA."""
    
    def __init__(self, on_action_added=None, is_ignored_area=None):
        """
        :param on_action_added: Callback executado toda vez que uma nova ação for inserida/atualizada.
        :param is_ignored_area: Callback(x, y) retornando True se a coordenada estiver na área a ignorar (ex: janela do app).
        """
        self.on_action_added = on_action_added
        self.is_ignored_area = is_ignored_area
        
        self.recording = False
        self.current_clicks = []
        self.mouse_listener = None
        self.keyboard_listener = None
        self.last_key_time = 0

    def start_recording(self):
        """Inicia os hooks de escuta globais."""
        if self.recording:
            return
        
        self.current_clicks = []
        self.recording = True
        self.last_key_time = time.time()
        
        # Hooks de pynput
        self.mouse_listener = mouse.Listener(on_click=self.on_click, on_scroll=self.on_scroll)
        self.mouse_listener.start()
        
        self.keyboard_listener = keyboard.Listener(on_press=self.on_key_press, on_release=self.on_key_release)
        self.keyboard_listener.start()

    def stop_recording(self):
        """Para todos os hooks ativos e retorna a lista de passos gravados."""
        self.recording = False
        
        if self.mouse_listener:
            try:
                self.mouse_listener.stop()
            except Exception:
                pass
            self.mouse_listener = None
            
        if self.keyboard_listener:
            try:
                self.keyboard_listener.stop()
            except Exception:
                pass
            self.keyboard_listener = None
            
        return self.current_clicks

    def on_click(self, x, y, button, pressed):
        """Trata cliques físicos de mouse."""
        if not self.recording or not pressed:
            return
            
        # Valida se o clique ocorreu dentro de uma área ignorada (como a janela do app)
        if self.is_ignored_area and self.is_ignored_area(x, y):
            return
            
        action = Action(
            Action.TYPE_CLICK,
            timestamp=time.time(),
            x=x,
            y=y,
            button=str(button)
        )
        self.current_clicks.append(action)
        
        if self.on_action_added:
            self.on_action_added(self.current_clicks)

    def on_scroll(self, x, y, dx, dy):
        """Trata rolagem de mouse e agrupa rolagens consecutivas em milissegundos."""
        if not self.recording:
            return
            
        if self.is_ignored_area and self.is_ignored_area(x, y):
            return
            
        now = time.time()
        can_merge = False
        
        # Agrupa se a última ação foi uma rolagem feita há menos de 0.5s
        if self.current_clicks:
            last_action = self.current_clicks[-1]
            if last_action.type == Action.TYPE_SCROLL:
                if now - last_action.timestamp < 0.5:
                    can_merge = True
                    
        if can_merge:
            last_action = self.current_clicks[-1]
            last_action.dx += dx
            last_action.dy += dy
            last_action.timestamp = now
        else:
            action = Action(
                Action.TYPE_SCROLL,
                timestamp=now,
                dx=dx,
                dy=dy
            )
            self.current_clicks.append(action)
            
        if self.on_action_added:
            self.on_action_added(self.current_clicks)

    def on_key_press(self, key):
        """Captura teclas do teclado e agrupa a digitação de forma inteligente."""
        if not self.recording:
            return
            
        try:
            char = None
            is_backspace = False
            
            # Identifica caracteres comuns e especiais de controle
            if hasattr(key, 'char') and key.char:
                char = key.char
            elif key == keyboard.Key.space:
                char = " "
            elif key == keyboard.Key.enter:
                char = "\n"
            elif key == keyboard.Key.backspace:
                is_backspace = True
            
            if char is not None or is_backspace:
                now = time.time()
                can_merge = False
                
                # Agrupa se a última ação foi digitação há menos de 3 segundos
                if self.current_clicks:
                    last_action = self.current_clicks[-1]
                    if last_action.type == Action.TYPE_TYPE:
                        if now - last_action.timestamp < 3.0:
                            can_merge = True
                
                if can_merge:
                    last_action = self.current_clicks[-1]
                    if is_backspace:
                        if last_action.text:
                            last_action.text = last_action.text[:-1]
                    else:
                        last_action.text += char
                    # Atualiza o timestamp para estender a janela de agrupamento
                    last_action.timestamp = now
                else:
                    if not is_backspace:
                        action = Action(
                            Action.TYPE_TYPE,
                            timestamp=now,
                            text=char
                        )
                        self.current_clicks.append(action)
                
                if self.on_action_added:
                    self.on_action_added(self.current_clicks)
        except Exception as e:
            print(f"[REC ERROR] Erro na captura de teclado: {e}")

    def on_key_release(self, key):
        """Evento de liberação de tecla (opcional para hooks futuros)."""
        pass
