import os
import re
import sys
import json
import queue
import threading
import subprocess
import urllib.request
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

# ==========================================
# ⚙️ 업데이트 설정
# ==========================================
ENABLE_AUTO_UPDATE = True
CURRENT_VERSION = "v1.0.3"
GITHUB_REPO = "sunglogbag81/Chzzk-VOD-downloader"
# ==========================================

PCT_RE = re.compile(r'(\d+(?:\.\d+)?)%')
CONFIG_FILE = "settings.json"

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.title(f"⚡ 치지직 VOD Downloader {CURRENT_VERSION}")
        self.geometry("960x820")  # UI 추가를 위해 세로 길이 약간 늘림
        self.minsize(920, 750)

        self.ui_queue = queue.Queue()
        self.download_thread = None
        self.fetch_thread = None
        self.proc = None
        self.stop_flag = threading.Event()
        
        self.q_list = []  

        # --- 변수 초기화 ---
        self.url_var = ctk.StringVar()
        self.outdir_var = ctk.StringVar(value=os.path.abspath(os.getcwd()))
        self.q_count_var = ctk.StringVar(value="대기열: 0개")

        self.best_var = ctk.BooleanVar(value=True)
        self.format_var = ctk.StringVar(value="MP4")
        self.cookies_var = ctk.StringVar(value="없음") 
        self.status_var = ctk.StringVar(value="대기 중...")

        # 신규 기능 변수
        self.start_time_var = ctk.StringVar(value="")
        self.end_time_var = ctk.StringVar(value="")
        self.save_settings_var = ctk.BooleanVar(value=False)  # 3번: OFF 기본
        self.embed_meta_var = ctk.BooleanVar(value=True)      # 4번: ON 기본

        # 설정 파일 불러오기
        self._load_settings()

        self._build_ui()
        self.after(120, self._poll_queue)

        # 프로그램 종료 시 설정 저장 로직 연결
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        if ENABLE_AUTO_UPDATE:
            threading.Thread(target=self._check_for_updates, daemon=True).start()

    # -------------------------
    # 💾 3번 기능: 설정 불러오기/저장
    # -------------------------
    def _load_settings(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                # 사용자가 설정 저장을 켜뒀을 때만 나머지 설정 적용
                if data.get("save_settings", False):
                    self.save_settings_var.set(True)
                    self.outdir_var.set(data.get("outdir", os.path.abspath(os.getcwd())))
                    self.best_var.set(data.get("best", True))
                    self.format_var.set(data.get("format", "MP4"))
                    self.cookies_var.set(data.get("cookies", "없음"))
                    self.embed_meta_var.set(data.get("embed_meta", True))
            except Exception:
                pass

    def _on_closing(self):
        if self.save_settings_var.get():
            data = {
                "save_settings": True,
                "outdir": self.outdir_var.get(),
                "best": self.best_var.get(),
                "format": self.format_var.get(),
                "cookies": self.cookies_var.get(),
                "embed_meta": self.embed_meta_var.get()
            }
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
            except Exception:
                pass
        else:
            # 설정 저장을 껐다면 기존 설정 파일 삭제
            if os.path.exists(CONFIG_FILE):
                try:
                    os.remove(CONFIG_FILE)
                except Exception:
                    pass
        self.destroy()

    # -------------------------
    # 🔄 자동 업데이트 다운로드 및 재시작
    # -------------------------
    def _check_for_updates(self):
        if GITHUB_REPO == "username/repo_name":
            return
        try:
            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                
            latest_version = data.get("tag_name", "")
            download_url = None
            for asset in data.get("assets", []):
                if asset.get("name", "").endswith(".exe"):
                    download_url = asset.get("browser_download_url")
                    break

            if latest_version and latest_version != CURRENT_VERSION and download_url:
                self.after(1000, lambda: self._show_auto_update_prompt(latest_version, download_url))
        except Exception as e:
            pass

    def _show_auto_update_prompt(self, latest_version, download_url):
        msg = f"새로운 버전({latest_version})이 출시되었습니다!\n(현재 버전: {CURRENT_VERSION})\n\n지금 바로 자동으로 업데이트하고 다시 시작할까요?"
        if messagebox.askyesno("업데이트 알림", msg):
            self._apply_update(download_url)

    def _apply_update(self, download_url):
        self.status_var.set("업데이트 파일을 다운로드 중입니다...")
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
            bat_content = f"""@echo off
chcp 65001 > nul
echo 기존 프로그램을 안전하게 종료하는 중입니다...
taskkill /f /im "{exe_name}" > nul 2>&1
timeout /t 3 /nobreak > nul
del "{current_exe}"
rename "{new_exe}" "{exe_name}"
start "" "{current_exe}"
del "%~f0"
"""
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_content)

            subprocess.Popen([bat_path], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            sys.exit(0)
        except Exception as e:
            self.ui_queue.put(("status", f"업데이트 실패: {e}"))
            self.ui_queue.put(("done_downloading", None))

    # -------------------------
    # UI 빌드
    # -------------------------
    def _build_ui(self):
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        title_label = ctk.CTkLabel(main_frame, text="CHZZK VOD DOWNLOADER", font=ctk.CTkFont(size=24, weight="bold"))
        title_label.pack(anchor="w", pady=(0, 15))

        # --- 상단 1: URL 및 대기열 ---
        input_frame = ctk.CTkFrame(main_frame, corner_radius=10)
        input_frame.pack(fill="x", pady=(0, 15))
        input_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(input_frame, text="VOD/채널 URL", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=15, pady=15)
        ctk.CTkEntry(input_frame, textvariable=self.url_var, placeholder_text="채널 링크 입력 시 전체 VOD 자동 추출...").grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=15)
        
        self.btn_add_queue = ctk.CTkButton(input_frame, text="➕ 대기열 추가", width=120, command=self.add_to_queue)
        self.btn_add_queue.grid(row=0, column=2, padx=(0, 15), pady=15)

        # --- 상단 2: 구간 클립 (2번 기능) ---
        clip_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        clip_frame.pack(fill="x", pady=(0, 5))
        
        ctk.CTkLabel(clip_frame, text="✂️ 구간 자르기:").pack(side="left", padx=(5, 5))
        ctk.CTkEntry(clip_frame, textvariable=self.start_time_var, placeholder_text="00:00:00", width=80, height=24).pack(side="left", padx=5)
        ctk.CTkLabel(clip_frame, text="~").pack(side="left")
        ctk.CTkEntry(clip_frame, textvariable=self.end_time_var, placeholder_text="01:30:00", width=80, height=24).pack(side="left", padx=5)
        ctk.CTkLabel(clip_frame, text="(비워두면 전체 다운로드)", text_color="gray").pack(side="left", padx=5)

        q_header_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        q_header_frame.pack(fill="x", pady=(10, 5))
        ctk.CTkLabel(q_header_frame, textvariable=self.q_count_var, font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkButton(q_header_frame, text="🗑 전체 비우기", width=100, height=24, fg_color="#4B5563", hover_color="#374151", command=self.clear_queue).pack(side="right")

        self.queue_frame = ctk.CTkScrollableFrame(main_frame, height=120, corner_radius=10)
        self.queue_frame.pack(fill="x", pady=(0, 15))

        # --- 설정 영역 ---
        settings_frame = ctk.CTkFrame(main_frame, corner_radius=10)
        settings_frame.pack(fill="x", pady=(0, 15))
        settings_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(settings_frame, text="저장 폴더", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=15, pady=15)
        ctk.CTkEntry(settings_frame, textvariable=self.outdir_var).grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=15)
        ctk.CTkButton(settings_frame, text="📁 폴더 찾기", width=100, fg_color="#4B5563", hover_color="#374151", command=self._choose_outdir).grid(row=0, column=2, padx=(0, 15), pady=15)

        # --- 옵션 영역 ---
        opt_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        opt_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkCheckBox(opt_frame, text="최고 화질 (bv*+ba/b)", variable=self.best_var).pack(side="left", padx=(0, 15))
        ctk.CTkLabel(opt_frame, text="포맷:").pack(side="left", padx=(5, 5))
        ctk.CTkOptionMenu(opt_frame, variable=self.format_var, values=["MP4", "MKV"], width=80).pack(side="left", padx=(0, 15))
        ctk.CTkLabel(opt_frame, text="쿠키:").pack(side="left", padx=(5, 5))
        ctk.CTkOptionMenu(opt_frame, variable=self.cookies_var, values=["없음", "chrome", "edge", "firefox"], width=100).pack(side="left", padx=(0, 15))
        
        # 4번, 3번 스위치 추가
        ctk.CTkCheckBox(opt_frame, text="썸네일/정보 삽입", variable=self.embed_meta_var).pack(side="left", padx=(0, 15))
        ctk.CTkCheckBox(opt_frame, text="설정 기억하기", variable=self.save_settings_var).pack(side="left")

        # --- 컨트롤 ---
        ctrl_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        ctrl_frame.pack(fill="x", pady=(0, 10))

        self.btn_start = ctk.CTkButton(ctrl_frame, text="▶ 대기열 다운로드 시작", font=ctk.CTkFont(weight="bold"), fg_color="#2563EB", hover_color="#1D4ED8", command=self.start_download)
        self.btn_start.pack(side="left", padx=(0, 10))

        self.btn_stop = ctk.CTkButton(ctrl_frame, text="⏹ 다운로드 중지", font=ctk.CTkFont(weight="bold"), fg_color="#DC2626", hover_color="#B91C1C", state="disabled", command=self.stop_download)
        self.btn_stop.pack(side="left", padx=(0, 20))

        self.status_label = ctk.CTkLabel(ctrl_frame, textvariable=self.status_var, text_color="#10B981", font=ctk.CTkFont(weight="bold"))
        self.status_label.pack(side="left")

        # --- 로그 ---
        self.txt = ctk.CTkTextbox(main_frame, wrap="word", font=ctk.CTkFont(family="Consolas", size=13))
        self.txt.pack(fill="both", expand=True, pady=(0, 10))
        self.txt.configure(state="disabled")

        self.pbar = ctk.CTkProgressBar(main_frame, height=12, progress_color="#10B981")
        self.pbar.pack(fill="x", pady=(0, 5))
        self.pbar.set(0)

    # -------------------------
    # 유틸리티 기능
    # -------------------------
    def _choose_outdir(self):
        d = filedialog.askdirectory(initialdir=self.outdir_var.get() or os.getcwd())
        if d:
            self.outdir_var.set(d)

    def log(self, s: str):
        self.txt.configure(state="normal")
        self.txt.insert("end", s + ("\n" if not s.endswith("\n") else ""))
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def update_q_count(self):
        self.q_count_var.set(f"대기열: {len(self.q_list)}개")

    def set_busy(self, busy: bool):
        if busy:
            self.btn_start.configure(state="disabled", fg_color="#4B5563")
            self.btn_add_queue.configure(state="disabled", fg_color="#4B5563")
            self.btn_stop.configure(state="normal", fg_color="#DC2626")
        else:
            self.btn_start.configure(state="normal", fg_color="#2563EB")
            self.btn_add_queue.configure(state="normal")
            self.btn_stop.configure(state="disabled", fg_color="#4B5563")

    def _script_dir_ffmpeg_location(self):
        if getattr(sys, 'frozen', False):
            app_dir = sys._MEIPASS
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))

        if os.name == "nt":
            return app_dir if os.path.isfile(os.path.join(app_dir, "ffmpeg.exe")) else None
        else:
            return app_dir if os.path.isfile(os.path.join(app_dir, "ffmpeg")) else None

    # -------------------------
    # 큐 데이터 처리
    # -------------------------
    def add_to_queue(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("오류", "VOD 또는 채널 URL을 입력하세요.")
            return

        self.btn_add_queue.configure(state="disabled", fg_color="#4B5563")
        self.status_var.set("URL 정보 분석 중...")
        
        self.fetch_thread = threading.Thread(target=self._fetch_url_info, args=(url,), daemon=True)
        self.fetch_thread.start()

    def _fetch_url_info(self, target_url):
        channel_match = re.search(r'chzzk\.naver\.com/([a-fA-F0-9]{32})', target_url)
        if channel_match:
            channel_id = channel_match.group(1)
            self.ui_queue.put(("log", f"🔎 채널 ID 감지됨: {channel_id}\n채널의 모든 VOD를 불러옵니다..."))
            
            try:
                page = 0
                size = 50
                added_count = 0
                
                while True:
                    api_url = f"https://api.chzzk.naver.com/service/v1/channels/{channel_id}/videos?sortType=LATEST&pagingType=PAGE&page={page}&size={size}"
                    req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                    
                    with urllib.request.urlopen(req) as resp:
                        res_data = json.loads(resp.read().decode('utf-8'))
                        
                    content = res_data.get('content')
                    if not content or not content.get('data'):
                        break
                        
                    for v in content.get('data', []):
                        video_no = v.get('videoNo')
                        if video_no:
                            title = v.get('videoTitle', f"VOD_{video_no}")
                            vid_url = f"https://chzzk.naver.com/video/{video_no}"
                            self.ui_queue.put(("add_ui_item", (vid_url, title)))
                            added_count += 1
                            
                    total_pages = content.get('totalPages', 1)
                    page += 1
                    if page >= total_pages:
                        break
                        
                self.ui_queue.put(("log", f"✅ 채널 VOD 총 {added_count}개 대기열 추가 완료!"))
                self.ui_queue.put(("status", "대기열 추가 완료"))
                return
            except Exception as e:
                self.ui_queue.put(("log", f"❌ 치지직 API 파싱 실패: {e}"))
                self.ui_queue.put(("status", "채널 파싱 실패"))
            finally:
                self.ui_queue.put(("done_fetching", None))
            return

        try:
            import yt_dlp
            ydl_opts = {'extract_flat': True, 'quiet': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_url, download=False)
                
                if 'entries' in info:
                    entries = list(info['entries'])
                    self.ui_queue.put(("log", f"재생목록 {len(entries)}개 감지됨."))
                    for entry in entries:
                        vid_url = entry.get('url') or entry.get('webpage_url')
                        title = entry.get('title', vid_url)
                        self.ui_queue.put(("add_ui_item", (vid_url, title)))
                else:
                    vid_url = info.get('url') or info.get('webpage_url') or target_url
                    title = info.get('title', vid_url)
                    self.ui_queue.put(("add_ui_item", (vid_url, title)))
                    
            self.ui_queue.put(("status", "대기열 추가 완료"))
        except Exception as e:
            self.ui_queue.put(("log", f"❌ URL 분석 실패: {e}"))
            self.ui_queue.put(("status", "URL 분석 실패"))
        finally:
            self.ui_queue.put(("done_fetching", None))

    def _create_q_item_ui(self, url, title):
        item_frame = ctk.CTkFrame(self.queue_frame, fg_color="#374151")
        item_frame.pack(fill="x", pady=2, padx=2)
        lbl_title = ctk.CTkLabel(item_frame, text=title, anchor="w")
        lbl_title.pack(side="left", padx=10, fill="x", expand=True)

        item_data = {'url': url, 'title': title, 'frame': item_frame}
        btn_del = ctk.CTkButton(item_frame, text="X", width=30, fg_color="#EF4444", hover_color="#B91C1C", command=lambda: self._remove_q_item(item_data))
        btn_del.pack(side="right", padx=5, pady=2)
        
        self.q_list.append(item_data)
        self.update_q_count()

    def _remove_q_item(self, item_data):
        if item_data in self.q_list:
            item_data['frame'].destroy()
            self.q_list.remove(item_data)
            self.update_q_count()

    def clear_queue(self):
        for item in self.q_list:
            item['frame'].destroy()
        self.q_list.clear()
        self.update_q_count()

    # -------------------------
    # 다운로드 프로세스
    # -------------------------
    def start_download(self):
        if not self.q_list:
            messagebox.showwarning("알림", "대기열이 비어있습니다.")
            return

        outdir = self.outdir_var.get().strip()
        if not outdir or not os.path.isdir(outdir):
            messagebox.showerror("오류", "저장 폴더를 확인하세요.")
            return

        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.configure(state="disabled")

        self.stop_flag.clear()
        self.set_busy(True)

        self.download_thread = threading.Thread(target=self._process_queue_loop, daemon=True)
        self.download_thread.start()

    def stop_download(self):
        self.stop_flag.set()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.status_var.set("현재 작업 중지 요청됨...")

    def _process_queue_loop(self):
        while self.q_list and not self.stop_flag.is_set():
            current_item = self.q_list[0]
            self.ui_queue.put(("progress", 0.0))
            self.ui_queue.put(("log", f"\n▶️ 다운로드 시작: {current_item['title']}"))
            
            success = self._run_single_ytdlp(current_item['url'])
            if success and not self.stop_flag.is_set():
                self.ui_queue.put(("pop_top_item", None))
            else:
                break

        if self.stop_flag.is_set():
            self.ui_queue.put(("status", "❌ 다운로드 중지됨"))
        elif not self.q_list:
            self.ui_queue.put(("status", "✅ 대기열 모든 다운로드 완료"))
            
        self.ui_queue.put(("done_downloading", None))

    def _run_single_ytdlp(self, url) -> bool:
        outdir = self.outdir_var.get().strip()
        use_best = self.best_var.get()
        fmt = self.format_var.get().lower()
        cookies = self.cookies_var.get()
        embed_meta = self.embed_meta_var.get()
        start_t = self.start_time_var.get().strip()
        end_t = self.end_time_var.get().strip()

        outtmpl = os.path.join(outdir, "%(title)s.%(ext)s")
        cmd = [sys.executable, "-u", "-m", "yt_dlp", "--newline", "--no-playlist", "--progress", "--progress-delta", "1", "-N", "4"]

        if use_best:
            cmd += ["-f", "bv*+ba/b"]
        
        cmd += ["--remux-video", fmt]

        if cookies != "없음":
            cmd += ["--cookies-from-browser", cookies]

        ffmpeg_loc = self._script_dir_ffmpeg_location()
        if ffmpeg_loc:
            cmd += ["--ffmpeg-location", ffmpeg_loc]

        # 4번: 썸네일/메타데이터 삽입 로직
        if embed_meta:
            cmd += ["--embed-thumbnail", "--embed-metadata"]

        # 2번: 구간 클립 다운로드 로직
        if start_t or end_t:
            st = start_t if start_t else "0"
            et = end_t if end_t else "inf"
            cmd += ["--download-sections", f"*{st}-{et}"]
            self.ui_queue.put(("log", f"✂️ 구간 자르기 적용됨: {st} ~ {et}"))

        cmd += ["--print", "after_move:filepath", "-o", outtmpl, url]

        last_printed_path = None
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, universal_newlines=True, encoding="utf-8", errors="replace"
            )

            for line in self.proc.stdout:
                if self.stop_flag.is_set():
                    break
                line = line.rstrip("\n")
                self.ui_queue.put(("log", line))

                m = PCT_RE.search(line)
                if m:
                    try:
                        self.ui_queue.put(("progress", float(m.group(1))))
                    except ValueError:
                        pass

                if line and (os.path.sep in line or (os.name == "nt" and ":" in line)):
                    cand = line.strip().strip('"').strip("'")
                    if os.path.exists(cand) and os.path.isfile(cand):
                        last_printed_path = cand

            rc = self.proc.wait()

            if self.stop_flag.is_set():
                return False
            if rc != 0:
                self.ui_queue.put(("log", f"⚠️ 다운로드 실패 (코드 {rc})"))
                return False

            self.ui_queue.put(("progress", 100.0))
            if last_printed_path:
                self.ui_queue.put(("status", f"완료: {os.path.basename(last_printed_path)}"))
            return True

        except Exception as e:
            self.ui_queue.put(("log", f"❌ 다운로드 예외 발생: {e}"))
            return False

    def _poll_queue(self):
        try:
            while True:
                typ, val = self.ui_queue.get_nowait()
                if typ == "log":
                    self.log(val)
                elif typ == "progress":
                    try:
                        self.pbar.set(max(0.0, min(1.0, float(val) / 100.0)))
                        self.status_var.set(f"다운로드 중... {val:.1f}%")
                    except Exception:
                        pass
                elif typ == "status":
                    self.status_var.set(val)
                elif typ == "add_ui_item":
                    self._create_q_item_ui(val[0], val[1])
                elif typ == "pop_top_item":
                    if self.q_list:
                        self._remove_q_item(self.q_list[0])
                elif typ == "done_fetching":
                    self.btn_add_queue.configure(state="normal")
                elif typ == "done_downloading":
                    self.set_busy(False)
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

if __name__ == "__main__":
    app = App()
    app.mainloop()
