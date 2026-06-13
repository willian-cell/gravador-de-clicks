import sys
import os

# Garante que a pasta src está no path de importação
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    import ctypes
    try:
        # Habilita DPI awareness para Windows Vista / 7 / 8 / 10 / 11
        # Isso garante que as capturas e coordenadas coincidam com precisão milimétrica.
        ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    import tkinter as tk
    from src.gui import ClickRecorderApp
    
    root = tk.Tk()
    app = ClickRecorderApp(root)
    root.mainloop()
