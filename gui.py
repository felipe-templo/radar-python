"""Interface grafica do Radar de Ofertas Mercado Livre, Shopee e Amazon.

Controla o mesmo loop de `src/radar/scheduler.py` (conectar ao Chrome via
CDP, rodar ciclo, aguardar) a partir de uma janela com botao iniciar/parar,
intervalo configuravel e log ao vivo. Nao substitui `main.py` (CLI) - e so
outra forma de rodar o mesmo bot.
"""

import logging
import math
import queue
import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import customtkinter as ctk

from radar.browser import connect_to_chrome
from radar.config import load_settings
from radar.dedup import DedupRepository
from radar.exceptions import ChromeNotConnectableError
from radar.logging_setup import setup_logging
from radar.queue_repo import OfferQueue
from radar.scheduler import run_all_sites
from radar.sites import SITES_BY_KEY
from radar.telegram_client import TelegramClient

DEFAULT_INTERVAL_HOURS = 4
SITE_MENU_OPTIONS = {
    "Mercado Livre": ["ml"],
    "Shopee": ["shopee"],
    "Amazon": ["amazon"],
    "Todos": ["ml", "shopee", "amazon"],
}
MAX_RECONNECT_BEFORE_LONG_WAIT = 5
LONG_WAIT_SECONDS = 900

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORS = {
    "bg": "#14161b",
    "surface_1": "#1c1f26",
    "surface_2": "#242832",
    "border": "#2e333d",
    "accent": "#5b8cff",
    "accent_hover": "#4a76e0",
    "success": "#3ddc84",
    "success_hover": "#2fb46c",
    "warning": "#f5a623",
    "danger": "#ef4444",
    "danger_hover": "#c93838",
    "muted": "#7b8394",
    "text_primary": "#eef1f6",
    "text_secondary": "#9aa2b1",
}

FONT_TITLE = ("Segoe UI", 22, "bold")
FONT_SUBTITLE = ("Segoe UI", 13, "normal")
FONT_SECTION = ("Segoe UI", 12, "bold")
FONT_BODY = ("Segoe UI", 13, "normal")
FONT_MONO = ("Consolas", 12, "normal")

_LEVEL_RE = re.compile(r"\[(\w+)\]")


def _blend(color_a: str, color_b: str, t: float) -> str:
    """Interpola linear entre duas cores hex #RRGGBB, t em [0, 1]."""
    ra, ga, ba = int(color_a[1:3], 16), int(color_a[3:5], 16), int(color_a[5:7], 16)
    rb, gb, bb = int(color_b[1:3], 16), int(color_b[3:5], 16), int(color_b[5:7], 16)
    r = int(ra + (rb - ra) * t)
    g = int(ga + (gb - ga) * t)
    b = int(ba + (bb - ba) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


class QueueLogHandler(logging.Handler):
    """Manda cada linha de log pra uma queue thread-safe, lida pela GUI."""

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        self.log_queue.put(self.format(record))


class RadarWorker:
    """Roda o loop do bot numa thread separada, parável via stop_event."""

    def __init__(self, log_queue: queue.Queue, on_state_change):
        self.log_queue = log_queue
        self.on_state_change = on_state_change
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.next_run_at: float | None = None

    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, interval_seconds: int, sites: list) -> None:
        if self.is_running():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run, args=(interval_seconds, sites), daemon=True
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def _run(self, interval_seconds: int, sites: list) -> None:
        logger = logging.getLogger("radar.gui")
        settings = load_settings()
        pw = browser = context = None
        reconnect_attempts = 0
        dedup = DedupRepository(settings.db_path)
        queue = OfferQueue(settings.db_path)
        telegram = TelegramClient(settings.telegram_bot_token, settings.telegram_chat_id)

        self.on_state_change("running")
        try:
            while not self.stop_event.is_set():
                try:
                    if browser is None or not browser.is_connected():
                        if pw:
                            pw.stop()
                        pw, browser, context = connect_to_chrome(settings.chrome_debug_url)
                        reconnect_attempts = 0

                    run_all_sites(settings, context, dedup, telegram, queue, sites)

                except ChromeNotConnectableError as exc:
                    reconnect_attempts += 1
                    logger.error("Chrome nao conectavel (tentativa %d): %s", reconnect_attempts, exc)
                    browser = None
                    if reconnect_attempts >= MAX_RECONNECT_BEFORE_LONG_WAIT:
                        telegram.send_alert(
                            settings.telegram_admin_chat_id,
                            f"Radar: Chrome inacessivel apos {reconnect_attempts} tentativas.",
                        )
                        self.next_run_at = time.time() + LONG_WAIT_SECONDS
                        self.stop_event.wait(LONG_WAIT_SECONDS)
                        continue
                except Exception:
                    logger.exception("Erro inesperado no ciclo")
                    telegram.send_alert(
                        settings.telegram_admin_chat_id,
                        "Radar: erro inesperado no ciclo, verificar logs/radar.log",
                    )

                self.next_run_at = time.time() + interval_seconds
                self.stop_event.wait(interval_seconds)
        finally:
            if pw:
                pw.stop()
            self.next_run_at = None
            self.on_state_change("stopped")


class RadarApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Radar de Ofertas")
        self.geometry("760x640")
        self.minsize(640, 520)
        self.configure(fg_color=COLORS["bg"])

        self.log_queue: queue.Queue = queue.Queue()
        self.worker = RadarWorker(self.log_queue, self._on_state_change)
        self._pulse_job: str | None = None
        self._pulse_t = 0.0
        self._build_layout()

        setup_logging(level="INFO")
        logging.getLogger().addHandler(self._make_handler())

        self.after(200, self._poll_log_queue)
        self.after(1000, self._tick_countdown)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _make_handler(self) -> QueueLogHandler:
        handler = QueueLogHandler(self.log_queue)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
        return handler

    def _build_layout(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 8))

        ctk.CTkLabel(
            header, text="📡 Radar de Ofertas", font=ctk.CTkFont(*FONT_TITLE),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            header, text="Mercado Livre, Shopee e Amazon -> Telegram",
            font=ctk.CTkFont(*FONT_SUBTITLE), text_color=COLORS["text_secondary"],
        ).pack(anchor="w")

        status_card = ctk.CTkFrame(
            self, fg_color=COLORS["surface_1"], corner_radius=16,
            border_width=1, border_color=COLORS["border"],
        )
        status_card.pack(fill="x", padx=24, pady=8)

        ctk.CTkLabel(
            status_card, text="Status", font=ctk.CTkFont(*FONT_SECTION),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", padx=18, pady=(14, 0))

        status_row = ctk.CTkFrame(status_card, fg_color="transparent")
        status_row.pack(fill="x", padx=18, pady=(6, 6))

        self.status_dot = ctk.CTkLabel(status_row, text="●", text_color=COLORS["muted"], font=ctk.CTkFont(size=20))
        self.status_dot.pack(side="left")
        self.status_label = ctk.CTkLabel(
            status_row, text="Parado", font=ctk.CTkFont(*FONT_SECTION), text_color=COLORS["text_primary"],
        )
        self.status_label.pack(side="left", padx=(6, 0))

        self.countdown_label = ctk.CTkLabel(
            status_card, text="Proxima verificacao: --:--:--",
            text_color=COLORS["text_secondary"], font=ctk.CTkFont(family="Consolas", size=13),
        )
        self.countdown_label.pack(anchor="w", padx=18, pady=(0, 16))

        controls_card = ctk.CTkFrame(
            self, fg_color=COLORS["surface_1"], corner_radius=16,
            border_width=1, border_color=COLORS["border"],
        )
        controls_card.pack(fill="x", padx=24, pady=8)

        ctk.CTkLabel(
            controls_card, text="Configuracao", font=ctk.CTkFont(*FONT_SECTION),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", padx=18, pady=(14, 0))

        site_row = ctk.CTkFrame(controls_card, fg_color="transparent")
        site_row.pack(fill="x", padx=18, pady=(10, 0))

        ctk.CTkLabel(site_row, text="Site", font=ctk.CTkFont(*FONT_BODY), text_color=COLORS["text_primary"]).pack(side="left")
        self.site_selector = ctk.CTkSegmentedButton(
            site_row, values=list(SITE_MENU_OPTIONS.keys()),
            selected_color=COLORS["accent"], selected_hover_color=COLORS["accent_hover"],
            unselected_color=COLORS["surface_2"], unselected_hover_color=COLORS["surface_2"],
        )
        self.site_selector.set("Mercado Livre")
        self.site_selector.pack(side="left", padx=(8, 0))

        row = ctk.CTkFrame(controls_card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=16)

        ctk.CTkLabel(row, text="Intervalo (horas)", font=ctk.CTkFont(*FONT_BODY), text_color=COLORS["text_primary"]).pack(side="left")
        self.interval_entry = ctk.CTkEntry(
            row, width=60, justify="center", fg_color=COLORS["surface_2"],
            border_color=COLORS["border"], border_width=1, corner_radius=8,
        )
        self.interval_entry.insert(0, str(DEFAULT_INTERVAL_HOURS))
        self.interval_entry.pack(side="left", padx=(8, 24))

        self.toggle_button = ctk.CTkButton(
            row, text="Iniciar", width=110, corner_radius=10,
            fg_color=COLORS["success"], hover_color=COLORS["success_hover"],
            text_color="#0e1512", font=ctk.CTkFont(*FONT_SECTION),
            command=self._toggle,
        )
        self.toggle_button.pack(side="right")

        log_card = ctk.CTkFrame(
            self, fg_color=COLORS["surface_1"], corner_radius=16,
            border_width=1, border_color=COLORS["border"],
        )
        log_card.pack(fill="both", expand=True, padx=24, pady=(8, 20))

        ctk.CTkLabel(
            log_card, text="Log", font=ctk.CTkFont(*FONT_SECTION), text_color=COLORS["text_secondary"],
        ).pack(anchor="w", padx=18, pady=(14, 0))
        self.log_box = ctk.CTkTextbox(
            log_card, fg_color=COLORS["bg"], corner_radius=10,
            border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(*FONT_MONO),
        )
        self.log_box.pack(fill="both", expand=True, padx=18, pady=(8, 16))
        self.log_box.configure(state="disabled")
        self.log_box.tag_config("INFO", foreground=COLORS["text_secondary"])
        self.log_box.tag_config("WARNING", foreground=COLORS["warning"])
        self.log_box.tag_config("ERROR", foreground=COLORS["danger"])
        self.log_box.tag_config("CRITICAL", foreground=COLORS["danger"])

    def _toggle(self):
        if self.worker.is_running():
            self.worker.stop()
            self.toggle_button.configure(text="Parando...", state="disabled")
        else:
            try:
                hours = float(self.interval_entry.get().replace(",", "."))
                if hours <= 0:
                    raise ValueError
            except ValueError:
                self._append_log("Intervalo invalido - use um numero maior que 0.")
                return
            interval_seconds = int(hours * 3600)
            site_keys = SITE_MENU_OPTIONS[self.site_selector.get()]
            sites = [SITES_BY_KEY[key] for key in site_keys]
            self.interval_entry.configure(state="disabled")
            self.site_selector.configure(state="disabled")
            self.worker.start(interval_seconds, sites)

    def _on_state_change(self, state: str):
        self.after(0, lambda: self._apply_state(state))

    def _apply_state(self, state: str):
        if state == "running":
            self.status_label.configure(text="Rodando")
            self.toggle_button.configure(text="Parar", state="normal")
            self._animate_color(self.toggle_button, "fg_color", COLORS["success"], COLORS["danger"])
            self._animate_color(self.toggle_button, "hover_color", COLORS["success_hover"], COLORS["danger_hover"])
            self._start_pulse()
        else:
            self._stop_pulse()
            self.status_dot.configure(text_color=COLORS["muted"])
            self.status_label.configure(text="Parado")
            self.countdown_label.configure(text="Proxima verificacao: --:--:--")
            self.toggle_button.configure(text="Iniciar", state="normal")
            self._animate_color(self.toggle_button, "fg_color", COLORS["danger"], COLORS["success"])
            self._animate_color(self.toggle_button, "hover_color", COLORS["danger_hover"], COLORS["success_hover"])
            self.interval_entry.configure(state="normal")
            self.site_selector.configure(state="normal")

    def _start_pulse(self):
        if self._pulse_job is not None:
            return
        self._pulse_t = 0.0
        self._pulse_status_dot()

    def _stop_pulse(self):
        if self._pulse_job is not None:
            self.after_cancel(self._pulse_job)
            self._pulse_job = None

    def _pulse_status_dot(self):
        self._pulse_t += 0.12
        factor = (math.sin(self._pulse_t) + 1) / 2
        color = _blend(COLORS["success_hover"], COLORS["success"], factor)
        self.status_dot.configure(text_color=color)
        self._pulse_job = self.after(50, self._pulse_status_dot)

    def _animate_color(self, widget, option: str, start_hex: str, end_hex: str, steps: int = 8, delay: int = 25, i: int = 0):
        t = i / steps
        widget.configure(**{option: _blend(start_hex, end_hex, t)})
        if i < steps:
            self.after(delay, lambda: self._animate_color(widget, option, start_hex, end_hex, steps, delay, i + 1))

    def _tick_countdown(self):
        if self.worker.is_running() and self.worker.next_run_at:
            remaining = max(0, int(self.worker.next_run_at - time.time()))
            h, rem = divmod(remaining, 3600)
            m, s = divmod(rem, 60)
            self.countdown_label.configure(text=f"Proxima verificacao: {h:02d}:{m:02d}:{s:02d}")
        self.after(1000, self._tick_countdown)

    def _poll_log_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        self.after(200, self._poll_log_queue)

    def _append_log(self, line: str):
        match = _LEVEL_RE.search(line)
        level = match.group(1) if match else "INFO"
        tag = level if level in ("INFO", "WARNING", "ERROR", "CRITICAL") else "INFO"

        self.log_box.configure(state="normal")
        start = self.log_box.index("end")
        self.log_box.insert("end", line + "\n")
        self.log_box.tag_add(tag, start, "end")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _on_close(self):
        self.worker.stop()
        self.destroy()


if __name__ == "__main__":
    app = RadarApp()
    app.mainloop()
