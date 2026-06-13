import time
import io
import json
import base64
import requests
from PIL import Image
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, NoSuchElementException

from src.config import Action, DEFAULT_API_URL, DEFAULT_SELENIUM_MODEL, DEFAULT_SYSTEM_PROMPT

class AutonomousSeleniumAgent:
    """Agente autônomo baseado em Selenium com visão híbrida (Visual + DOM)."""
    
    def __init__(self, db_manager, driver, chat_callback=None, status_callback=None, confirm_action_callback=None):
        """
        :param db_manager: DatabaseManager instanciado.
        :param driver: Webdriver Selenium ativo.
        :param chat_callback: Callback(sender, text) para escrever no chat do Painel.
        :param status_callback: Callback(text) para atualizar o status do agente na tela.
        :param confirm_action_callback: Callback(title, msg) para pedir confirmação de ação sensível.
        """
        self.db = db_manager
        self.driver = driver
        self.chat_callback = chat_callback
        self.status_callback = status_callback
        self.confirm_action = confirm_action_callback

    def log_chat(self, sender, text):
        if self.chat_callback:
            self.chat_callback(sender, text)

    def log_status(self, text):
        if self.status_callback:
            self.status_callback(text)

    def run_sensitive_action(self, action):
        """Executa ações de sistema com consentimento do usuário (copiado do agente visual)."""
        act_type = action.get("type")
        if not self.confirm_action:
            return f"Erro ao executar '{act_type}': Mecanismo de confirmação indisponível."
            
        if act_type == "read_file":
            path = action.get("path")
            if not path:
                return "Erro ao ler arquivo: caminho vazio."
            abs_path = os.path.abspath(path)
            if not os.path.isfile(abs_path):
                return f"Erro: arquivo não encontrado: '{abs_path}'."
            if not self.confirm_action("Confirmar leitura de arquivo", f"O agente quer ler este arquivo:\n\n{abs_path}\n\nPermitir?"):
                return f"Ação negada pelo usuário: leitura do arquivo '{abs_path}'."
            try:
                with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(2000)
                return f"Sucesso ao ler arquivo '{abs_path}':\n{content}"
            except Exception as e:
                return f"Erro: {str(e)}"
                
        elif act_type == "write_file":
            path = action.get("path")
            content = action.get("content", "")
            if not path:
                return "Erro ao escrever arquivo: caminho vazio."
            abs_path = os.path.abspath(path)
            if not self.confirm_action("Confirmar escrita de arquivo", f"O agente quer gravar este arquivo:\n\n{abs_path}\n\nPermitir?"):
                return f"Ação negada pelo usuário: escrita do arquivo '{abs_path}'."
            try:
                with open(abs_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return f"Sucesso ao gravar no arquivo '{abs_path}'."
            except Exception as e:
                return f"Erro: {str(e)}"
                
        elif act_type == "run_command":
            cmd = (action.get("command") or "").strip()
            if not cmd:
                return "Erro ao executar comando: comando vazio."
            if not self.confirm_action("Confirmar comando no terminal", f"O agente quer rodar este comando:\n\n{cmd}\n\nPermitir?"):
                return f"Ação negada pelo usuário: execução do comando '{cmd}'."
            import subprocess
            try:
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10, encoding='utf-8', errors='ignore')
                return f"Comando executado. Código: {res.returncode}\nStdout:\n{res.stdout[:1500]}\nStderr:\n{res.stderr[:1500]}"
            except subprocess.TimeoutExpired:
                return "Erro: comando excedeu tempo limite."
            except Exception as e:
                return f"Erro: {str(e)}"
                
        elif act_type == "open_url":
            url = (action.get("url") or "").strip()
            if not url:
                return "Erro ao abrir URL: URL vazia."
            if not self.confirm_action("Confirmar abertura de URL", f"O agente quer abrir a URL abaixo:\n\n{url}\n\nPermitir?"):
                return f"Ação negada pelo usuário: abertura da URL '{url}'."
            import webbrowser
            try:
                webbrowser.open(url)
                return f"Sucesso ao abrir '{url}' no navegador."
            except Exception as e:
                return f"Erro: {str(e)}"
                
        return f"Ação de sistema desconhecida '{act_type}'."

    def execute_dom_action(self, action):
        """Executa ações direcionadas a elementos do DOM do Selenium com tratamento e fallback."""
        act_type = action.get("type")
        by_type = action.get("by")
        val = action.get("value")
        
        # Encontra o elemento
        element = None
        try:
            if by_type == "id":
                element = self.driver.find_element(By.ID, val)
            elif by_type == "name":
                element = self.driver.find_element(By.NAME, val)
            elif by_type == "placeholder":
                element = self.driver.find_element(By.XPATH, f"//input[@placeholder='{val}'] | //textarea[@placeholder='{val}']")
            elif by_type == "xpath":
                element = self.driver.find_element(By.XPATH, val)
            elif by_type == "css":
                element = self.driver.find_element(By.CSS_SELECTOR, val)
        except Exception:
            return f"Elemento '{val}' (por {by_type}) não localizado na página atual."

        if not element:
            return f"Elemento '{val}' não encontrado."

        try:
            # Rola para o elemento ficar visível
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.2)
            
            if act_type == "click":
                try:
                    # Clique padrão Selenium
                    element.click()
                except Exception:
                    # FALLBACK: Clique via Javascript direto no DOM (evita erro de cobertura/interceptação)
                    self.driver.execute_script("arguments[0].click();", element)
                return f"Clique executado no elemento '{val}'."
                
            elif act_type == "type":
                text = action.get("text", "")
                try:
                    element.clear()
                except Exception:
                    pass
                element.send_keys(text)
                return f"Digitou '{text}' no elemento '{val}'."
                
            elif act_type == "wait":
                dur = float(action.get("duration", 1.0))
                time.sleep(dur)
                return f"Aguardou {dur}s."
                
        except Exception as e:
            return f"Erro ao interagir com o elemento '{val}': {str(e)}"

        return f"Ação de DOM desconhecida: {act_type}"

    def run_agent_loop(self, task_description, check_stop_flag_callback, get_chat_history_callback, file_content_1="", wait_for_user_callback=None):
        """
        Executa o loop autônomo do Selenium.
        :param task_description: Objetivo do agente.
        :param check_stop_flag_callback: Retorna True se deve parar.
        :param get_chat_history_callback: Retorna histórico do chat.
        :param file_content_1: Dados de arquivo opcional.
        """
        api_key = self.db.get_setting("openai_api_key", "").strip()
        api_url = self.db.get_setting("agent_api_url", DEFAULT_API_URL).strip()
        model_name = self.db.get_setting("agent_selenium_model", DEFAULT_SELENIUM_MODEL).strip()
        system_prompt = self.db.get_setting("agent_system_prompt", DEFAULT_SYSTEM_PROMPT).strip()

        if not api_key:
            self.log_chat("Sistema", "Erro: API Key não configurada nas Configurações Globais.")
            return

        executed_actions_log = []
        action_feedback_list = []
        iteration = 0
        max_iterations = 12
        success = False

        self.log_chat("Agente", f"Iniciando tarefa autônoma [Selenium Web]: '{task_description}'")

        try:
            while iteration < max_iterations:
                if check_stop_flag_callback():
                    break
                
                # Valida se o driver continua ativo
                try:
                    _ = self.driver.current_url
                except WebDriverException:
                    self.log_chat("Sistema", "Erro: A janela do navegador automatizado foi fechada ou ficou inacessível.")
                    break

                iteration += 1
                self.log_status(f"Status: Executando iteração {iteration}/{max_iterations}...")

                # Compila feedbacks
                feedback_str = "\n".join(action_feedback_list)
                action_feedback_list = []
                feedback_block = ""
                if feedback_str:
                    feedback_block = f"=== RETORNO DAS AÇÕES DA ITERAÇÃO ANTERIOR ===\n{feedback_str}\n==============================================\n\n"

                # Histórico de chat
                chat_history = get_chat_history_callback()
                chat_context_str = "\n".join([f"[{m['role']}]: {m['content']}" for m in chat_history])

                # 1. VISÃO: Tira print do navegador
                try:
                    screenshot_bytes = self.driver.get_screenshot_as_png()
                    img = Image.open(io.BytesIO(screenshot_bytes))
                    # Otimiza e converte para JPEG
                    buffer = io.BytesIO()
                    img.convert("RGB").save(buffer, format="JPEG", quality=80)
                    img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                    image_payload = {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_base64}"
                        }
                    }
                    has_screenshot = True
                except Exception as e:
                    print(f"[SELENIUM WARN] Falha ao capturar print: {e}")
                    has_screenshot = False

                # 2. ESTRUTURA DOM: Extrai elementos interativos da página atual
                elements_info = []
                elements = self.driver.find_elements(By.XPATH, "//*[self::input or self::textarea or self::select or self::button or self::a]")
                for el in elements:
                    try:
                        if el.is_displayed() and el.is_enabled():
                            elements_info.append({
                                "tag": el.tag_name,
                                "id": el.get_attribute("id") or "",
                                "name": el.get_attribute("name") or "",
                                "placeholder": el.get_attribute("placeholder") or "",
                                "type": el.get_attribute("type") or "",
                                "text": el.text[:60] or "",
                                "class": el.get_attribute("class") or ""
                            })
                    except Exception:
                        pass

                # Prepara o prompt do LLM
                prompt = (
                    f"=== DIRETRIZES DO AGENTE ===\n{system_prompt}\n=============================\n\n"
                    f"{feedback_block}"
                    f"Você é um assistente de automação web Selenium rodando em loop. O usuário deseja realizar a seguinte tarefa: '{task_description}'.\n"
                    f"URL atual do navegador: {self.driver.current_url}\n\n"
                    f"Temos dados de um arquivo local relevante (se necessário):\n"
                    f"=== DADOS DO ARQUIVO ===\n{file_content_1}\n========================\n\n"
                    f"Elementos interativos localizados na página atual (DOM):\n"
                    f"{json.dumps(elements_info, indent=2)}\n\n"
                    f"=== HISTÓRICO DE CHAT ===\n{chat_context_str}\n========================\n\n"
                    f"Lista de ações já executadas nas iterações anteriores:\n"
                    f"{json.dumps(executed_actions_log, indent=2)}\n\n"
                    f"Analise o print do navegador (se fornecido) e os elementos DOM acima para decidir o próximo passo.\n"
                    f"Retorne OBRIGATORIAMENTE um JSON puro (sem markdown ```json). O JSON deve seguir exatamente o formato:\n"
                    f"{{\n"
                    f"  \"completed\": false, // defina como true apenas quando atingir o objetivo web final\n"
                    f"  \"message\": \"Texto detalhado explicando o que você está fazendo no navegador\",\n"
                    f"  \"waiting_for_user\": false, // defina como true se precisar de suporte do usuário no chat\n"
                    f"  \"actions\": [\n"
                    f"    // Lista ordenada de ações no DOM ou no Sistema. Exemplos:\n"
                    f"    // {{\"type\": \"click\", \"by\": \"id\", \"value\": \"id_do_elemento\"}},\n"
                    f"    // {{\"type\": \"type\", \"by\": \"name\", \"value\": \"nome_campo\", \"text\": \"valor\"}},\n"
                    f"    // {{\"type\": \"click\", \"by\": \"xpath\", \"value\": \"//a[contains(text(),'Entrar')]\"}},\n"
                    f"    // {{\"type\": \"wait\", \"duration\": 2.0}},\n"
                    f"    // {{\"type\": \"read_file\", \"path\": \"caminho\"}},\n"
                    f"    // {{\"type\": \"write_file\", \"path\": \"caminho\", \"content\": \"conteudo\"}},\n"
                    f"    // {{\"type\": \"run_command\", \"command\": \"comando\"}},\n"
                    f"    // {{\"type\": \"open_url\", \"url\": \"https://exemplo.com\"}}\n"
                    f"  ]\n"
                    f"}}"
                )

                content_list = [{"type": "text", "text": prompt}]
                if has_screenshot:
                    content_list.append(image_payload)

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
                    "max_tokens": 1000,
                    "temperature": 0.1
                }

                # Executa a requisição
                res = requests.post(f"{api_url}/chat/completions", headers=headers, json=payload, timeout=60)
                res.raise_for_status()
                res_data = res.json()
                ai_message = res_data['choices'][0]['message']['content'].strip()

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
                    self.log_chat("Agente", "Objetivo web alcançado!")
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

                    # Ações de sistema
                    if act_type in ("read_file", "write_file", "run_command", "open_url"):
                        self.log_status(f"Status: Solicitando aprovação para {act_type}...")
                        feedback_msg = self.run_sensitive_action(act)
                        action_feedback_list.append(feedback_msg)
                        executed_actions_log.append(f"{act_type}: {feedback_msg.splitlines()[0] if feedback_msg else ''}")
                        continue

                    # Ações do DOM Selenium
                    feedback_msg = self.execute_dom_action(act)
                    action_feedback_list.append(feedback_msg)
                    executed_actions_log.append(f"{act_type} em {act.get('value')}: {feedback_msg}")

                time.sleep(1.0)

            if not success and iteration >= max_iterations:
                self.log_chat("Agente", "Limite de iterações atingido sem conclusão da automação web.")

        except Exception as e:
            self.log_chat("Sistema", f"Erro na execução do agente web: {str(e)}")
            print(f"[SELENIUM AGENT ERROR] Erro no loop: {e}")
