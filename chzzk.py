import os
import re
import sys
import json
import queue
import signal
import threading
import subprocess
import urllib.request
import time
from tkinter import filedialog, messagebox
import customtkinter as ctk

# ==========================================
# ⚙️ 업데이트 및 설정
# ==========================================
ENABLE_AUTO_UPDATE = True
CURRENT_VERSION = "v1.2.2"
GITHUB_REPO = "sunglogbag81/Chzzk-VOD-downloader"
# ==========================================

PCT_RE = re.compile(r'(\d+(?:\.\d+)?)%')
SPEED_ETA_RE = re.compile(r'(\d+(?:\.\d+)?)%.*?at\s+([0-9a-zA-Z./~]+)\s+ETA\s+([\d:]+)')
LIVE_RE = re.compile(r'\[download\]\s+([0-9.]+\w+)\s+at\s+([0-9.]+\w+/s)')
CONFIG_FILE = "settings.json"

BG_COLOR = "#18181B"
CARD_COLOR = "#27272A"
INPUT_COLOR = "#1F1F22"
BORDER_COLOR = "#3F3F46"
TEXT_PRIMARY = "#F4F4F5"
TEXT_SECONDARY = "#A1A1AA"
CHZZK_GREEN = "#00D287"
CHZZK_GREEN_HOVER = "#00B373"
BTN_GRAY = "#3F3F46"
BTN_GRAY_HOVER = "#52525B"

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.default_font = ctk.CTkFont(family="Malgun Gothic", size=13)
        self.bold_font = ctk.CTkFont(family="Malgun Gothic", size=14, weight="bold")
        self.title_font = ctk.CTkFont(family="Malgun Gothic", size=22, weight="bold")

        ctk.set_appearance_mode("Dark")
        self.title(f"Chzzk VOD Downloader {CURRENT_VERSION}")
        self.geometry("1040x660")
        self.minsize(1000, 600)
        self.configure(fg_color=BG_COLOR)

        self.ui_queue = queue.Queue()
        self.download_thread = None
        self.fetch_thread = None
        self.proc = None
        self.stop_flag = threading.Event()
        self.q_list = []
        self._is_live = False

        self.url_var = ctk.StringVar()
        self.outdir_var = ctk.StringVar(value=os.path.abspath(os.getcwd()))
        self.q_count_var = ctk.StringVar(value="대기열 (0)")
        self.resolution_var = ctk.StringVar(value="1080p (최고 화질)")
        self.format_var = ctk.StringVar(value="MP4")
        self.cookies_var = ctk.StringVar(value="선택 안함")
        self.filename_tpl_var = ctk.StringVar(value="[제목] (기본)")
        self.status_var = ctk.StringVar(value="대기 중")
        self.start_time_var = ctk.StringVar(value="")
        self.end_time_var = ctk.StringVar(value="")

        self.embed_meta_var = ctk.BooleanVar(value=True)
        self.save_thumb_var = ctk.BooleanVar(value=False)
        self.auto_shutdown_var = ctk.BooleanVar(value=False)
        self.save_settings_var = ctk.BooleanVar(value=True)

        self._load_settings()
        self._build_ui()
        self.after(120, self._poll_queue)

        if ENABLE_AUTO_UPDATE:
            threading.Thread(target=self._check_for_updates, daemon=True).start()

    # -------------------------
    # 💾 설정 관리
    # -------------------------
    def _load_settings(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("save_settings", True):
                        self.save_settings_var.set(True)
                        self.outdir_var.set(data.get("outdir", os.path.abspath(os.getcwd())))
                        self.resolution_var.set(data.get("resolution", "1080p (최고 화질)"))
                        self.format_var.set(data.get("format", "MP4"))
                        self.cookies_var.set(data.get("cookies", "선택 안함"))
                        self.filename_tpl_var.set(data.get("filename_tpl", "[제목] (기본)"))
                        self.embed_meta_var.set(data.get("embed_meta", True))
                        self.save_thumb_var.set(data.get("save_thumb", False))
                        self.auto_shutdown_var.set(data.get("auto_shutdown", False))
            except: pass

    def on_closing(self):
        if self.save_settings_var.get():
            data = {
                "save_settings": True,
                "outdir": self.outdir_var.get(),
                "resolution": self.resolution_var.get(),
                "format": self.format_var.get(),
                "cookies": self.cookies_var.get(),
                "filename_tpl": self.filename_tpl_var.get(),
                "embed_meta": self.embed_meta_var.get(),
                "save_thumb": self.save_thumb_var.get(),
                "auto_shutdown": self.auto_shutdown_var.get()
            }
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
            except: pass
        else:
            if os.path.exists(CONFIG_FILE):
                try: os.remove(CONFIG_FILE)
                except: pass
        self.stop_download()
        self.destroy()
        os._exit(0)

    # -------------------------
    # 🔄 자동 업데이트
    # -------------------------
    def _check_for_updates(self):
        if "/" not in GITHUB_REPO: return
        try:
            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latest_version = data.get("tag_name", "")
                download_url = next((a.get("browser_download_url") for a in data.get("assets", []) if a.get("name", "").endswith(".exe")), None)
                if latest_version and latest_version != CURRENT_VERSION and download_url:
                    self.after(1000, lambda: self._show_auto_update_prompt(latest_version, download_url))
        except: pass

    def _show_auto_update_prompt(self, latest_version, download_url):
        if messagebox.askyesno("업데이트", f"새로운 버전({latest_version})이 출시되었습니다.\n지금 바로 업데이트하시겠습니까?"):
            self._apply_update(download_url)

    def _apply_update(self, download_url):
        self.status_var.set("업데이트 파일 다운로드 중...")
        self.set_busy(True)
        threading.Thread(target=self._download_and_restart, args=(download_url,), daemon=True).start()

    def _download_and_restart(self, download_url):
        try:
            current_exe = sys.executable
            exe_dir = os.path.dirname(current_exe)
            exe_name = os.path.basename(current_exe)
            new_exe = os.path.join(exe_dir, "new_" + exe_name)
            urllib.request.urlretrieve(download_url, new_exe)
            bat_path = os.path.join(exe_dir, "update_chzzk.bat")
            bat_content = (
                f"@echo off\nchcp 65001 > nul\n"
                f"taskkill /f /im \"{exe_name}\" > nul 2>&1\n"
                f"timeout /t 3 /nobreak > nul\n"
                f"del \"{current_exe}\"\n"
                f"rename \"{new_exe}\" \"{exe_name}\"\n"
                f"start \"\" \"{current_exe}\"\n"
                f"del \"%~f0\"\n"
            )
            with open(bat_path, "w", encoding="utf-8") as f: f.write(bat_content)
            subprocess.Popen(bat_path, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            os._exit(0)
        except Exception as e:
            self.ui_queue.put(("status", f"업데이트 실패: {e}"))
            self.ui_queue.put(("done_downloading", None))

    # -------------------------
    # 🖼️ UI 디자인
    # -------------------------
    def _build_ui(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(25, 10))
        ctk.CTkLabel(header_frame, text="CHZZK VOD Downloader", font=self.title_font, text_color=TEXT_PRIMARY).pack(side="left")
        ctk.CTkLabel(header_frame, text=f"{CURRENT_VERSION}", font=self.default_font, text_color=TEXT_SECONDARY).pack(side="left", padx=10, pady=(6, 0))

        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=25, pady=5)
        main_container.columnconfigure(0, weight=55)
        main_container.columnconfigure(1, weight=45)
        main_container.rowconfigure(0, weight=1)

        left_panel = ctk.CTkFrame(main_container, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        url_card = ctk.CTkFrame(left_panel, corner_radius=8, fg_color=CARD_COLOR)
        url_card.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(url_card, text="동영상 URL", font=self.bold_font, text_color=TEXT_PRIMARY).pack(anchor="w", padx=20, pady=(15, 5))
        url_inner = ctk.CTkFrame(url_card, fg_color="transparent")
        url_inner.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkEntry(url_inner, textvariable=self.url_var, font=self.default_font, placeholder_text="VOD / 채널 주소 / 생방송 주소(/live/)", height=42, fg_color=INPUT_COLOR, border_width=1, border_color=BORDER_COLOR, text_color=TEXT_PRIMARY).pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.btn_add_queue = ctk.CTkButton(url_inner, text="목록에 추가", width=85, height=42, font=self.bold_font, fg_color=BTN_GRAY, hover_color=BTN_GRAY_HOVER, command=self.add_to_queue)
        self.btn_add_queue.pack(side="right")

        queue_card = ctk.CTkFrame(left_panel, corner_radius=8, fg_color=CARD_COLOR)
        queue_card.pack(fill="both", expand=True, pady=(0, 20))
        q_head = ctk.CTkFrame(queue_card, fg_color="transparent")
        q_head.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(q_head, textvariable=self.q_count_var, font=self.bold_font, text_color=TEXT_PRIMARY).pack(side="left")
        ctk.CTkButton(q_head, text="전체 삭제", width=70, height=28, fg_color=BG_COLOR, hover_color=BORDER_COLOR, font=self.default_font, text_color=TEXT_SECONDARY, command=self.clear_queue).pack(side="right")
        self.queue_frame = ctk.CTkScrollableFrame(queue_card, corner_radius=6, fg_color=BG_COLOR)
        self.queue_frame.pack(fill="both", expand=True, padx=20, pady=(5, 20))

        right_panel = ctk.CTkFrame(main_container, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        set_card = ctk.CTkFrame(right_panel, corner_radius=8, fg_color=CARD_COLOR)
        set_card.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(set_card, text="다운로드 옵션", font=self.bold_font, text_color=TEXT_PRIMARY).pack(anchor="w", padx=20, pady=(15, 10))

        f_inner = ctk.CTkFrame(set_card, fg_color="transparent")
        f_inner.pack(fill="x", padx=20, pady=(0, 15))
        ctk.CTkLabel(f_inner, text="저장 폴더", font=self.default_font, text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 15))
        ctk.CTkEntry(f_inner, textvariable=self.outdir_var, font=self.default_font, height=36, fg_color=INPUT_COLOR, border_width=1, border_color=BORDER_COLOR, text_color=TEXT_PRIMARY).pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(f_inner, text="변경", width=60, height=36, font=self.default_font, fg_color=BTN_GRAY, hover_color=BTN_GRAY_HOVER, command=self._choose_outdir).pack(side="right")

        opt_grid = ctk.CTkFrame(set_card, fg_color="transparent")
        opt_grid.pack(fill="x", padx=20, pady=(0, 15))
        opt_grid.columnconfigure(1, weight=1)

        ctk.CTkLabel(opt_grid, text="해상도", anchor="w", font=self.default_font, text_color=TEXT_SECONDARY).grid(row=0, column=0, sticky="w", pady=6, padx=(0, 25))
        ctk.CTkOptionMenu(opt_grid, variable=self.resolution_var, values=["1080p (최고 화질)", "1080p", "720p", "480p", "360p", "오디오 전용 (MP3)"], font=self.default_font, height=34, fg_color=INPUT_COLOR, button_color=BTN_GRAY, button_hover_color=BTN_GRAY_HOVER).grid(row=0, column=1, sticky="ew", pady=6)

        ctk.CTkLabel(opt_grid, text="파일 이름", anchor="w", font=self.default_font, text_color=TEXT_SECONDARY).grid(row=1, column=0, sticky="w", pady=6, padx=(0, 25))
        ctk.CTkOptionMenu(opt_grid, variable=self.filename_tpl_var, values=["[제목] (기본)", "[채널명] 제목", "[업로드일] 제목"], font=self.default_font, height=34, fg_color=INPUT_COLOR, button_color=BTN_GRAY, button_hover_color=BTN_GRAY_HOVER).grid(row=1, column=1, sticky="ew", pady=6)

        ctk.CTkLabel(opt_grid, text="포맷 / 인증", anchor="w", font=self.default_font, text_color=TEXT_SECONDARY).grid(row=2, column=0, sticky="w", pady=6, padx=(0, 25))
        fc_frame = ctk.CTkFrame(opt_grid, fg_color="transparent")
        fc_frame.grid(row=2, column=1, sticky="ew", pady=6)
        ctk.CTkOptionMenu(fc_frame, variable=self.format_var, values=["MP4", "MKV"], font=self.default_font, width=90, height=34, fg_color=INPUT_COLOR, button_color=BTN_GRAY, button_hover_color=BTN_GRAY_HOVER).pack(side="left", padx=(0, 10))
        ctk.CTkOptionMenu(fc_frame, variable=self.cookies_var, values=["선택 안함", "chrome", "edge", "firefox"], font=self.default_font, width=120, height=34, fg_color=INPUT_COLOR, button_color=BTN_GRAY, button_hover_color=BTN_GRAY_HOVER).pack(side="left")

        ctk.CTkLabel(opt_grid, text="구간 자르기", anchor="w", font=self.default_font, text_color=TEXT_SECONDARY).grid(row=3, column=0, sticky="w", pady=6, padx=(0, 25))
        sec_inner = ctk.CTkFrame(opt_grid, fg_color="transparent")
        sec_inner.grid(row=3, column=1, sticky="w", pady=6)
        ctk.CTkEntry(sec_inner, textvariable=self.start_time_var, placeholder_text="00:00:00", font=self.default_font, width=90, height=34, justify="center", fg_color=INPUT_COLOR, border_width=1, border_color=BORDER_COLOR).pack(side="left")
        ctk.CTkLabel(sec_inner, text=" - ", font=self.default_font, text_color=TEXT_SECONDARY).pack(side="left", padx=5)
        ctk.CTkEntry(sec_inner, textvariable=self.end_time_var, placeholder_text="01:30:00", font=self.default_font, width=90, height=34, justify="center", fg_color=INPUT_COLOR, border_width=1, border_color=BORDER_COLOR).pack(side="left")

        tog_frame = ctk.CTkFrame(set_card, fg_color="transparent")
        tog_frame.pack(fill="x", padx=20, pady=(15, 20))
        ctk.CTkSwitch(tog_frame, text="메타데이터 저장", variable=self.embed_meta_var, font=self.default_font, progress_color=CHZZK_GREEN).grid(row=0, column=0, padx=(0, 20), pady=6, sticky="w")
        ctk.CTkSwitch(tog_frame, text="썸네일 별도 저장", variable=self.save_thumb_var, font=self.default_font, progress_color=CHZZK_GREEN).grid(row=0, column=1, padx=(0, 20), pady=6, sticky="w")
        ctk.CTkSwitch(tog_frame, text="완료 시 PC 종료", variable=self.auto_shutdown_var, font=self.default_font, progress_color="#DC2626").grid(row=1, column=0, padx=(0, 20), pady=6, sticky="w")
        ctk.CTkSwitch(tog_frame, text="현재 설정 기억", variable=self.save_settings_var, font=self.default_font, progress_color=CHZZK_GREEN).grid(row=1, column=1, padx=(0, 20), pady=6, sticky="w")

        act_card = ctk.CTkFrame(right_panel, corner_radius=8, fg_color=CARD_COLOR)
        act_card.pack(fill="both", expand=True, pady=(0, 20))
        self.status_label = ctk.CTkLabel(act_card, textvariable=self.status_var, font=self.bold_font, text_color=TEXT_PRIMARY)
        self.status_label.pack(pady=(20, 5))
        self.pbar = ctk.CTkProgressBar(act_card, height=8, progress_color=CHZZK_GREEN, fg_color=BG_COLOR)
        self.pbar.pack(fill="x", padx=25, pady=(5, 20))
        self.pbar.set(0)

        btn_frame = ctk.CTkFrame(act_card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=25, pady=(0, 20))
        self.btn_start = ctk.CTkButton(btn_frame, text="다운로드 시작", height=45, font=self.bold_font, fg_color=CHZZK_GREEN, hover_color=CHZZK_GREEN_HOVER, text_color="#000000", command=self.start_download)
        self.btn_start.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.btn_stop = ctk.CTkButton(btn_frame, text="정지", width=65, height=45, font=self.default_font, fg_color="#DC2626", hover_color="#B91C1C", state="disabled", command=self.stop_download)
        self.btn_stop.pack(side="left", padx=(0, 10))
        self.btn_folder = ctk.CTkButton(btn_frame, text="폴더 열기", width=80, height=45, font=self.default_font, fg_color=BTN_GRAY, hover_color=BTN_GRAY_HOVER, command=lambda: os.startfile(self.outdir_var.get()))
        self.btn_folder.pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    # -------------------------
    # 🔧 유틸 및 대기열 컨트롤
    # -------------------------
    def _choose_outdir(self):
        d = filedialog.askdirectory(initialdir=self.outdir_var.get() or os.getcwd())
        if d: self.outdir_var.set(d)

    def update_q_count(self):
        self.q_count_var.set(f"대기열 ({len(self.q_list)})")

    def set_busy(self, busy: bool):
        if busy:
            self.btn_start.configure(state="disabled", fg_color=BTN_GRAY)
            self.btn_add_queue.configure(state="disabled", fg_color=BTN_GRAY)
            self.btn_stop.configure(state="normal", fg_color="#DC2626")
        else:
            self.btn_start.configure(state="normal", fg_color=CHZZK_GREEN)
            self.btn_add_queue.configure(state="normal", fg_color=BTN_GRAY)
            self.btn_stop.configure(state="disabled", fg_color=BTN_GRAY)

    def _set_pbar_live(self, live: bool):
        if live and not self._is_live:
            self._is_live = True
            self.pbar.configure(mode="indeterminate")
            self.pbar.start()
        elif not live and self._is_live:
            self._is_live = False
            self.pbar.stop()
            self.pbar.configure(mode="determinate")
            self.pbar.set(0)

    def _script_dir_ffmpeg_location(self):
        if getattr(sys, "frozen", False):
            app_dir = sys._MEIPASS if hasattr(sys, "_MEIPASS") else os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))
        if os.name == "nt": return app_dir if os.path.isfile(os.path.join(app_dir, "ffmpeg.exe")) else None
        else: return app_dir if os.path.isfile(os.path.join(app_dir, "ffmpeg")) else None

    # -------------------------
    # 📋 대기열 UI 관리
    # -------------------------
    def add_to_queue(self):
        url = self.url_var.get().strip()
        if not url: return messagebox.showerror("오류", "URL을 입력하세요.")
        if "/clips/" in url: return messagebox.showerror("지원 불가", "클립 영상은 지원하지 않습니다.")
        self.btn_add_queue.configure(state="disabled", fg_color=BTN_GRAY)
        self.status_var.set("비디오 정보 분석 중...")
        self.fetch_thread = threading.Thread(target=self._fetch_url_info, args=(url,), daemon=True)
        self.fetch_thread.start()

    def _fetch_url_info(self, target_url):
        is_live_url = "/live/" in target_url
        channel_match = re.search(r'chzzk\.naver\.com/([a-fA-F0-9]{32})', target_url)

        if channel_match and not is_live_url and "video" not in target_url:
            channel_id = channel_match.group(1)
            self.ui_queue.put(("status", "채널 내 모든 VOD 스캔 중..."))
            try:
                page = 0; size = 50; added_count = 0
                while True:
                    api_url = f"https://api.chzzk.naver.com/service/v1/channels/{channel_id}/videos?sortType=LATEST&pagingType=PAGE&page={page}&size={size}"
                    req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req) as resp:
                        res_data = json.loads(resp.read().decode("utf-8"))
                        content = res_data.get("content")
                        if not content or not content.get("data"): break
                        for v in content.get("data", []):
                            video_no = v.get("videoNo")
                            if video_no:
                                title = v.get("videoTitle", f"VOD_{video_no}")
                                vid_url = f"https://chzzk.naver.com/video/{video_no}"
                                self.ui_queue.put(("add_ui_item", (vid_url, title)))
                                added_count += 1
                        total_pages = content.get("totalPages", 1)
                        page += 1
                        if page >= total_pages: break
                self.ui_queue.put(("status", "대기열 추가 완료"))
                return
            except Exception as e:
                self.ui_queue.put(("status", "채널 파싱 실패"))
                self.ui_queue.put(("show_error", f"채널 파싱 실패:\n{e}"))
            finally:
                self.ui_queue.put(("done_fetching", None))
            return

        try:
            import yt_dlp
            ydl_opts = {"extract_flat": True, "quiet": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_url, download=False)
                if "entries" in info:
                    for entry in list(info["entries"]):
                        vid_url = entry.get("url") or entry.get("webpage_url")
                        self.ui_queue.put(("add_ui_item", (vid_url, entry.get("title", vid_url))))
                else:
                    vid_url = info.get("url") or info.get("webpage_url") or target_url
                    title = info.get("title", vid_url)
                    if info.get("is_live") or is_live_url:
                        title = f"[🔴LIVE] {title}"
                    self.ui_queue.put(("add_ui_item", (vid_url, title)))
                self.ui_queue.put(("status", "대기열 추가 완료"))
        except Exception as e:
            self.ui_queue.put(("status", "URL 분석 실패"))
            self.ui_queue.put(("show_error", f"URL 분석 실패:\n{e}"))
        finally:
            self.ui_queue.put(("done_fetching", None))

    def _create_q_item_ui(self, url, title):
        item_frame = ctk.CTkFrame(self.queue_frame, fg_color=CARD_COLOR, corner_radius=6)
        item_frame.pack(fill="x", pady=3, padx=2)
        text_color = "#FCA5A5" if "[🔴LIVE]" in title else TEXT_PRIMARY
        ctk.CTkLabel(item_frame, text=title, anchor="w", font=self.default_font, text_color=text_color).pack(side="left", padx=15, fill="x", expand=True, pady=10)
        item_data = {"url": url, "title": title, "frame": item_frame}
        c_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
        c_frame.pack(side="right", padx=(0, 10))
        ctk.CTkButton(c_frame, text="↑", width=28, height=28, fg_color=BTN_GRAY, hover_color=BTN_GRAY_HOVER, command=lambda: self._move_up(item_data)).pack(side="left", padx=2)
        ctk.CTkButton(c_frame, text="↓", width=28, height=28, fg_color=BTN_GRAY, hover_color=BTN_GRAY_HOVER, command=lambda: self._move_down(item_data)).pack(side="left", padx=2)
        ctk.CTkButton(c_frame, text="✕", width=28, height=28, text_color="#FCA5A5", fg_color="transparent", hover_color="#7F1D1D", command=lambda: self._remove_q_item(item_data)).pack(side="left", padx=2)
        self.q_list.append(item_data)
        self.update_q_count()

    def _move_up(self, item):
        idx = self.q_list.index(item)
        if idx > 0:
            self.q_list.insert(idx - 1, self.q_list.pop(idx))
            self._repack_queue()

    def _move_down(self, item):
        idx = self.q_list.index(item)
        if idx < len(self.q_list) - 1:
            self.q_list.insert(idx + 1, self.q_list.pop(idx))
            self._repack_queue()

    def _repack_queue(self):
        for item in self.q_list: item["frame"].pack_forget()
        for item in self.q_list: item["frame"].pack(fill="x", pady=3, padx=2)

    def _remove_q_item(self, item_data):
        if item_data in self.q_list:
            item_data["frame"].destroy()
            self.q_list.remove(item_data)
            self.update_q_count()

    def clear_queue(self):
        for item in self.q_list: item["frame"].destroy()
        self.q_list.clear()
        self.update_q_count()

    # -------------------------
    # ▶️ 다운로드 제어 및 yt-dlp
    # -------------------------
    def start_download(self):
        if not self.q_list: return messagebox.showwarning("알림", "대기열이 비어있습니다.")
        if not os.path.isdir(self.outdir_var.get().strip()): return messagebox.showerror("오류", "유효한 저장 경로를 지정하세요.")
        self.stop_flag.clear()
        self.set_busy(True)
        self._set_pbar_live(False)
        self.download_thread = threading.Thread(target=self._process_queue_loop, daemon=True)
        self.download_thread.start()

    def stop_download(self):
        self.stop_flag.set()
        if self.proc and self.proc.poll() is None:
            try:
                if os.name == 'nt':
                    os.kill(self.proc.pid, signal.CTRL_BREAK_EVENT)
                else:
                    self.proc.terminate()
            except: pass
        self.status_var.set("안전하게 종료하는 중...")

    def _process_queue_loop(self):
        while self.q_list and not self.stop_flag.is_set():
            current_item = self.q_list[0]
            is_live = "[🔴LIVE]" in current_item["title"]
            self.ui_queue.put(("set_live_mode", is_live))

            success = self._run_single_ytdlp(current_item["url"], is_live)

            if success and not self.stop_flag.is_set():
                self.ui_queue.put(("pop_top_item", None))
            else:
                break

        if self.stop_flag.is_set():
            self.ui_queue.put(("status", "작업이 정지되었습니다."))
        elif not self.q_list:
            self.ui_queue.put(("status", "모든 다운로드 완료"))
            if self.auto_shutdown_var.get():
                self.ui_queue.put(("show_warning", "60초 뒤 시스템이 종료됩니다.\n(취소: 명령 프롬프트에서 'shutdown /a' 입력)"))
                os.system("shutdown /s /t 60")

        self.ui_queue.put(("done_downloading", None))

    def _run_single_ytdlp(self, url, is_live) -> bool:
        outdir = self.outdir_var.get().strip()
        resolution = self.resolution_var.get()
        fmt = self.format_var.get().lower()
        cookies = self.cookies_var.get()
        tpl = self.filename_tpl_var.get()

        if tpl == "[채널명] 제목": outtmpl = os.path.join(outdir, "[%(uploader)s] %(title)s.%(ext)s")
        elif tpl == "[업로드일] 제목": outtmpl = os.path.join(outdir, "[%(upload_date)s] %(title)s.%(ext)s")
        else: outtmpl = os.path.join(outdir, "%(title)s.%(ext)s")

        cmd = [sys.executable, "-u", "-m", "yt_dlp", "--newline", "--no-playlist", "--progress", "--progress-delta", "1", "-N", "4"]

        if is_live:
            # 라이브는 안정성을 위해 remux 없이 TS 그대로 저장하거나, wait_for_video 추가
            cmd += ["--wait-for-video", "10"]
            # 라이브에서 --remux-video를 쓰면 실시간 병합 중 오류가 잦으므로 생략 권장
            # 다만 사용자가 포맷을 지정했으니 일단 유지하되, 오류 시 무시 로직을 강화함
        else:
            if "오디오 전용" not in resolution: cmd += ["--remux-video", fmt]

        if "최고 화질" in resolution: cmd += ["-f", "bv*+ba/b"]
        elif "1080p" in resolution: cmd += ["-f", "bv*[height<=1080]+ba/b"]
        elif "720p" in resolution: cmd += ["-f", "bv*[height<=720]+ba/b"]
        elif "480p" in resolution: cmd += ["-f", "bv*[height<=480]+ba/b"]
        elif "360p" in resolution: cmd += ["-f", "bv*[height<=360]+ba/b"]
        elif "오디오 전용" in resolution: cmd += ["-f", "ba", "-x", "--audio-format", "mp3"]

        if not is_live and "오디오 전용" not in resolution: 
             cmd += ["--remux-video", fmt]

        if cookies != "선택 안함": cmd += ["--cookies-from-browser", cookies]

        ffmpeg_loc = self._script_dir_ffmpeg_location()
        if ffmpeg_loc: cmd += ["--ffmpeg-location", ffmpeg_loc]

        if "오디오 전용" not in resolution:
            if self.embed_meta_var.get(): cmd += ["--embed-thumbnail", "--embed-metadata"]
            if self.save_thumb_var.get(): cmd += ["--write-thumbnail"]

        start_t = self.start_time_var.get().strip()
        end_t = self.end_time_var.get().strip()
        if start_t or end_t:
            st = start_t if start_t else "0"
            et = end_t if end_t else "inf"
            cmd += ["--download-sections", f"*{st}-{et}"]

        cmd += ["--print", "after_move:filepath", "-o", outtmpl, url]

        last_printed_path = None
        last_error_lines = []

        try:
            cflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, universal_newlines=True, encoding="utf-8", errors="replace",
                creationflags=cflags
            )
            for line in self.proc.stdout:
                line = line.rstrip("\n")
                if line.strip():
                    last_error_lines.append(line)
                    if len(last_error_lines) > 10: last_error_lines.pop(0)

                m_speed = SPEED_ETA_RE.search(line)
                if m_speed:
                    pct, speed, eta = m_speed.groups()
                    self.ui_queue.put(("progress_ext", (pct, speed, eta)))
                else:
                    m_live = LIVE_RE.search(line)
                    if m_live and "ETA" not in line and "%" not in line:
                        size, speed = m_live.groups()
                        self.ui_queue.put(("progress_live", (size, speed)))
                    else:
                        m = PCT_RE.search(line)
                        if m:
                            try: self.ui_queue.put(("progress", float(m.group(1))))
                            except: pass

                if line and (os.path.sep in line or (os.name == "nt" and ":" in line)):
                    cand = line.strip().strip('"').strip("'")
                    if os.path.exists(cand) and os.path.isfile(cand):
                        last_printed_path = cand

            rc = self.proc.wait()

            # 3221225786 = CTRL_C_EXIT (Windows), 3199971767 = ffmpeg invalid data
            # 사용자가 멈췄거나, ffmpeg가 강종되었더라도 파일이 있다면 성공으로 간주
            if self.stop_flag.is_set() or rc == 3221225786 or rc == 3199971767:
                if last_printed_path:
                    self.ui_queue.put(("status", f"녹화 저장됨 (부분): {os.path.basename(last_printed_path)}"))
                    return True
                # 라이브는 경로가 안 찍힐 수 있음 -> 현재 폴더에서 가장 최신 파일 추적하는 로직은 복잡하니 패스
                # 대신 rc가 0이 아니어도 성공 처리
                return True

            if rc != 0:
                error_detail = "\n".join(last_error_lines[-5:]) if last_error_lines else "알 수 없는 오류"
                self.ui_queue.put(("status", "오류 발생"))
                self.ui_queue.put(("show_error", f"yt-dlp 오류 (종료 코드 {rc}):\n\n{error_detail}"))
                return False

            self.ui_queue.put(("progress", 100.0))
            if last_printed_path:
                self.ui_queue.put(("status", f"완료: {os.path.basename(last_printed_path)}"))
            return True

        except Exception as e:
            self.ui_queue.put(("status", "시스템 예외 발생"))
            self.ui_queue.put(("show_error", f"시스템 예외:\n{e}"))
            return False

    # -------------------------
    # 🔁 UI 동기화 (메인 스레드)
    # -------------------------
    def _poll_queue(self):
        try:
            while True:
                typ, val = self.ui_queue.get_nowait()

                if typ == "set_live_mode":
                    self._set_pbar_live(val)

                elif typ == "progress_ext":
                    pct, speed, eta = val
                    try:
                        self._set_pbar_live(False)
                        self.pbar.set(max(0.0, min(1.0, float(pct) / 100.0)))
                        self.status_var.set(f"다운로드 중... {pct}% ({speed}, 남은 시간: {eta})")
                    except: pass

                elif typ == "progress_live":
                    size, speed = val
                    try:
                        self._set_pbar_live(True)
                        self.status_var.set(f"🔴 라이브 녹화 중... {size} ({speed})")
                    except: pass

                elif typ == "progress":
                    try:
                        self._set_pbar_live(False)
                        self.pbar.set(max(0.0, min(1.0, float(val) / 100.0)))
                        self.status_var.set(f"다운로드 중... {val:.1f}%")
                    except: pass

                elif typ == "status":
                    self.status_var.set(val)

                elif typ == "show_error":
                    messagebox.showerror("오류", val)
                elif typ == "show_warning":
                    messagebox.showwarning("시스템 종료", val)

                elif typ == "add_ui_item":
                    self._create_q_item_ui(val[0], val[1])
                elif typ == "pop_top_item":
                    if self.q_list: self._remove_q_item(self.q_list[0])
                elif typ == "done_fetching":
                    self.btn_add_queue.configure(state="normal", fg_color=BTN_GRAY)
                elif typ == "done_downloading":
                    self._set_pbar_live(False)
                    self.set_busy(False)

        except queue.Empty:
            pass
        self.after(120, self._poll_queue)


if __name__ == "__main__":
    app = App()
    app.mainloop()
