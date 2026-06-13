import time
import os
import io
import json
import base64
import ctypes
import requests
from PIL import ImageGrab, Image
from pynput.mouse import Controller as MouseController, Button as MouseButton
from pynput.keyboard import Controller as KeyController

from src.config import Action, DEFAULT_API_URL, DEFAULT_OCR_MODEL, DEFAULT_SYSTEM_PROMPT

# Estrutura para obter detalhes de monitores em Windows
class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", ctypes.c_long * 4),
        ("rcWork", ctypes.c_long * 4),
        ("dwFlags", ctypes.c_ulong)
    ]

def get_windows_monitors():
    """
    Retorna a lista de monitores com suas coordenadas físicas,
    escala de DPI e limites lógicos correspondentes.
    """
    monitors = []
    
    def monitor_enum_proc(hMonitor, hdcMonitor, lprcMonitor, dwData):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(info)):
            rect = list(info.rcMonitor)
            
            # Tenta obter a escala real de DPI do monitor
            try:
                dpi_x = ctypes.c_uint()
                dpi_y = ctypes.c_uint()
                # MDT_EFFECTIVE_DPI = 0
                ctypes.windll.shcore.GetDpiForMonitor(hMonitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
                scale_x = dpi_x.value / 96.0
                scale_y = dpi_y.value / 96.0
            except Exception:
                scale_x = 1.0
                scale_y = 1.0
                
            phys_w = rect[2] - rect[0]
            phys_h = rect[3] - rect[1]
            
            monitors.append({
                "hMonitor": hMonitor,
                "physical_rect": rect, # [left, top, right, bottom] físicos
                "scale_x": scale_x,
                "scale_y": scale_y,
                "logical_rect": [
                    int(rect[0] / scale_x),
                    int(rect[1] / scale_y),
                    int(rect[2] / scale_x),
                    int(rect[3] / scale_y)
                ],
                "logical_w": int(phys_w / scale_x),
                "logical_h": int(phys_h / scale_y)
            })
        return True

    MonitorEnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    callback = MonitorEnumProc(monitor_enum_proc)
    ctypes.windll.user32.EnumDisplayMonitors(None, None, callback, 0)
    
    # Ordena da esquerda para a direita
    monitors.sort(key=lambda m: m["physical_rect"][0])
    return monitors


class AutonomousVisualAgent:
    """Agente autônomo baseado em Visão Computacional (OCR / GPT-4o)."""
    
    def __init__(self, db_manager, chat_callback=None, status_callback=None, confirm_action_callback=None):
        """
        :param db_manager: DatabaseManager instanciado.
        :param chat_callback: Callback(sender, text) para escrever no chat do Painel.
        :param status_callback: Callback(text) para atualizar o status do agente na tela.
        :param confirm_action_callback: Callback(title, msg) para pedir confirmação de ação sensível.
        """
        self.db = db_manager
        self.chat_callback = chat_callback
        self.status_callback = status_callback
        self.confirm_action = confirm_action_callback
        
        self.mouse_ctrl = MouseController()
        self.key_ctrl = KeyController()

    def log_chat(self, sender, text):
        if self.chat_callback:
            self.chat_callback(sender, text)

    def log_status(self, text):
        if self.status_callback:
            self.status_callback(text)

    def run_sensitive_action(self, action):
        """Executa ações sensíveis como ler/escrever arquivos e rodar comandos no terminal."""
        act_type = action.get("type")
        
        # Valida callbacks
        if not self.confirm_action:
            return f"Erro ao executar '{act_type}': Mecanismo de confirmação não disponível."
            
        if act_type == "read_file":
            path = action.get("path")
            if not path:
                return "Erro ao ler arquivo: caminho vazio."
            abs_path = os.path.abspath(path)
            if not os.path.isfile(abs_path):
                return f"Erro: arquivo não encontrado ou é diretório: '{abs_path}'."
                
            if not self.confirm_action("Confirmar leitura de arquivo", f"O agente quer ler este arquivo:\n\n{abs_path}\n\nPermitir a leitura dos primeiros 2000 caracteres?"):
                return f"Ação negada pelo usuário: leitura do arquivo '{abs_path}'."
                
            try:
                with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(2000)
                return f"Sucesso ao ler arquivo '{abs_path}':\n{content}"
            except Exception as e:
                return f"Erro ao ler arquivo: {str(e)}"
                
        elif act_type == "write_file":
            path = action.get("path")
            content = action.get("content", "")
            if not path:
                return "Erro ao escrever arquivo: caminho vazio."
            abs_path = os.path.abspath(path)
            parent = os.path.dirname(abs_path)
            if not parent or not os.path.isdir(parent):
                return f"Erro: pasta destino não existe: '{parent}'."
                
            is_overwrite = os.path.exists(abs_path)
            title = "Confirmar escrita de arquivo"
            msg = f"O agente deseja {'SOBRESCREVER' if is_overwrite else 'CRIAR'} o seguinte arquivo:\n\n{abs_path}\n\nPermitir escrita?"
            
            if not self.confirm_action(title, msg):
                return f"Ação negada pelo usuário: escrita do arquivo '{abs_path}'."
                
            try:
                with open(abs_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return f"Sucesso ao gravar no arquivo '{abs_path}'."
            except Exception as e:
                return f"Erro ao gravar arquivo: {str(e)}"
                
        elif act_type == "run_command":
            cmd = (action.get("command") or "").strip()
            if not cmd:
                return "Erro ao executar comando: comando vazio."
            if len(cmd) > 500:
                return "Erro: comando excede 500 caracteres."
                
            if not self.confirm_action("Confirmar comando no terminal", f"O agente quer rodar este comando no terminal CMD:\n\n{cmd}\n\nPermitir execução?"):
                return f"Ação negada pelo usuário: execução do comando '{cmd}'."
                
            import subprocess
            try:
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10, encoding='utf-8', errors='ignore')
                return f"Comando '{cmd}' executado.\nCódigo de saída: {res.returncode}\nStdout:\n{res.stdout[:1500]}\nStderr:\n{res.stderr[:1500]}"
            except subprocess.TimeoutExpired:
                return f"Erro: O comando excedeu o limite de tempo de 10s."
            except Exception as e:
                return f"Erro ao rodar comando: {str(e)}"
                
        elif act_type == "open_url":
            url = (action.get("url") or "").strip()
            if not url:
                return "Erro ao abrir URL: URL vazia."
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                return f"Erro: URL inválida (deve conter http/https): '{url}'."
                
            if not self.confirm_action("Confirmar abertura de URL", f"O agente quer abrir a URL abaixo no seu navegador padrão:\n\n{url}\n\nPermitir?"):
                return f"Ação negada pelo usuário: abertura da URL '{url}'."
                
            import webbrowser
            try:
                webbrowser.open(url)
                return f"Sucesso ao abrir a URL '{url}' no navegador padrão."
            except Exception as e:
                return f"Erro ao abrir URL: {str(e)}"
                
        return f"Ação desconhecida '{act_type}'."

    def run_agent_loop(self, task_description, check_stop_flag_callback, get_chat_history_callback, file_content_1="", wait_for_user_callback=None):
        """
        Executa o loop autônomo de OCR/Visão.
        :param task_description: Instrução do que fazer.
        :param check_stop_flag_callback: Função que retorna True se a execução foi cancelada.
        :param get_chat_history_callback: Função que retorna o histórico recente em lista.
        :param file_content_1: Conteúdo opcional do arquivo 1.
        """
        api_key = self.db.get_setting("openai_api_key", "").strip()
        api_url = self.db.get_setting("agent_api_url", DEFAULT_API_URL).strip()
        model_name = self.db.get_setting("agent_ocr_model", DEFAULT_OCR_MODEL).strip()
        system_prompt = self.db.get_setting("agent_system_prompt", DEFAULT_SYSTEM_PROMPT).strip()
        
        if not api_key:
            self.log_chat("Sistema", "Erro: API Key não configurada nas Configurações Globais.")
            return

        # Carrega contexto das automações existentes
        recordings_list = self.db.get_all_recordings()
        recordings_context = "=== AUTOMACÕES/GRAVAÇÕES SALVAS NO SISTEMA ===\n"
        if recordings_list:
            for r in recordings_list:
                desc = r.get('description') or ''
                desc_str = f" - Descrição: {desc}" if desc else ""
                try:
                    steps = len(json.loads(r['clicks_data']))
                except Exception:
                    steps = 0
                recordings_context += f"- '{r['name']}' ({steps} passos){desc_str}\n"
        else:
            recordings_context += "Nenhuma gravação de automação salva ainda.\n"
        recordings_context += "=============================================\n\n"

        executed_actions_log = []
        action_feedback_list = []
        iteration = 0
        max_iterations = 12
        success = False

        self.log_chat("Agente", f"Iniciando tarefa autônoma [Visão/OCR]: '{task_description}'")

        try:
            while iteration < max_iterations:
                if check_stop_flag_callback():
                    break
                
                iteration += 1
                self.log_status(f"Status: Rodando iteração {iteration}/{max_iterations}...")

                # Compila retornos das ações anteriores
                feedback_str = "\n".join(action_feedback_list)
                action_feedback_list = [] # Limpa para a iteração atual
                feedback_block = ""
                if feedback_str:
                    feedback_block = f"=== RETORNO DAS AÇÕES DA ITERAÇÃO ANTERIOR ===\n{feedback_str}\n==============================================\n\n"

                # Obtém o histórico recente do chat
                chat_history = get_chat_history_callback()
                chat_context_str = "\n".join([f"[{m['role']}]: {m['content']}" for m in chat_history])

                # Mapeia monitores e captura imagens
                monitors = get_windows_monitors()
                if not monitors:
                    raise RuntimeError("Nenhum monitor localizado no sistema operacional Windows.")
                
                # Captura global
                screenshot_global = ImageGrab.grab(all_screens=True)
                
                # Para fins de coordenadas globais do Windows virtual
                try:
                    user32 = ctypes.windll.user32
                    x_virtual = user32.GetSystemMetrics(76)
                    y_virtual = user32.GetSystemMetrics(77)
                except Exception:
                    x_virtual, y_virtual = 0, 0
                
                images_payload = []
                monitors_desc = []
                
                for idx, mon in enumerate(monitors, start=1):
                    left, top, right, bottom = mon["physical_rect"]
                    
                    # Translada coordenadas globais para a tela capturada do PIL
                    c_left = max(0, min(screenshot_global.width, left - x_virtual))
                    c_top = max(0, min(screenshot_global.height, top - y_virtual))
                    c_right = max(0, min(screenshot_global.width, right - x_virtual))
                    c_bottom = max(0, min(screenshot_global.height, bottom - y_virtual))
                    
                    # Corta imagem do monitor
                    cropped = screenshot_global.crop((c_left, c_top, c_right, c_bottom))
                    
                    # --- PASSO CRÍTICO: REDIMENSIONA O PRINT FÍSICO PARA A RESOLUÇÃO LÓGICA DO MONITOR ---
                    logical_w, logical_h = mon["logical_w"], mon["logical_h"]
                    cropped_resized = cropped.resize((logical_w, logical_h), Image.Resampling.LANCZOS)
                    
                    # Converte para base64
                    buffer = io.BytesIO()
                    cropped_resized.save(buffer, format="JPEG", quality=80)
                    img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                    
                    images_payload.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_base64}"
                        }
                    })
                    
                    monitors_desc.append(
                        f"- Imagem {idx} (Tela {idx}): Resolução Lógica {logical_w}x{logical_h}. Escala DPI: {mon['scale_x']}x. Limites lógicos na área de trabalho: esquerda={mon['logical_rect'][0]}, topo={mon['logical_rect'][1]}."
                    )
                
                # Constrói o Prompt principal enriquecido para o LLM
                prompt = (
                    f"=== DIRETRIZES DO AGENTE ===\n{system_prompt}\n=============================\n\n"
                    f"{feedback_block}"
                    f"{recordings_context}"
                    f"Você é um robô de RPA autônomo inteligente rodando em loop. Seu objetivo final é: '{task_description}'.\n"
                    f"Temos os seguintes dados de um arquivo local relevante (se necessário):\n"
                    f"=== DADOS DO ARQUIVO ===\n{file_content_1}\n========================\n\n"
                    f"Monitores ativos no sistema operacional Windows:\n"
                    f"{chr(10).join(monitors_desc)}\n\n"
                    f"IMPORTANTE: Você deve informar em qual monitor deseja interagir usando a chave `\"monitor\"` (ex: 1 para Tela 1) e as coordenadas `\"x\"` e `\"y\"` em pixels LÓGICOS (ou seja, variando exatamente de 0 a largura-1 e 0 a altura-1 da Tela correspondente).\n"
                    f"Nós redimensionamos as imagens enviadas para a resolução lógica exata de cada tela. Portanto, escolha as coordenadas diretamente da imagem correspondente. Selecione sempre o CENTRO GEOMÉTRICO do botão ou campo que deseja interagir para evitar cliques inválidos.\n\n"
                    f"=== HISTÓRICO DE CHAT ===\n{chat_context_str}\n========================\n\n"
                    f"Lista de ações executadas nas iterações anteriores:\n"
                    f"{json.dumps(executed_actions_log, indent=2)}\n\n"
                    f"Analise o estado atual das imagens das telas e forneça o próximo conjunto de ações.\n"
                    f"Retorne OBRIGATORIAMENTE um objeto JSON puro. Não use blocos adicionais de formatação markdown. Respeite estritamente o formato:\n"
                    f"{{\n"
                    f"  \"completed\": false, // defina como true apenas quando verificar na tela que o objetivo final da tarefa foi totalmente alcançado\n"
                    f"  \"message\": \"Texto detalhado explicando o que você vê e qual ação está realizando agora\",\n"
                    f"  \"waiting_for_user\": false, // defina como true se precisar que o usuário responda ou faça algo no chat para continuar\n"
                    f"  \"actions\": [\n"
                    f"    // Lista ordenada de ações a serem executadas nesta iteração. Exemplos:\n"
                    f"    // {{\"type\": \"click\", \"monitor\": 1, \"x\": 450, \"y\": 320}},\n"
                    f"    // {{\"type\": \"type\", \"text\": \"texto a digitar\"}},\n"
                    f"    // {{\"type\": \"scroll\", \"dx\": 0, \"dy\": -100}},\n"
                    f"    // {{\"type\": \"wait\", \"duration\": 1.5}},\n"
                    f"    // {{\"type\": \"read_file\", \"path\": \"caminho_do_arquivo\"}}, // Pede permissão\n"
                    f"    // {{\"type\": \"write_file\", \"path\": \"caminho\", \"content\": \"conteudo\"}}, // Pede permissão\n"
                    f"    // {{\"type\": \"run_command\", \"command\": \"comando\"}}, // Pede permissão\n"
                    f"    // {{\"type\": \"open_url\", \"url\": \"https://exemplo.com\"}} // Pede permissão\n"
                    f"  ]\n"
                    f"}}"
                )

                content_list = [{"type": "text", "text": prompt}]
                content_list.extend(images_payload)

                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model_name,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "user", "content": content_list}
                    ],
                    "max_tokens": 1200,
                    "temperature": 0.1
                }

                # Executa requisição
                res = requests.post(f"{api_url}/chat/completions", headers=headers, json=payload, timeout=65)
                res.raise_for_status()
                res_data = res.json()
                ai_message = res_data['choices'][0]['message']['content'].strip()

                # Limpa marcações markdown extras se o LLM as enviou incorretamente
                if ai_message.startswith("```json"):
                    ai_message = ai_message[7:]
                if ai_message.endswith("```"):
                    ai_message = ai_message[:-3]
                ai_message = ai_message.strip()

                response_json = json.loads(ai_message)

                msg_text = response_json.get("message", "")
                if msg_text:
                    self.log_chat("Agente", msg_text)

                if response_json.get("completed", False):
                    success = True
                    self.log_chat("Agente", "Objetivo alcançado com sucesso!")
                    break

                if response_json.get("waiting_for_user", False):
                    self.log_status("Status: Aguardando resposta do usuário...")
                    if wait_for_user_callback:
                        user_msg = wait_for_user_callback()
                        if check_stop_flag_callback() or not user_msg:
                            break
                        executed_actions_log.append(f"Resposta do Usuário no Chat: \"{user_msg}\"")
                        continue
                    else:
                        break

                # Executa ações
                actions = response_json.get("actions", [])
                for act in actions:
                    if check_stop_flag_callback():
                        break

                    act_type = act.get("type")

                    # Ações de sistema sensíveis requerem confirmação do usuário
                    if act_type in ("read_file", "write_file", "run_command", "open_url"):
                        self.log_status(f"Status: Solicitando aprovação para {act_type}...")
                        feedback_msg = self.run_sensitive_action(act)
                        action_feedback_list.append(feedback_msg)
                        executed_actions_log.append(f"{act_type}: {feedback_msg.splitlines()[0] if feedback_msg else ''}")
                        continue

                    # Ações físicas
                    if act_type == "click":
                        try:
                            mon_idx = int(act.get("monitor", 1)) - 1
                            if mon_idx < 0 or mon_idx >= len(monitors):
                                mon_idx = 0
                            
                            target_mon = monitors[mon_idx]
                            logical_rect = target_mon["logical_rect"]
                            
                            rel_x = int(act.get("x", 0))
                            rel_y = int(act.get("y", 0))
                            
                            # Limita coordenadas aos limites lógicos daquele monitor
                            rel_x = max(0, min(target_mon["logical_w"] - 1, rel_x))
                            rel_y = max(0, min(target_mon["logical_h"] - 1, rel_y))
                            
                            # Translação: lógica do monitor + coordenada lógica relativa
                            # pynput no Windows lida diretamente com coordenadas lógicas globais
                            global_x = logical_rect[0] + rel_x
                            global_y = logical_rect[1] + rel_y
                        except Exception as e:
                            print(f"[AGENT ERROR] Falha ao traduzir coordenadas de clique: {e}")
                            global_x, global_y = 0, 0
                            mon_idx, rel_x, rel_y = 0, 0, 0
                        
                        self.mouse_ctrl.position = (global_x, global_y)
                        time.sleep(0.2)
                        self.mouse_ctrl.press(MouseButton.left)
                        time.sleep(0.05)
                        self.mouse_ctrl.release(MouseButton.left)
                        time.sleep(0.5)
                        executed_actions_log.append(f"Clique na Tela {mon_idx + 1} em ({rel_x}, {rel_y}) -> Global ({global_x}, {global_y})")

                    elif act_type == "type":
                        text = act.get("text", "")
                        self.key_ctrl.type(text)
                        time.sleep(0.2)
                        executed_actions_log.append(f"Digitou: \"{text}\"")

                    elif act_type == "scroll":
                        dx = int(act.get("dx", 0))
                        dy = int(act.get("dy", 0))
                        self.mouse_ctrl.scroll(dx, dy)
                        time.sleep(0.3)
                        executed_actions_log.append(f"Rolou scroll (dx={dx}, dy={dy})")

                    elif act_type == "wait":
                        dur = float(act.get("duration", 1.0))
                        time.sleep(dur)
                        executed_actions_log.append(f"Aguardou {dur}s")

                # Auto-Reflexão: Pequena pausa de transição e reavaliação na próxima iteração
                time.sleep(1.0)

            if not success and iteration >= max_iterations:
                self.log_chat("Agente", "Limite de iterações atingido sem sucesso total.")

        except Exception as e:
            self.log_chat("Sistema", f"Erro crítico na execução do agente: {str(e)}")
            print(f"[AGENT ERROR] Erro no loop de OCR: {e}")
