import queue
import threading
import time
import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog
from PIL import Image, ImageTk

from src.config import Action, DEFAULT_LOGO_PATH, DEFAULT_SYSTEM_PROMPT
from src.database import DatabaseManager
from src.recorder import ClickRecorder
from src.playback import MacroPlayer
from src.agent_ocr import AutonomousVisualAgent
from src.agent_selenium import AutonomousSeleniumAgent
from src.agent_merge import merge_files_to_excel

# Paleta de Cores Premium (Dark Theme)
BG_PRIMARY = "#121214"      # Fundo geral
BG_SECONDARY = "#1E1E24"    # Fundo de cards/frames
BG_INPUT = "#2E2F38"        # Fundo de inputs
FG_PRIMARY = "#F8F9FA"      # Texto claro
FG_SECONDARY = "#94A3B8"    # Texto cinza
COLOR_TEAL = "#00B4D8"      # Ciano principal
COLOR_GREEN = "#2EC4B6"     # Verde (Sucesso/Gravar)
COLOR_RED = "#FF5A5F"       # Vermelho (Parar)
COLOR_ORANGE = "#FF9F1C"    # Amarelo/Laranja (Executar)


class ClickRecorderApp:
    """Interface Gráfica Modernizada com Tema Dark de Alta Fidelidade (ClickRecorder Pro)."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("ClickRecorder RPA Pro")
        self.root.geometry("1180x740")
        self.root.configure(bg=BG_PRIMARY)
        self.root.resizable(True, True)

        # Gerenciamento de Fila de Atualizações da GUI (Thread Safety)
        self.gui_queue = queue.Queue()
        self.root.after(50, self.process_gui_queue)

        # Core do sistema
        self.db = DatabaseManager()
        self.recorder = ClickRecorder(
            on_action_added=self.on_recorder_action_added,
            is_ignored_area=self.is_cursor_in_ignored_gui
        )
        self.player = MacroPlayer(
            on_status_update=self.on_playback_status_update,
            run_agent_callback=self.run_agent_callback_dispatch
        )
        
        # Variáveis de Estado
        self.recordings = []
        self.current_clicks = []
        self.playing = False
        self.recording = False
        self.agent_active = False
        
        # Selenium Driver Ativo
        self.selenium_driver = None

        # Histórico de Conversa Local
        self.chat_history_list = []
        self.user_message_event = threading.Event()
        self.last_user_message = ""

        # Montagem Visual
        self.build_ui()
        self.load_recordings()

    # ----------------------------------------------------
    # Thread Safe GUI Event Loop
    # ----------------------------------------------------
    def process_gui_queue(self):
        """Processa funções enfileiradas de outras threads de maneira segura na thread principal."""
        try:
            while True:
                fn, args, kwargs = self.gui_queue.get_nowait()
                try:
                    fn(*args, **kwargs)
                except Exception as e:
                    print(f"[GUI QUEUE ERROR] Falha ao rodar função agendada: {e}")
                self.gui_queue.task_done()
        except queue.Empty:
            pass
        self.root.after(50, self.process_gui_queue)

    def schedule_gui_update(self, fn, *args, **kwargs):
        """Enfileira uma chamada de GUI vinda de thread secundária."""
        self.gui_queue.put((fn, args, kwargs))

    # ----------------------------------------------------
    # Utilitários de Janela e DPI
    # ----------------------------------------------------
    def is_cursor_in_ignored_gui(self, x, y):
        """Retorna True se o clique do mouse ocorreu dentro dos limites lógicos de janelas do app."""
        # Se estiver minimizado, não ignora nada
        if self.root.state() == 'iconic':
            return False
            
        try:
            win_x = self.root.winfo_rootx()
            win_y = self.root.winfo_rooty()
            win_w = self.root.winfo_width()
            win_h = self.root.winfo_height()
            if win_x <= x <= win_x + win_w and win_y <= y <= win_y + win_h:
                return True
        except Exception:
            pass
        return False

    # ----------------------------------------------------
    # Elementos de Estilização Customizados
    # ----------------------------------------------------
    def style_button(self, widget, bg_color, hover_color=None):
        """Aplica estilo flat moderno a botões."""
        widget.configure(
            bg=bg_color,
            fg="white",
            activebackground=hover_color or bg_color,
            activeforeground="white",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2"
        )
        if hover_color:
            widget.bind("<Enter>", lambda e: widget.configure(bg=hover_color))
            widget.bind("<Leave>", lambda e: widget.configure(bg=bg_color))

    def style_entry(self, widget):
        """Aplica estilo dark moderno a inputs."""
        widget.configure(
            bg=BG_INPUT,
            fg=FG_PRIMARY,
            insertbackground=FG_PRIMARY,
            relief=tk.FLAT,
            bd=2,
            highlightthickness=1,
            highlightbackground="#3E3F48",
            highlightcolor=COLOR_TEAL
        )

    # ----------------------------------------------------
    # Construção da Interface do Usuário (UI/UX)
    # ----------------------------------------------------
    def build_ui(self):
        # 1. Top Logo Bar
        top_bar = tk.Frame(self.root, bg=BG_SECONDARY, height=70)
        top_bar.pack(fill=tk.X, side=tk.TOP)
        top_bar.pack_propagate(False)
        self.create_logo(top_bar)

        # Divisor Superior
        tk.Frame(self.root, bg="#2A2A35", height=1).pack(fill=tk.X)

        # 2. Main Container Frame
        main_container = tk.Frame(self.root, bg=BG_PRIMARY)
        main_container.pack(fill=tk.BOTH, expand=True)

        # 3. Painel Esquerdo (Automações Salvas)
        left_panel = tk.Frame(main_container, bg=BG_SECONDARY, padx=15, pady=15, width=280)
        left_panel.pack(side=tk.LEFT, fill=tk.Y)
        left_panel.pack_propagate(False)

        tk.Label(left_panel, text="Automações Salvas", font=("Arial", 12, "bold"), bg=BG_SECONDARY, fg=FG_PRIMARY).pack(anchor=tk.W, pady=(0, 10))
        
        self.recordings_listbox = tk.Listbox(
            left_panel, 
            bg=BG_INPUT, 
            fg=FG_PRIMARY, 
            selectbackground=COLOR_TEAL, 
            selectforeground="white",
            relief=tk.FLAT, 
            bd=0, 
            font=("Arial", 9), 
            highlightthickness=0
        )
        self.recordings_listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        # Configuração de Velocidade
        speed_frame = tk.Frame(left_panel, bg=BG_SECONDARY)
        speed_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Label(speed_frame, text="Velocidade:", font=("Arial", 9), bg=BG_SECONDARY, fg=FG_SECONDARY).pack(side=tk.LEFT)
        
        self.speed_var = tk.StringVar(value="Real")
        self.speed_menu = tk.OptionMenu(speed_frame, self.speed_var, "Real", "Turbo", "Safe")
        self.speed_menu.configure(bg=BG_INPUT, fg=FG_PRIMARY, activebackground=BG_INPUT, activeforeground=FG_PRIMARY, relief=tk.FLAT, bd=0, highlightthickness=0)
        self.speed_menu["menu"].configure(bg=BG_INPUT, fg=FG_PRIMARY)
        self.speed_menu.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        # Botões do Painel Esquerdo
        self.btn_execute = tk.Button(left_panel, text="▶ Executar Automação", font=("Arial", 10, "bold"), command=self.execute_recording, height=2)
        self.btn_execute.pack(fill=tk.X, pady=4)
        self.style_button(self.btn_execute, COLOR_ORANGE, "#E08500")

        self.btn_stop_exec = tk.Button(left_panel, text="■ Parar Execução", font=("Arial", 10, "bold"), command=self.stop_execution, state=tk.DISABLED, height=2)
        self.btn_stop_exec.pack(fill=tk.X, pady=4)
        self.style_button(self.btn_stop_exec, "#555", "#444")

        self.btn_new = tk.Button(left_panel, text="+ Nova Automação", font=("Arial", 10, "bold"), command=self.new_automation)
        self.btn_new.pack(fill=tk.X, pady=4)
        self.style_button(self.btn_new, COLOR_GREEN, "#1FA598")

        self.btn_edit = tk.Button(left_panel, text="✏ Editar Automação", font=("Arial", 9, "bold"), command=self.edit_automation)
        self.btn_edit.pack(fill=tk.X, pady=4)
        self.style_button(self.btn_edit, "#3A3B45", "#4E4F5A")

        self.btn_delete = tk.Button(left_panel, text="🗑 Excluir Automação", font=("Arial", 9, "bold"), command=self.delete_recording)
        self.btn_delete.pack(fill=tk.X, pady=(4, 0))
        self.style_button(self.btn_delete, COLOR_RED, "#D84A4F")

        # Divisor Central 1
        tk.Frame(main_container, bg="#2A2A35", width=1).pack(side=tk.LEFT, fill=tk.Y)

        # 4. Painel Central (Controle do Gravador & Configurações Globais)
        middle_panel = tk.Frame(main_container, bg=BG_PRIMARY, padx=15, pady=15)
        middle_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(middle_panel, text="Controle de Gravação", font=("Arial", 12, "bold"), bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W)

        # Status badge do gravador
        self.recorder_status_var = tk.StringVar(value="Pronto para iniciar gravação.")
        self.recorder_status_lbl = tk.Label(middle_panel, textvariable=self.recorder_status_var, font=("Arial", 10), bg=BG_PRIMARY, fg=COLOR_TEAL, wraplength=400, justify=tk.LEFT)
        self.recorder_status_lbl.pack(anchor=tk.W, pady=(5, 10))

        # Botões Iniciar/Parar
        btn_rec_frame = tk.Frame(middle_panel, bg=BG_PRIMARY)
        btn_rec_frame.pack(anchor=tk.W, fill=tk.X, pady=(0, 15))

        self.btn_start_rec = tk.Button(btn_rec_frame, text="● Iniciar Gravação", font=("Arial", 11, "bold"), width=18, height=2, command=self.start_recording)
        self.btn_start_rec.pack(side=tk.LEFT, padx=(0, 10))
        self.style_button(self.btn_start_rec, COLOR_GREEN, "#1FA598")

        self.btn_stop_rec = tk.Button(btn_rec_frame, text="■ Parar Gravação", font=("Arial", 11, "bold"), width=18, height=2, command=self.stop_recording, state=tk.DISABLED)
        self.btn_stop_rec.pack(side=tk.LEFT)
        self.style_button(self.btn_stop_rec, "#555", "#444")

        # Contador de Cliques
        self.click_count_var = tk.StringVar(value="Ações Registradas: 0")
        tk.Label(middle_panel, textvariable=self.click_count_var, font=("Arial", 10, "italic"), bg=BG_PRIMARY, fg=FG_SECONDARY).pack(anchor=tk.W, pady=(0, 15))

        # Dicas Box
        tips_frame = tk.LabelFrame(middle_panel, text="Dicas Rápidas", bg=BG_PRIMARY, fg=FG_PRIMARY, font=("Arial", 9, "bold"), padx=10, pady=8, highlightthickness=0, borderwidth=1, relief=tk.SOLID)
        tips_frame.pack(fill=tk.X, pady=(0, 15))
        tips_text = (
            "1. Clique em 'Iniciar Gravação' para calibrar a tela.\n"
            "2. Uma contagem de 3s aparecerá antes de iniciar.\n"
            "3. Grave cliques, rolagens e digitação normalmente.\n"
            "4. O botão '■ Parar' na janela do app encerrará o processo."
        )
        tk.Label(tips_frame, text=tips_text, justify=tk.LEFT, font=("Arial", 9), bg=BG_PRIMARY, fg=FG_SECONDARY).pack(anchor=tk.W)

        # Seção Selenium
        selenium_sec = tk.LabelFrame(middle_panel, text="Automação Web Selenium", bg=BG_PRIMARY, fg=FG_PRIMARY, font=("Arial", 9, "bold"), padx=10, pady=8, highlightthickness=0, borderwidth=1, relief=tk.SOLID)
        selenium_sec.pack(fill=tk.X, pady=(0, 15))
        
        self.btn_open_sel = tk.Button(selenium_sec, text="Abrir Navegador Automatizado", font=("Arial", 9, "bold"), command=self.open_selenium, width=28)
        self.btn_open_sel.pack(anchor=tk.W, pady=5)
        self.style_button(self.btn_open_sel, "#6F42C1", "#5930A4")

        # Configurações Globais (Scrollable Frame ou Cards)
        config_frame = tk.LabelFrame(middle_panel, text="Configurações do Robô & IA", bg=BG_PRIMARY, fg=FG_PRIMARY, font=("Arial", 9, "bold"), padx=10, pady=8, highlightthickness=0, borderwidth=1, relief=tk.SOLID)
        config_frame.pack(fill=tk.BOTH, expand=True)

        # Layout Grade de Configurações
        tk.Label(config_frame, text="API Key OpenAI:", font=("Arial", 9), bg=BG_PRIMARY, fg=FG_SECONDARY).grid(row=0, column=0, sticky=tk.W, pady=3)
        self.api_key_var = tk.StringVar(value=self.db.get_setting("openai_api_key", ""))
        self.entry_api_key = tk.Entry(config_frame, textvariable=self.api_key_var, show="*", width=30)
        self.entry_api_key.grid(row=0, column=1, sticky=tk.W, pady=3, padx=10)
        self.style_entry(self.entry_api_key)

        tk.Label(config_frame, text="API Base URL:", font=("Arial", 9), bg=BG_PRIMARY, fg=FG_SECONDARY).grid(row=1, column=0, sticky=tk.W, pady=3)
        self.api_url_var = tk.StringVar(value=self.db.get_setting("agent_api_url", "https://api.openai.com/v1"))
        self.entry_api_url = tk.Entry(config_frame, textvariable=self.api_url_var, width=30)
        self.entry_api_url.grid(row=1, column=1, sticky=tk.W, pady=3, padx=10)
        self.style_entry(self.entry_api_url)

        tk.Label(config_frame, text="Modelo Visão/OCR:", font=("Arial", 9), bg=BG_PRIMARY, fg=FG_SECONDARY).grid(row=2, column=0, sticky=tk.W, pady=3)
        self.ocr_model_var = tk.StringVar(value=self.db.get_setting("agent_ocr_model", "gpt-4o"))
        self.entry_ocr_model = tk.Entry(config_frame, textvariable=self.ocr_model_var, width=30)
        self.entry_ocr_model.grid(row=2, column=1, sticky=tk.W, pady=3, padx=10)
        self.style_entry(self.entry_ocr_model)

        tk.Label(config_frame, text="Modelo Selenium:", font=("Arial", 9), bg=BG_PRIMARY, fg=FG_SECONDARY).grid(row=3, column=0, sticky=tk.W, pady=3)
        self.sel_model_var = tk.StringVar(value=self.db.get_setting("agent_selenium_model", "gpt-4o-mini"))
        self.entry_sel_model = tk.Entry(config_frame, textvariable=self.sel_model_var, width=30)
        self.entry_sel_model.grid(row=3, column=1, sticky=tk.W, pady=3, padx=10)
        self.style_entry(self.entry_sel_model)

        tk.Label(config_frame, text="Espera Máxima (s):", font=("Arial", 9), bg=BG_PRIMARY, fg=FG_SECONDARY).grid(row=4, column=0, sticky=tk.W, pady=3)
        self.max_wait_var = tk.StringVar(value=self.db.get_setting("max_wait_delay", "10.0"))
        self.entry_max_wait = tk.Entry(config_frame, textvariable=self.max_wait_var, width=10)
        self.entry_max_wait.grid(row=4, column=1, sticky=tk.W, pady=3, padx=10)
        self.style_entry(self.entry_max_wait)

        self.btn_save_config = tk.Button(config_frame, text="Salvar Configs", font=("Arial", 9, "bold"), command=self.save_configs, width=15)
        self.btn_save_config.grid(row=5, column=1, sticky=tk.E, pady=10, padx=10)
        self.style_button(self.btn_save_config, COLOR_GREEN, "#1FA598")

        # Divisor Central 2
        tk.Frame(main_container, bg="#2A2A35", width=1).pack(side=tk.LEFT, fill=tk.Y)

        # 5. Painel Direito (Agente de IA e Chat Premium)
        right_panel = tk.Frame(main_container, bg=BG_SECONDARY, padx=15, pady=15, width=380)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH)
        right_panel.pack_propagate(False)

        tk.Label(right_panel, text="Painel do Agente IA", font=("Arial", 12, "bold"), bg=BG_SECONDARY, fg=FG_PRIMARY).pack(anchor=tk.W)

        self.agent_status_var = tk.StringVar(value="Status: Inativo")
        self.agent_status_lbl = tk.Label(right_panel, textvariable=self.agent_status_var, font=("Arial", 9, "italic"), bg=BG_SECONDARY, fg=FG_SECONDARY)
        self.agent_status_lbl.pack(anchor=tk.W, pady=(2, 8))

        # Checkbox Minimizar
        self.minimize_var = tk.BooleanVar(value=True)
        self.chk_minimize = tk.Checkbutton(
            right_panel, 
            text="Minimizar app ao iniciar agente IA",
            variable=self.minimize_var,
            bg=BG_SECONDARY,
            fg=FG_PRIMARY,
            activebackground=BG_SECONDARY,
            activeforeground=FG_PRIMARY,
            selectcolor=BG_PRIMARY,
            relief=tk.FLAT,
            bd=0,
            font=("Arial", 9)
        )
        self.chk_minimize.pack(anchor=tk.W, pady=(0, 10))

        # Caixa do Chat (Custom Tags para Balões de Conversa)
        chat_container = tk.Frame(right_panel, bg=BG_INPUT)
        chat_container.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        chat_scroll = tk.Scrollbar(chat_container, bg=BG_INPUT, relief=tk.FLAT)
        chat_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.chat_history = tk.Text(
            chat_container, 
            wrap=tk.WORD, 
            yscrollcommand=chat_scroll.set, 
            bg=BG_INPUT, 
            fg=FG_PRIMARY,
            relief=tk.FLAT, 
            bd=0, 
            padx=10, 
            pady=10,
            font=("Arial", 9),
            state=tk.DISABLED
        )
        self.chat_history.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        chat_scroll.config(command=self.chat_history.yview)

        # Configura as tags de estilo para os balões de conversa no widget de Text
        self.chat_history.tag_configure("user", foreground="#00E5FF", font=("Arial", 9, "bold"), justify=tk.RIGHT, spacing3=8)
        self.chat_history.tag_configure("agent", foreground="#00F5D4", font=("Arial", 9, "bold"), spacing3=8)
        self.chat_history.tag_configure("system", foreground=COLOR_ORANGE, font=("Arial", 9, "italic"), spacing3=8)
        self.chat_history.tag_configure("text_user", foreground=FG_PRIMARY, justify=tk.RIGHT, lmargin1=80, spacing3=15)
        self.chat_history.tag_configure("text_agent", foreground=FG_PRIMARY, rmargin=80, spacing3=15)
        self.chat_history.tag_configure("text_system", foreground=FG_SECONDARY, lmargin1=40, rmargin=40, spacing3=15)

        # Barra de Entrada do Chat
        chat_input_frame = tk.Frame(right_panel, bg=BG_SECONDARY)
        chat_input_frame.pack(fill=tk.X)

        self.chat_input = tk.Entry(chat_input_frame, font=("Arial", 10))
        self.chat_input.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.chat_input.bind("<Return>", lambda e: self.send_user_message())
        self.style_entry(self.chat_input)

        self.btn_send = tk.Button(chat_input_frame, text="Enviar", font=("Arial", 9, "bold"), command=self.send_user_message, width=10)
        self.btn_send.pack(side=tk.RIGHT, padx=(5, 0))
        self.style_button(self.btn_send, COLOR_TEAL, "#0091B0")

    # ----------------------------------------------------
    # Logo e Identidade Visual
    # ----------------------------------------------------
    def create_logo(self, parent):
        """Carrega e redimensiona a logo PNG corporativa de forma flexível."""
        try:
            logo_path = DEFAULT_LOGO_PATH
            if not os.path.exists(logo_path):
                # Fallback se a logo não existir
                logo_label = tk.Label(parent, text="RPA", font=("Arial", 18, "bold"), bg=BG_SECONDARY, fg=COLOR_TEAL, width=8)
                logo_label.pack(side=tk.LEFT, padx=15)
            else:
                img = Image.open(logo_path)
                img.thumbnail((50, 50), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(img)
                logo_label = tk.Label(parent, image=self.logo_photo, bg=BG_SECONDARY)
                logo_label.pack(side=tk.LEFT, padx=15)
        except Exception as e:
            print(f"[GUI WARN] Não foi possível carregar a logo: {e}")
            logo_label = tk.Label(parent, text="RPA", font=("Arial", 18, "bold"), bg=BG_SECONDARY, fg=COLOR_TEAL, width=8)
            logo_label.pack(side=tk.LEFT, padx=15)

        title_frame = tk.Frame(parent, bg=BG_SECONDARY)
        title_frame.pack(side=tk.LEFT, pady=5)
        
        tk.Label(title_frame, text="ClickRecorder Pro", font=("Arial", 14, "bold"), bg=BG_SECONDARY, fg=COLOR_TEAL).pack(anchor=tk.W)
        tk.Label(title_frame, text="Sistema de Automação Autônoma RPA", font=("Arial", 8), bg=BG_SECONDARY, fg=FG_SECONDARY).pack(anchor=tk.W)

    # ----------------------------------------------------
    # Controle e Execução de Configurações
    # ----------------------------------------------------
    def save_configs(self):
        """Salva as configurações inseridas pelo usuário no banco de dados SQLite."""
        self.db.set_setting("openai_api_key", self.api_key_var.get().strip())
        self.db.set_setting("agent_api_url", self.api_url_var.get().strip())
        self.db.set_setting("agent_ocr_model", self.ocr_model_var.get().strip())
        self.db.set_setting("agent_selenium_model", self.sel_model_var.get().strip())
        self.db.set_setting("max_wait_delay", self.max_wait_var.get().strip())
        messagebox.showinfo("Configurações", "Configurações globais salvas com sucesso!")

    # ----------------------------------------------------
    # Gerenciamento de Automações Salvas
    # ----------------------------------------------------
    def load_recordings(self):
        """Carrega gravações do banco e popula listbox de automações."""
        self.recordings = self.db.get_all_recordings()
        self.recordings_listbox.delete(0, tk.END)
        for idx, rec in enumerate(self.recordings, start=1):
            try:
                clicks = json.loads(rec['clicks_data'])
                steps_count = len(clicks)
            except Exception:
                steps_count = 0
            run_cnt = rec.get('run_count', 0) or 0
            label = f"{idx}. {rec['name']} ({steps_count} passos) [Executado: {run_cnt}x]"
            self.recordings_listbox.insert(tk.END, label)

    # ----------------------------------------------------
    # Gravação pynput
    # ----------------------------------------------------
    def start_recording(self):
        if self.recording:
            return
            
        self.recording = True
        self.btn_start_rec.config(state=tk.DISABLED)
        self.btn_stop_rec.config(state=tk.NORMAL)
        self.style_button(self.btn_stop_rec, COLOR_RED, "#D84A4F")
        self.recorder_status_var.set("Iniciando em 3 segundos...")
        self.click_count_var.set("Ações Registradas: 0")
        
        threading.Thread(target=self.countdown_and_record_thread, daemon=True).start()

    def countdown_and_record_thread(self):
        for count in [3, 2, 1]:
            self.schedule_gui_update(self.recorder_status_var.set, f"Preparando... {count}")
            time.sleep(1)
            
        self.schedule_gui_update(self.recorder_status_var.set, "GRAVANDO... use o computador normalmente. Clique em parar ao terminar.")
        self.recorder.start_recording()

    def on_recorder_action_added(self, current_actions):
        """Chamado a cada clique/ação capturada."""
        count = len(current_actions)
        self.schedule_gui_update(self.click_count_var.set, f"Ações Registradas: {count}")

    def stop_recording(self):
        if not self.recording:
            return
            
        self.recording = False
        self.btn_start_rec.config(state=tk.NORMAL)
        self.btn_stop_rec.config(state=tk.DISABLED)
        self.style_button(self.btn_stop_rec, "#555", "#444")
        
        actions = self.recorder.stop_recording()
        
        if not actions:
            self.recorder_status_var.set("Nenhuma ação capturada. Gravação encerrada.")
            return

        name = simpledialog.askstring("Salvar Automação", "Digite um nome para a automação gravada:", parent=self.root)
        if not name:
            name = f"Automação {len(self.recordings) + 1}"
            
        description = simpledialog.askstring("Descrição", "Descreva brevemente o que esta automação faz:", parent=self.root) or ""

        try:
            if self.db.add_recording(name.strip(), actions, description.strip()):
                self.load_recordings()
                self.recorder_status_var.set(f"Automação '{name}' salva com sucesso!")
            else:
                self.recorder_status_var.set("Erro ao salvar gravação.")
        except ValueError as e:
            messagebox.showerror("Erro", str(e), parent=self.root)

    def delete_recording(self):
        sel = self.recordings_listbox.curselection()
        if not sel:
            messagebox.showinfo("Aviso", "Selecione uma automação para excluir.")
            return
            
        record = self.recordings[sel[0]]
        confirm = messagebox.askyesno("Excluir", f"Deseja realmente remover '{record['name']}'?", parent=self.root)
        if confirm:
            if self.db.delete_recording(record["name"]):
                self.load_recordings()
                self.recorder_status_var.set(f"Automação '{record['name']}' excluída.")

    # ----------------------------------------------------
    # Execução de Macros (Playback)
    # ----------------------------------------------------
    def execute_recording(self):
        if self.playing:
            messagebox.showwarning("Aviso", "Uma execução já está em andamento.")
            return
            
        sel = self.recordings_listbox.curselection()
        if not sel:
            messagebox.showinfo("Aviso", "Selecione uma automação para executar.")
            return
            
        record = self.recordings[sel[0]]
        try:
            clicks = json.loads(record["clicks_data"])
        except Exception:
            clicks = []
            
        if not clicks:
            messagebox.showinfo("Aviso", "Esta automação não possui passos gravados.")
            return
            
        self.playing = True
        self.btn_execute.config(state=tk.DISABLED)
        self.btn_stop_exec.config(state=tk.NORMAL)
        self.style_button(self.btn_stop_exec, COLOR_RED, "#D84A4F")
        
        # Incrementa contador
        self.db.increment_run_count(record["name"])
        self.load_recordings()
        self.recordings_listbox.selection_set(sel[0])

        speed = self.speed_var.get()
        try:
            max_wait = float(self.max_wait_var.get())
        except ValueError:
            max_wait = 10.0

        threading.Thread(target=self.playback_thread, args=(clicks, speed, max_wait), daemon=True).start()

    def playback_thread(self, clicks, speed, max_wait):
        self.player.play(clicks, speed_mode=speed, max_wait_delay=max_wait)
        self.schedule_gui_update(self.on_playback_finished)

    def on_playback_status_update(self, msg):
        self.schedule_gui_update(self.recorder_status_var.set, msg)

    def on_playback_finished(self):
        self.playing = False
        self.btn_execute.config(state=tk.NORMAL)
        self.btn_stop_exec.config(state=tk.DISABLED)
        self.style_button(self.btn_stop_exec, "#555", "#444")

    def stop_execution(self):
        if self.playing:
            self.player.stop_playback()
            self.playing = False
            # Libera qualquer thread do agente que esteja esperando resposta do chat
            self.user_message_event.set()

    # ----------------------------------------------------
    # Criação/Edição de Automação (Editor)
    # ----------------------------------------------------
    def new_automation(self):
        name = simpledialog.askstring("Nova Automação", "Digite o nome da automação:", parent=self.root)
        if not name or not name.strip():
            return
        
        try:
            if self.db.add_recording(name.strip(), []):
                self.load_recordings()
                # Localiza o índice do recém criado e abre o editor
                for idx, r in enumerate(self.recordings):
                    if r["name"] == name.strip():
                        self.recordings_listbox.selection_clear(0, tk.END)
                        self.recordings_listbox.selection_set(idx)
                        self.edit_automation()
                        break
        except ValueError as e:
            messagebox.showerror("Erro", str(e), parent=self.root)

    def edit_automation(self):
        """Abre a janela do Editor unificado de automações."""
        sel = self.recordings_listbox.curselection()
        if not sel:
            messagebox.showinfo("Aviso", "Selecione uma automação para editar.")
            return
            
        record = self.recordings[sel[0]]
        
        # Carrega passos
        try:
            clicks = json.loads(record["clicks_data"])
        except Exception:
            clicks = []
            
        actions = [Action.from_dict(c) for c in clicks]
        
        editor = tk.Toplevel(self.root)
        editor.title(f"Editor: {record['name']}")
        editor.geometry("740x650")
        editor.configure(bg=BG_PRIMARY)
        
        # Estilos do Editor
        tk.Label(editor, text="Nome da Automação:", font=("Arial", 10, "bold"), bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, padx=20, pady=(15, 2))
        name_var = tk.StringVar(value=record["name"])
        name_entry = tk.Entry(editor, textvariable=name_var, width=50, font=("Arial", 10))
        name_entry.pack(anchor=tk.W, padx=20, pady=(0, 10))
        self.style_entry(name_entry)

        tk.Label(editor, text="Descrição:", font=("Arial", 10, "bold"), bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, padx=20, pady=(0, 2))
        desc_var = tk.StringVar(value=record.get("description", "") or "")
        desc_entry = tk.Entry(editor, textvariable=desc_var, width=50, font=("Arial", 10))
        desc_entry.pack(anchor=tk.W, padx=20, pady=(0, 15))
        self.style_entry(desc_entry)

        # Listbox de Passos
        tk.Label(editor, text="Passos Sequenciais:", font=("Arial", 10, "bold"), bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, padx=20)
        
        list_frame = tk.Frame(editor, bg=BG_PRIMARY)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        scroll = tk.Scrollbar(list_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        steps_listbox = tk.Listbox(list_frame, bg=BG_INPUT, fg=FG_PRIMARY, selectbackground=COLOR_TEAL, font=("Arial", 9), relief=tk.FLAT, bd=0, yscrollcommand=scroll.set)
        steps_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=steps_listbox.yview)

        def populate_steps():
            steps_listbox.delete(0, tk.END)
            for idx, act in enumerate(actions, start=1):
                steps_listbox.insert(tk.END, f"{idx}. {str(act)}")

        populate_steps()

        # Botões de operações do passo selecionado
        ops_frame = tk.Frame(editor, bg=BG_PRIMARY)
        ops_frame.pack(fill=tk.X, padx=20, pady=5)

        # Helper para obter o passo selecionado
        def get_selected_action_idx():
            cur = steps_listbox.curselection()
            return cur[0] if cur else None

        def delete_step():
            idx = get_selected_action_idx()
            if idx is not None:
                del actions[idx]
                populate_steps()
                steps_listbox.selection_set(min(idx, len(actions)-1))

        def duplicate_step():
            idx = get_selected_action_idx()
            if idx is not None:
                dup = Action.from_dict(actions[idx].to_dict())
                actions.insert(idx + 1, dup)
                populate_steps()
                steps_listbox.selection_set(idx + 1)

        def move_up():
            idx = get_selected_action_idx()
            if idx is not None and idx > 0:
                actions[idx], actions[idx-1] = actions[idx-1], actions[idx]
                populate_steps()
                steps_listbox.selection_set(idx - 1)

        def move_down():
            idx = get_selected_action_idx()
            if idx is not None and idx < len(actions) - 1:
                actions[idx], actions[idx+1] = actions[idx+1], actions[idx]
                populate_steps()
                steps_listbox.selection_set(idx + 1)

        # Grid de Botões de controle de passos
        btn_grid_frame = tk.Frame(editor, bg=BG_PRIMARY)
        btn_grid_frame.pack(fill=tk.X, padx=20, pady=10)

        # Diálogo para Adicionar / Editar Passo individual
        def open_action_editor(action, is_new=False, insert_idx=None):
            dlg = tk.Toplevel(editor)
            dlg.title("Configurar Passo")
            dlg.geometry("500x560")
            dlg.configure(bg=BG_PRIMARY)
            
            tk.Label(dlg, text="Tipo de Ação:", font=("Arial", 10, "bold"), bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, padx=20, pady=(15, 2))
            
            type_var = tk.StringVar(value=action.type)
            type_menu = tk.OptionMenu(dlg, type_var, Action.TYPE_CLICK, Action.TYPE_TYPE, Action.TYPE_WAIT, Action.TYPE_READ_FILE, Action.TYPE_SCROLL, Action.TYPE_AI)
            type_menu.configure(bg=BG_INPUT, fg=FG_PRIMARY, activebackground=BG_INPUT, activeforeground=FG_PRIMARY, relief=tk.FLAT, bd=0)
            type_menu.pack(anchor=tk.W, padx=20, pady=(0, 10))

            fields_container = tk.Frame(dlg, bg=BG_PRIMARY)
            fields_container.pack(fill=tk.BOTH, expand=True, padx=20)

            # Elementos do formulário
            x_var = tk.StringVar(value=str(action.x))
            y_var = tk.StringVar(value=str(action.y))
            button_var = tk.StringVar(value=action.button)
            text_var = tk.StringVar(value=action.text)
            duration_var = tk.StringVar(value=str(action.duration))
            file_path_var = tk.StringVar(value=action.file_path)
            read_mode_var = tk.StringVar(value=action.read_mode)
            file_selector_var = tk.StringVar(value=action.file_selector)
            dx_var = tk.StringVar(value=str(action.dx))
            dy_var = tk.StringVar(value=str(action.dy))
            ai_task_var = tk.StringVar(value=action.ai_task)
            ai_mode_var = tk.StringVar(value=action.ai_mode)
            file_path_2_var = tk.StringVar(value=action.file_path_2)
            file_path_3_var = tk.StringVar(value=action.file_path_3)
            output_path_var = tk.StringVar(value=action.output_path)

            def browse_file(target_var):
                path = filedialog.askopenfilename(title="Selecionar Arquivo")
                if path:
                    target_var.set(path)

            def draw_dynamic_fields(*args):
                # Limpa
                for w in fields_container.winfo_children():
                    w.destroy()

                t = type_var.get()
                
                # Ajusta tamanho da janela conforme o tipo
                if t == Action.TYPE_AI and ai_mode_var.get() == "excel_merge":
                    dlg.geometry("500x640")
                else:
                    dlg.geometry("500x480")

                if t == Action.TYPE_CLICK:
                    tk.Label(fields_container, text="Coordenada X (pixels lógicos):", bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, pady=3)
                    e_x = tk.Entry(fields_container, textvariable=x_var)
                    e_x.pack(fill=tk.X, pady=2)
                    self.style_entry(e_x)

                    tk.Label(fields_container, text="Coordenada Y (pixels lógicos):", bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, pady=3)
                    e_y = tk.Entry(fields_container, textvariable=y_var)
                    e_y.pack(fill=tk.X, pady=2)
                    self.style_entry(e_y)

                    tk.Label(fields_container, text="Botão do Mouse:", bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, pady=3)
                    m_btn = tk.OptionMenu(fields_container, button_var, "Button.left", "Button.right", "Button.middle")
                    m_btn.configure(bg=BG_INPUT, fg=FG_PRIMARY)
                    m_btn.pack(anchor=tk.W, pady=2)

                elif t == Action.TYPE_TYPE:
                    tk.Label(fields_container, text="Texto para Digitar:", bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, pady=3)
                    e_txt = tk.Entry(fields_container, textvariable=text_var)
                    e_txt.pack(fill=tk.X, pady=2)
                    self.style_entry(e_txt)

                elif t == Action.TYPE_WAIT:
                    tk.Label(fields_container, text="Duração do Atraso (segundos):", bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, pady=3)
                    e_dur = tk.Entry(fields_container, textvariable=duration_var)
                    e_dur.pack(fill=tk.X, pady=2)
                    self.style_entry(e_dur)

                elif t == Action.TYPE_READ_FILE:
                    tk.Label(fields_container, text="Caminho do Arquivo Local:", bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, pady=3)
                    f_frame = tk.Frame(fields_container, bg=BG_PRIMARY)
                    f_frame.pack(fill=tk.X, pady=2)
                    f_entry = tk.Entry(f_frame, textvariable=file_path_var)
                    f_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
                    self.style_entry(f_entry)
                    btn_brs = tk.Button(f_frame, text="...", command=lambda: browse_file(file_path_var), width=3)
                    btn_brs.pack(side=tk.RIGHT, padx=(5, 0))
                    self.style_button(btn_brs, "#444")

                    tk.Label(fields_container, text="Modo de Leitura:", bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, pady=3)
                    m_opt = tk.OptionMenu(fields_container, read_mode_var, "complete", "line", "json", "csv")
                    m_opt.configure(bg=BG_INPUT, fg=FG_PRIMARY)
                    m_opt.pack(anchor=tk.W, pady=2)

                    tk.Label(fields_container, text="Seletor/Chave (ex: 1 ou usuario.nome ou 1,2):", bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, pady=3)
                    e_sel = tk.Entry(fields_container, textvariable=file_selector_var)
                    e_sel.pack(fill=tk.X, pady=2)
                    self.style_entry(e_sel)

                elif t == Action.TYPE_SCROLL:
                    tk.Label(fields_container, text="Movimento Horizontal (dx):", bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, pady=3)
                    e_dx = tk.Entry(fields_container, textvariable=dx_var)
                    e_dx.pack(fill=tk.X, pady=2)
                    self.style_entry(e_dx)

                    tk.Label(fields_container, text="Movimento Vertical (dy):", bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, pady=3)
                    e_dy = tk.Entry(fields_container, textvariable=dy_var)
                    e_dy.pack(fill=tk.X, pady=2)
                    self.style_entry(e_dy)

                elif t == Action.TYPE_AI:
                    tk.Label(fields_container, text="Modo da Inteligência Artificial:", bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, pady=3)
                    ai_opt = tk.OptionMenu(fields_container, ai_mode_var, "ocr", "selenium", "excel_merge")
                    ai_opt.configure(bg=BG_INPUT, fg=FG_PRIMARY)
                    ai_opt.pack(anchor=tk.W, pady=2)
                    ai_mode_var.trace_add("write", draw_dynamic_fields)

                    tk.Label(fields_container, text="Instrução/Tarefa da IA:", bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, pady=3)
                    e_task = tk.Entry(fields_container, textvariable=ai_task_var)
                    e_task.pack(fill=tk.X, pady=2)
                    self.style_entry(e_task)

                    if ai_mode_var.get() == "excel_merge":
                        # Multi-arquivos
                        for i, var in enumerate([file_path_var, file_path_2_var, file_path_3_var], start=1):
                            tk.Label(fields_container, text=f"Planilha/CSV Origem {i}:", bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, pady=1)
                            f_fr = tk.Frame(fields_container, bg=BG_PRIMARY)
                            f_fr.pack(fill=tk.X, pady=1)
                            f_ent = tk.Entry(f_fr, textvariable=var)
                            f_ent.pack(side=tk.LEFT, fill=tk.X, expand=True)
                            self.style_entry(f_ent)
                            btn_b = tk.Button(f_fr, text="...", command=lambda v=var: browse_file(v), width=3)
                            btn_b.pack(side=tk.RIGHT, padx=(5, 0))
                            self.style_button(btn_b, "#444")
                            
                        tk.Label(fields_container, text="Destino Planilha Saída (.xlsx):", bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, pady=1)
                        f_fr_out = tk.Frame(fields_container, bg=BG_PRIMARY)
                        f_fr_out.pack(fill=tk.X, pady=1)
                        f_ent_out = tk.Entry(f_fr_out, textvariable=output_path_var)
                        f_ent_out.pack(side=tk.LEFT, fill=tk.X, expand=True)
                        self.style_entry(f_ent_out)
                        
                        def browse_save():
                            p = filedialog.asksaveasfilename(title="Salvar Planilha", defaultextension=".xlsx", filetypes=[("Excel Files", "*.xlsx")])
                            if p:
                                output_path_var.set(p)
                                
                        btn_s = tk.Button(f_fr_out, text="...", command=browse_save, width=3)
                        btn_s.pack(side=tk.RIGHT, padx=(5, 0))
                        self.style_button(btn_s, "#444")
                    else:
                        tk.Label(fields_container, text="Arquivo de Dados Local (opcional):", bg=BG_PRIMARY, fg=FG_PRIMARY).pack(anchor=tk.W, pady=3)
                        f_frame = tk.Frame(fields_container, bg=BG_PRIMARY)
                        f_frame.pack(fill=tk.X, pady=2)
                        f_entry = tk.Entry(f_frame, textvariable=file_path_var)
                        f_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
                        self.style_entry(f_entry)
                        btn_brs = tk.Button(f_frame, text="...", command=lambda: browse_file(file_path_var), width=3)
                        btn_brs.pack(side=tk.RIGHT, padx=(5, 0))
                        self.style_button(btn_brs, "#444")

            type_var.trace_add("write", draw_dynamic_fields)
            draw_dynamic_fields()

            # Salva
            def save_inner():
                try:
                    action.type = type_var.get()
                    if action.type == Action.TYPE_CLICK:
                        action.x = int(x_var.get())
                        action.y = int(y_var.get())
                        action.button = button_var.get()
                    elif action.type == Action.TYPE_TYPE:
                        action.text = text_var.get()
                    elif action.type == Action.TYPE_WAIT:
                        action.duration = float(duration_var.get())
                    elif action.type == Action.TYPE_READ_FILE:
                        action.file_path = file_path_var.get()
                        action.read_mode = read_mode_var.get()
                        action.file_selector = file_selector_var.get()
                    elif action.type == Action.TYPE_SCROLL:
                        action.dx = int(dx_var.get())
                        action.dy = int(dy_var.get())
                    elif action.type == Action.TYPE_AI:
                        action.ai_task = ai_task_var.get()
                        action.ai_mode = ai_mode_var.get()
                        action.file_path = file_path_var.get()
                        action.file_path_2 = file_path_2_var.get()
                        action.file_path_3 = file_path_3_var.get()
                        action.output_path = output_path_var.get()
                        
                    if is_new:
                        if insert_idx is not None:
                            actions.insert(insert_idx, action)
                        else:
                            actions.append(action)
                            
                    populate_steps()
                    dlg.destroy()
                except Exception as e:
                    messagebox.showerror("Erro de Validação", f"Erro nos dados inseridos: {e}", parent=dlg)

            btn_save_step = tk.Button(dlg, text="Salvar Passo", font=("Arial", 10, "bold"), command=save_inner, height=2)
            btn_save_step.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=15)
            self.style_button(btn_save_step, COLOR_GREEN, "#1FA598")

        # Funções de inserção de passos
        def get_insert_idx():
            idx = get_selected_action_idx()
            return idx + 1 if idx is not None else len(actions)

        def add_click_step():
            open_action_editor(Action(Action.TYPE_CLICK, x=0, y=0), is_new=True, insert_idx=get_insert_idx())

        def add_type_step():
            open_action_editor(Action(Action.TYPE_TYPE, text=""), is_new=True, insert_idx=get_insert_idx())

        def add_wait_step():
            open_action_editor(Action(Action.TYPE_WAIT, duration=1.0), is_new=True, insert_idx=get_insert_idx())

        def add_read_step():
            open_action_editor(Action(Action.TYPE_READ_FILE, file_path=""), is_new=True, insert_idx=get_insert_idx())

        def add_scroll_step():
            open_action_editor(Action(Action.TYPE_SCROLL, dx=0, dy=0), is_new=True, insert_idx=get_insert_idx())

        def add_ai_step():
            open_action_editor(Action(Action.TYPE_AI, ai_task=""), is_new=True, insert_idx=get_insert_idx())

        def edit_step():
            idx = get_selected_action_idx()
            if idx is not None:
                open_action_editor(actions[idx], is_new=False, insert_idx=idx)

        # Preenche os botões superiores (Ações no passo selecionado)
        tk.Button(ops_frame, text="✏ Editar", command=edit_step, font=("Arial", 8, "bold"), width=8, bg="#444", fg="white").pack(side=tk.LEFT, padx=3)
        tk.Button(ops_frame, text="🗑 Excluir", command=delete_step, font=("Arial", 8, "bold"), width=8, bg=COLOR_RED, fg="white").pack(side=tk.LEFT, padx=3)
        tk.Button(ops_frame, text="📋 Duplicar", command=duplicate_step, font=("Arial", 8, "bold"), width=9, bg="#444", fg="white").pack(side=tk.LEFT, padx=3)
        tk.Button(ops_frame, text="↑ Subir", command=move_up, font=("Arial", 8, "bold"), width=7, bg="#444", fg="white").pack(side=tk.LEFT, padx=3)
        tk.Button(ops_frame, text="↓ Descer", command=move_down, font=("Arial", 8, "bold"), width=7, bg="#444", fg="white").pack(side=tk.LEFT, padx=3)

        # Preenche os botões inferiores (Adicionar novos passos)
        tk.Button(btn_grid_frame, text="+ Clique", command=add_click_step, font=("Arial", 8, "bold"), bg=COLOR_GREEN, fg="white", width=9).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_grid_frame, text="+ Digitar", command=add_type_step, font=("Arial", 8, "bold"), bg=COLOR_TEAL, fg="white", width=9).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_grid_frame, text="+ Espera", command=add_wait_step, font=("Arial", 8, "bold"), bg=COLOR_ORANGE, fg="white", width=9).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_grid_frame, text="+ LerArq", command=add_read_step, font=("Arial", 8, "bold"), bg="#6F42C1", fg="white", width=9).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_grid_frame, text="+ Rolar", command=add_scroll_step, font=("Arial", 8, "bold"), bg="#E83E8C", fg="white", width=9).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_grid_frame, text="+ Passo IA", command=add_ai_step, font=("Arial", 8, "bold"), bg="#FD7E14", fg="white", width=11).pack(side=tk.LEFT, padx=2)

        # Salvar Alterações Gerais do Editor
        def save_editor_changes():
            new_name = name_var.get().strip() or record["name"]
            desc = desc_var.get().strip()
            clicks_data = [a.to_dict() for a in actions]
            
            if self.db.update_recording(record["name"], new_name=new_name, clicks=clicks_data, description=desc):
                self.load_recordings()
                self.recorder_status_var.set(f"Automação '{new_name}' editada com sucesso!")
                editor.destroy()
            else:
                messagebox.showerror("Erro", "Erro ao salvar alterações no banco de dados.", parent=editor)

        btn_save_all = tk.Button(editor, text="Salvar Todas as Alterações", font=("Arial", 11, "bold"), command=save_editor_changes, height=2)
        btn_save_all.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=20)
        self.style_button(btn_save_all, COLOR_GREEN, "#1FA598")

    # ----------------------------------------------------
    # Selenium Webdriver Manual Controls
    # ----------------------------------------------------
    def open_selenium(self):
        """Abre caixa de diálogo para iniciar o Selenium Chrome webdriver."""
        url = simpledialog.askstring("Abrir Navegador", "URL Inicial:", initialvalue="https://www.google.com", parent=self.root)
        if not url:
            return
            
        self.recorder_status_var.set("Iniciando navegador automatizado Chrome...")
        
        def run_browser():
            try:
                from selenium import webdriver
                self.selenium_driver = webdriver.Chrome()
                self.selenium_driver.get(url)
                self.schedule_gui_update(self.recorder_status_var.set, f"Navegador aberto em: {url}")
            except Exception as e:
                self.schedule_gui_update(messagebox.showerror, "Erro Selenium", f"Não foi possível abrir o navegador Chrome: {e}")
                self.schedule_gui_update(self.recorder_status_var.set, "Erro ao iniciar Selenium.")

        threading.Thread(target=run_browser, daemon=True).start()

    # ----------------------------------------------------
    # Chat e Comunicação com o Agente
    # ----------------------------------------------------
    def append_chat_message(self, sender, text):
        """Insere mensagens formatadas em balões na caixa de chat (Thread-safe)."""
        self.chat_history.config(state=tk.NORMAL)
        
        if sender == "Você":
            self.chat_history.insert(tk.END, "[Você]\n", "user")
            self.chat_history.insert(tk.END, f"{text}\n\n", "text_user")
            self.chat_history_list.append({"role": "user", "content": text})
        elif sender == "Agente":
            self.chat_history.insert(tk.END, "[Agente IA]\n", "agent")
            self.chat_history.insert(tk.END, f"{text}\n\n", "text_agent")
            self.chat_history_list.append({"role": "assistant", "content": text})
        else:
            self.chat_history.insert(tk.END, f"[{sender}]\n", "system")
            self.chat_history.insert(tk.END, f"{text}\n\n", "text_system")
            
        self.chat_history.see(tk.END)
        self.chat_history.config(state=tk.DISABLED)

    def send_user_message(self):
        msg = self.chat_input.get().strip()
        if not msg:
            return
            
        self.chat_input.delete(0, tk.END)
        self.append_chat_message("Você", msg)
        
        # Se o agente IA estiver rodando e aguardando resposta
        if self.agent_active and not self.user_message_event.is_set():
            self.last_user_message = msg
            self.user_message_event.set()
        else:
            # Caso contrário, inicia uma nova tarefa autônoma baseada no prompt digitado
            if not self.playing:
                self.playing = True
                self.btn_execute.config(state=tk.DISABLED)
                self.btn_stop_exec.config(state=tk.NORMAL)
                self.style_button(self.btn_stop_exec, COLOR_RED, "#D84A4F")
                
                # Executa o despachante na thread secundária
                threading.Thread(target=self.run_agent_callback_dispatch, args=(msg,), daemon=True).start()
            else:
                self.append_chat_message("Sistema", "Uma tarefa ou automação já está ativa. Aguarde ou clique em Parar.")

    def ask_user_confirmation_gui(self, title, message):
        """Pede confirmação do usuário (Thread-safe). Retorna True/False."""
        done = threading.Event()
        result = {"value": False}

        def ask():
            try:
                # Restaura a janela se estiver minimizada para chamar atenção
                if self.root.state() == "iconic":
                    self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
                result["value"] = messagebox.askyesno(title, message, parent=self.root)
            finally:
                done.set()

        self.schedule_gui_update(ask)
        done.wait()
        return result["value"]

    # ----------------------------------------------------
    # Despachante e Loop de Agentes de IA
    # ----------------------------------------------------
    def run_agent_callback_dispatch(self, task_description, ai_mode="ocr", file_path="", file_path_2="", file_path_3="", output_path=""):
        """Despacha a tarefa do agente de IA com base no modo solicitado."""
        api_key = self.db.get_setting("openai_api_key", "").strip()
        api_url = self.db.get_setting("agent_api_url", "https://api.openai.com/v1").strip()
        model_name = self.db.get_setting("agent_ocr_model", "gpt-4o").strip()
        
        if not api_key:
            self.schedule_gui_update(self.append_chat_message, "Sistema", "Erro: API Key não configurada nas Configurações.")
            self.schedule_gui_update(self.on_playback_finished)
            return

        self.agent_active = True
        self.schedule_gui_update(self.agent_status_var.set, "Status: Pensando...")

        # 1. Pré-Verificação Conversacional (Conversa amigável livre)
        is_conv = False
        try:
            # Obtém histórico das gravações
            recs = self.db.get_all_recordings()
            rec_context = "=== AUTOMACÕES SALVAS NO SISTEMA ===\n"
            for r in recs:
                steps = 0
                try:
                    steps = len(json.loads(r['clicks_data']))
                except: pass
                rec_context += f"- '{r['name']}' ({steps} passos)\n"
            rec_context += "===================================\n\n"

            recent_chat = self.chat_history_list[-8:]
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Você é o robô ClickRecorder RPA Pro.\n"
                        f"{rec_context}"
                        "Determine se a última mensagem do usuário é apenas uma interação social/conversa amigável "
                        "(ex: saudações, perguntas de como funciona, ajuda teórica) ou se é uma ordem explícita para interagir fisicamente "
                        "com a tela (ex: cliques, automação, comandos, consolidar planilhas).\n"
                        "Se for APENAS conversacional, responda como JSON puro:\n"
                        "{\"is_conversational\": true, \"response\": \"Sua resposta natural em português\"}\n"
                        "Se exigir automação física na tela, responda:\n"
                        "{\"is_conversational\": false, \"response\": \"\"}"
                    )
                }
            ]
            for m in recent_chat[:-1]:
                messages.append({"role": m["role"], "content": m["content"]})
            messages.append({"role": "user", "content": task_description})

            payload = {
                "model": "gpt-4o-mini",
                "response_format": {"type": "json_object"},
                "messages": messages,
                "temperature": 0.4
            }
            res = requests.post(f"{api_url}/chat/completions", headers={"Authorization": f"Bearer {api_key}"}, json=payload, timeout=15)
            res.raise_for_status()
            choice = json.loads(res.json()['choices'][0]['message']['content'].strip())
            
            if choice.get("is_conversational", False):
                self.schedule_gui_update(self.append_chat_message, "Agente", choice.get("response", ""))
                is_conv = True
        except Exception as e:
            print(f"[CONV WARN] Falha na triagem de chat: {e}")

        if is_conv:
            self.agent_active = False
            self.schedule_gui_update(self.agent_status_var.set, "Status: Inativo")
            self.schedule_gui_update(self.on_playback_finished)
            return

        # Minimiza a janela principal se configurado
        minimized = False
        if self.minimize_var.get():
            self.schedule_gui_update(self.root.iconify)
            time.sleep(0.6)
            minimized = True

        # Callback auxiliar para parar execução
        def check_stop():
            return not self.playing

        # Callback para pegar histórico do chat
        def get_chat():
            return self.chat_history_list[-8:] if self.chat_history_list else []

        # Callback para esperar resposta do usuário no chat
        def wait_for_user():
            self.user_message_event.clear()
            self.user_message_event.wait()
            if not self.playing:
                return ""
            return self.last_user_message

        # Conteúdo do arquivo 1 opcional
        file_content_1 = ""
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    file_content_1 = f.read(2000)
            except: pass

        # Direciona
        try:
            if ai_mode == "excel_merge":
                self.schedule_gui_update(self.agent_status_var.set, "Status: Mesclando Excel...")
                merge_files_to_excel(
                    task_description=task_description,
                    api_key=api_key,
                    api_url=api_url,
                    model_name=model_name,
                    file_path_1=file_path,
                    file_path_2=file_path_2,
                    file_path_3=file_path_3,
                    output_path=output_path,
                    chat_callback=lambda s, t: self.schedule_gui_update(self.append_chat_message, s, t),
                    status_callback=lambda text: self.schedule_gui_update(self.agent_status_var.set, text)
                )
            elif ai_mode == "selenium":
                if not self.selenium_driver:
                    self.schedule_gui_update(self.append_chat_message, "Sistema", "Erro: Navegador automatizado não está ativo. Abra-o primeiro.")
                else:
                    agent = AutonomousSeleniumAgent(
                        db_manager=self.db,
                        driver=self.selenium_driver,
                        chat_callback=lambda s, t: self.schedule_gui_update(self.append_chat_message, s, t),
                        status_callback=lambda text: self.schedule_gui_update(self.agent_status_var.set, text),
                        confirm_action_callback=self.ask_user_confirmation_gui
                    )
                    agent.run_agent_loop(task_description, check_stop, get_chat, file_content_1, wait_for_user_callback=wait_for_user)
            else: # ocr
                agent = AutonomousVisualAgent(
                    db_manager=self.db,
                    chat_callback=lambda s, t: self.schedule_gui_update(self.append_chat_message, s, t),
                    status_callback=lambda text: self.schedule_gui_update(self.agent_status_var.set, text),
                    confirm_action_callback=self.ask_user_confirmation_gui
                )
                agent.run_agent_loop(task_description, check_stop, get_chat, file_content_1, wait_for_user_callback=wait_for_user)
                
        except Exception as ex:
            self.schedule_gui_update(self.append_chat_message, "Sistema", f"Erro no Agente: {ex}")
        finally:
            if minimized:
                self.schedule_gui_update(self.root.deiconify)
                self.schedule_gui_update(self.root.lift)
                self.schedule_gui_update(self.root.focus_force)
            
            self.agent_active = False
            self.schedule_gui_update(self.agent_status_var.set, "Status: Inativo")
            self.schedule_gui_update(self.on_playback_finished)
