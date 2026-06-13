import sqlite3
import json
import os
import shutil
from datetime import datetime
from src.config import DEFAULT_DB_PATH, Action

class DatabaseManager:
    """Gerencia a persistência de gravações, configurações globais e perfis de IA (skills)."""
    
    def __init__(self, db_path=None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.backup_database()
        self.init_database()
    
    def backup_database(self):
        """Cria um backup de segurança do banco antes de iniciar."""
        try:
            if os.path.exists(self.db_path):
                backup_path = self.db_path + ".bak"
                shutil.copy2(self.db_path, backup_path)
        except Exception as e:
            print(f"[DB WARN] Falha ao criar backup do banco: {e}")

    def init_database(self):
        """Inicializa o banco de dados SQLite com schema e migrações."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Habilita o modo WAL (Write-Ahead Logging) para concorrência segura em threads
                conn.execute("PRAGMA journal_mode=WAL")
                cursor = conn.cursor()
                
                # Tabela de automações/gravações
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS recordings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        clicks_data TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        description TEXT,
                        last_run_at TIMESTAMP,
                        run_count INTEGER DEFAULT 0
                    )
                """)
                
                # Tabela de configurações globais
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)
                
                # Tabela de perfis de IA / Skills
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS skills (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        prompt TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Migrações seguras (caso colunas não existam em bancos de dados antigos)
                cursor.execute("PRAGMA table_info(recordings)")
                columns = [col[1] for col in cursor.fetchall()]
                
                migrations = [
                    ("description", "ALTER TABLE recordings ADD COLUMN description TEXT"),
                    ("last_run_at", "ALTER TABLE recordings ADD COLUMN last_run_at TIMESTAMP"),
                    ("run_count", "ALTER TABLE recordings ADD COLUMN run_count INTEGER DEFAULT 0"),
                    ("updated_at", "ALTER TABLE recordings ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                ]
                
                for col_name, alter_query in migrations:
                    if col_name not in columns:
                        cursor.execute(alter_query)
                
                # Semeia skills padrões caso a tabela esteja vazia
                cursor.execute("SELECT COUNT(*) FROM skills")
                if cursor.fetchone()[0] == 0:
                    default_skills = [
                        ("Disparador WhatsApp", "Você é um especialista em disparar mensagens do WhatsApp. Encontre o campo de busca de contatos, procure pelo contato correto, clique na conversa, escreva a mensagem e envie."),
                        ("Mesclador de Notas Fiscais", "Você é um especialista em consolidar dados de notas fiscais. Extraia informações relevantes como data, valor, CNPJ, cliente e crie uma planilha formatada."),
                        ("Preenchedor de Cadastro", "Você é um especialista em preenchimento de cadastros. Encontre os campos de formulário como Nome, CPF, Endereço, insira os dados correspondentes da fonte e clique em salvar.")
                    ]
                    cursor.executemany("INSERT INTO skills (name, prompt) VALUES (?, ?)", default_skills)
                
                conn.commit()
        except Exception as e:
            print(f"[DB ERROR] Erro crítico ao inicializar o banco de dados: {e}")

    def get_setting(self, key, default=""):
        """Recupera uma configuração global do banco."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
                row = cursor.fetchone()
                return row[0] if row else default
        except Exception as e:
            print(f"[DB WARN] Erro ao recuperar configuração '{key}': {e}")
            return default

    def set_setting(self, key, value):
        """Salva ou atualiza uma configuração global no banco."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
                conn.commit()
            return True
        except Exception as e:
            print(f"[DB ERROR] Erro ao salvar configuração '{key}': {e}")
            return False

    def add_recording(self, name, clicks, description=""):
        """Adiciona uma nova gravação/automação ao banco de dados."""
        try:
            # Converte objetos Action para dicionários e gera JSON
            if clicks and isinstance(clicks[0], Action):
                clicks_json = json.dumps([action.to_dict() for action in clicks])
            else:
                clicks_json = json.dumps(clicks)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO recordings (name, clicks_data, description, created_at, updated_at, run_count)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0)
                """, (name, clicks_json, description))
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            raise ValueError(f"A gravação '{name}' já existe.")
        except Exception as e:
            print(f"[DB ERROR] Erro ao adicionar gravação '{name}': {e}")
            return False

    def get_all_recordings(self):
        """Retorna todas as gravações salvas ordenadas pela data de criação decrescente."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, name, clicks_data, created_at, updated_at, description, last_run_at, run_count 
                    FROM recordings ORDER BY created_at DESC
                """)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            print(f"[DB ERROR] Erro ao obter lista de gravações: {e}")
            return []

    def get_recording(self, name):
        """Retorna uma automação específica pelo nome."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, name, clicks_data, created_at, updated_at, description, last_run_at, run_count 
                    FROM recordings WHERE name = ?
                """, (name,))
                row = cursor.fetchone()
                if row:
                    record = dict(row)
                    record['clicks'] = json.loads(record['clicks_data'])
                    return record
                return None
        except Exception as e:
            print(f"[DB ERROR] Erro ao carregar gravação '{name}': {e}")
            return None

    def update_recording(self, name, new_name=None, clicks=None, description=None):
        """Atualiza dados estruturais de uma gravação."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                fields = []
                params = []
                
                if new_name is not None:
                    fields.append("name = ?")
                    params.append(new_name)
                if clicks is not None:
                    if clicks and isinstance(clicks[0], Action):
                        clicks_json = json.dumps([action.to_dict() for action in clicks])
                    else:
                        clicks_json = json.dumps(clicks)
                    fields.append("clicks_data = ?")
                    params.append(clicks_json)
                if description is not None:
                    fields.append("description = ?")
                    params.append(description)
                
                if not fields:
                    return True
                
                fields.append("updated_at = CURRENT_TIMESTAMP")
                params.append(name)
                
                query = f"UPDATE recordings SET {', '.join(fields)} WHERE name = ?"
                cursor.execute(query, params)
                conn.commit()
            return True
        except Exception as e:
            print(f"[DB ERROR] Erro ao atualizar gravação '{name}': {e}")
            return False

    def delete_recording(self, name):
        """Remove permanentemente uma gravação do banco de dados."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM recordings WHERE name = ?", (name,))
                conn.commit()
            return True
        except Exception as e:
            print(f"[DB ERROR] Erro ao deletar gravação '{name}': {e}")
            return False

    def increment_run_count(self, name):
        """Incrementa o contador de uso e salva o timestamp do último uso da gravação."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE recordings 
                    SET run_count = COALESCE(run_count, 0) + 1, last_run_at = CURRENT_TIMESTAMP
                    WHERE name = ?
                """, (name,))
                conn.commit()
            return True
        except Exception as e:
            print(f"[DB ERROR] Erro ao incrementar execução de '{name}': {e}")
            return False

    def get_all_skills(self):
        """Retorna todos os perfis de IA (skills)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT id, name, prompt FROM skills ORDER BY name ASC")
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            print(f"[DB ERROR] Erro ao carregar perfis de IA: {e}")
            return []

    def add_skill(self, name, prompt):
        """Adiciona ou atualiza uma skill/perfil de IA."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO skills (name, prompt)
                    VALUES (?, ?)
                """, (name, prompt))
                conn.commit()
            return True
        except Exception as e:
            print(f"[DB ERROR] Erro ao salvar perfil de IA '{name}': {e}")
            return False

    def delete_skill(self, name):
        """Remove um perfil de IA pelo nome."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM skills WHERE name = ?", (name,))
                conn.commit()
            return True
        except Exception as e:
            print(f"[DB ERROR] Erro ao deletar perfil de IA '{name}': {e}")
            return False
