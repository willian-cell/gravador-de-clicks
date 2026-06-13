import time
import os
import json
import csv
from pynput import mouse, keyboard
from src.config import Action

def get_file_content_to_type(file_path, read_mode, selector):
    """
    Lê um arquivo local do disco e extrai o conteúdo a ser digitado
    com base no modo de leitura (read_mode) e no seletor (selector).
    """
    if not file_path:
        raise ValueError("Caminho do arquivo não especificado.")
        
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")
        
    # Lê todo o conteúdo como string
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        
    if read_mode == 'complete':
        return content
        
    elif read_mode == 'line':
        lines = content.splitlines()
        try:
            line_idx = int(selector) - 1 # 1-indexado
            if 0 <= line_idx < len(lines):
                return lines[line_idx]
            else:
                raise IndexError(f"Linha {selector} fora do limite (total de linhas: {len(lines)})")
        except ValueError:
            raise ValueError("O seletor para modo 'Linha' deve ser um número inteiro.")
            
    elif read_mode == 'json':
        try:
            data = json.loads(content)
            # Suporta chaves aninhadas separadas por ponto, ex: usuario.nome
            keys = selector.split('.')
            val = data
            for k in keys:
                if isinstance(val, dict):
                    val = val[k]
                elif isinstance(val, list):
                    val = val[int(k)]
                else:
                    raise KeyError(f"Chave '{k}' não encontrada")
            return str(val)
        except Exception as e:
            raise ValueError(f"Erro ao obter chave JSON '{selector}': {e}")
            
    elif read_mode == 'csv':
        try:
            lines = content.splitlines()
            reader = csv.reader(lines)
            rows = list(reader)
            if not rows:
                return ""
            
            # Formato de seletor 1: "linha,coluna" (ex: "1,2")
            parts = selector.split(',')
            if len(parts) == 2:
                try:
                    row_idx = int(parts[0].strip()) - 1
                    col_idx = int(parts[1].strip()) - 1
                    if 0 <= row_idx < len(rows) and 0 <= col_idx < len(rows[row_idx]):
                        return rows[row_idx][col_idx]
                    else:
                        raise IndexError(f"Coordenadas CSV {selector} fora dos limites.")
                except ValueError:
                    pass # Tenta o próximo padrão se não for numérico
            
            # Formato de seletor 2: Nome da coluna (busca a coluna na linha 2)
            col_selector = selector.strip()
            # Tenta ver se é um índice numérico simples de coluna
            if col_selector.isdigit():
                col_idx = int(col_selector) - 1
                if len(rows) > 0 and 0 <= col_idx < len(rows[0]):
                    return rows[0][col_idx]
            else:
                # Trata a primeira linha como cabeçalho
                header = rows[0]
                if col_selector in header:
                    col_idx = header.index(col_selector)
                    if len(rows) > 1:
                        return rows[1][col_idx] # primeira linha de dados
                    
            raise ValueError(f"Formato do seletor CSV inválido ou não encontrado: '{selector}'. Use 'linha,coluna' (ex: 1,2) ou nome da coluna.")
        except Exception as e:
            raise ValueError(f"Erro ao parsear CSV: {e}")
            
    return content


class MacroPlayer:
    """Motor de execução de automações e playback de cliques."""
    
    def __init__(self, on_status_update=None, run_agent_callback=None):
        """
        :param on_status_update: Callback(msg) para atualizar o status na interface visual.
        :param run_agent_callback: Callback para rodar os passos de IA (OCR/Selenium).
        """
        self.on_status_update = on_status_update
        self.run_agent_callback = run_agent_callback
        self.playing = False
        
        # Controladores físicos
        self.mouse_controller = mouse.Controller()
        self.keyboard_controller = keyboard.Controller()

    def stop_playback(self):
        """Solicita a parada imediata da execução."""
        if self.playing:
            self.playing = False
            self.update_status("Parada solicitada pelo usuário...")

    def update_status(self, msg):
        """Envia status atualizado se houver callback cadastrado."""
        if self.on_status_update:
            self.on_status_update(msg)

    def sleep_interruptible(self, duration):
        """Dorme em pequenos intervalos para responder rapidamente à solicitação de parada."""
        steps = int(duration / 0.05)
        for _ in range(steps):
            if not self.playing:
                return
            time.sleep(0.05)
        remainder = duration % 0.05
        if self.playing and remainder > 0:
            time.sleep(remainder)

    def play(self, clicks_list, speed_mode="Real", max_wait_delay=10.0):
        """
        Executa a reprodução dos cliques em thread secundária.
        :param clicks_list: Lista de ações (dicts ou Action objects).
        :param speed_mode: Modo de velocidade: "Real", "Turbo", "Safe".
        :param max_wait_delay: Atraso máximo entre ações em segundos (no modo Real).
        """
        if not clicks_list:
            self.update_status("Nenhuma ação para reproduzir.")
            return

        self.playing = True
        
        # Converte dicionários para Action objects se necessário
        actions = []
        for item in clicks_list:
            if isinstance(item, dict):
                actions.append(Action.from_dict(item))
            else:
                actions.append(item)
        
        try:
            self.update_status(f"Iniciando reprodução: 0/{len(actions)} passos...")
            time.sleep(1.0)
            
            last_timestamp = actions[0].timestamp if actions else time.time()
            
            for idx, action in enumerate(actions):
                if not self.playing:
                    break
                
                # Executa o delay de acordo com o modo de velocidade selecionado
                if idx > 0 and speed_mode != "Turbo":
                    if speed_mode == "Safe":
                        # No modo seguro, atraso fixo mínimo de 1.0s para dar tempo à máquina
                        delay = max(1.0, action.timestamp - last_timestamp)
                        # Capa em no máximo o dobro do delay padrão ou no limite global
                        delay = min(delay, max_wait_delay)
                    else:
                        # Modo Real (comprimi delays entre 0.35s e 0.5s para 0.5s)
                        delay = action.timestamp - last_timestamp
                        if 0.35 <= delay < 0.5:
                            delay = 0.5
                        elif delay > max_wait_delay:
                            delay = max_wait_delay
                    
                    if delay > 0:
                        self.sleep_interruptible(delay)
                elif idx > 0 and speed_mode == "Turbo":
                    # Turbo mode: delay mínimo fixo
                    self.sleep_interruptible(0.05)
                
                if not self.playing:
                    break
                
                last_timestamp = action.timestamp
                self.update_status(f"Executando passo {idx + 1}/{len(actions)}: {str(action)}...")
                
                # Execução de cada tipo de ação
                if action.type == Action.TYPE_CLICK:
                    button_str = action.button.lower()
                    if "right" in button_str:
                        button = mouse.Button.right
                    elif "middle" in button_str:
                        button = mouse.Button.middle
                    else:
                        button = mouse.Button.left
                    
                    # Move o mouse e clica
                    self.mouse_controller.position = (action.x, action.y)
                    time.sleep(0.05)
                    self.mouse_controller.press(button)
                    time.sleep(0.05)
                    self.mouse_controller.release(button)
                    
                elif action.type == Action.TYPE_TYPE:
                    self.keyboard_controller.type(action.text)
                    
                elif action.type == Action.TYPE_WAIT:
                    self.sleep_interruptible(action.duration)
                    
                elif action.type == Action.TYPE_READ_FILE:
                    try:
                        text_to_type = get_file_content_to_type(
                            action.file_path,
                            action.read_mode,
                            action.file_selector
                        )
                        self.keyboard_controller.type(text_to_type)
                    except Exception as err:
                        self.update_status(f"Erro ao ler arquivo: {str(err)}")
                        raise err
                        
                elif action.type == Action.TYPE_SCROLL:
                    self.mouse_controller.scroll(action.dx, action.dy)
                    
                elif action.type == Action.TYPE_AI:
                    if self.run_agent_callback:
                        # Roda o agente autônomo na thread atual
                        self.run_agent_callback(
                            action.ai_task,
                            ai_mode=action.ai_mode,
                            file_path=action.file_path,
                            file_path_2=action.file_path_2,
                            file_path_3=action.file_path_3,
                            output_path=action.output_path
                        )
                    else:
                        self.update_status("Erro: Callback do agente de IA não configurado.")
                
            if self.playing:
                self.update_status(f"Automação executada com sucesso: {len(actions)} passos processados.")
            else:
                self.update_status("Execução interrompida.")
                
        except Exception as e:
            self.update_status(f"Erro na execução: {e}")
            print(f"[PLAYBACK ERROR] Erro durante playback de macro: {e}")
        finally:
            self.playing = False
