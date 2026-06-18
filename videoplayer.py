import os
import random
import sys
import tkinter as tk
from PIL import Image, ImageTk, ImageOps
from ffpyplayer.player import MediaPlayer


VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm")
length = 5  # seconds to show per clip

current_video = None
player = None

def _videos_folder():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "videos")

def get_random_video(folder=None):
    global current_video
    if folder is None:
        folder = _videos_folder()
    videos = [f for f in os.listdir(folder) if f.lower().endswith(VIDEO_EXTENSIONS)]
    if not videos:
        raise FileNotFoundError(f"No video files found in {folder}")
    choices = [v for v in videos if os.path.join(folder, v) != current_video]
    if not choices:
        choices = videos  # fallback when there's only one video
    current_video = os.path.join(folder, random.choice(choices))
    return current_video


root = tk.Tk()
root.title("Video Player")
root.configure(background="gray15")
root.minsize(200, 150)
root.geometry("400x300+100+100")

# controls bar — packed first so it always reserves space before the video expands
controls_frame = tk.Frame(root, bg="gray20")
controls_frame.pack(fill="x", side="bottom")

# video display label
video_label = tk.Label(root, bg="gray15")
video_label.pack(expand=True, fill="both")

paused = False
muted = False
volume = 1.0  # last non-zero volume, restored on unmute

def toggle_pause(): #pause button
    global paused
    if loading:
        return
    paused = not paused
    player.set_pause(paused)
    pause_btn.config(text="Play" if paused else "Pause")

def skip_video(): #skip button
    global paused
    if paused:
        paused = False
        pause_btn.config(text="Pause")
    loop()

def toggle_mute(): #mute button
    global muted
    muted = not muted
    player.set_volume(0.0 if muted else volume)
    mute_btn.config(text="Unmute" if muted else "Mute")

pause_btn = tk.Button(controls_frame, text="Pause", command=toggle_pause,
                      bg="gray25", fg="white", relief="flat", padx=10)
pause_btn.pack(side="left", padx=5, pady=5)

skip_btn = tk.Button(controls_frame, text="Skip", command=skip_video,
                     bg="gray25", fg="white", relief="flat", padx=10)
skip_btn.pack(side="left", padx=5, pady=5)

mute_btn = tk.Button(controls_frame, text="Mute", command=toggle_mute,
                     bg="gray25", fg="white", relief="flat", padx=10)
mute_btn.pack(side="left", padx=5, pady=5)

tk.Label(controls_frame, text="Duration:", fg="white", bg="gray20").pack(side="left", padx=(15, 2), pady=5)
length_var = tk.IntVar(value=length)
length_slider = tk.Scale(controls_frame, variable=length_var, from_=1, to=60,
                         orient="horizontal", bg="gray20", fg="white",
                         highlightthickness=0, troughcolor="gray35", length=120,
                         command=lambda _: globals().update(length=length_var.get()))
length_slider.pack(side="left", pady=5)
tk.Label(controls_frame, text="sec", fg="white", bg="gray20").pack(side="left", pady=5)

# opaque overlay that covers the display while the next video loads
loading_frame = tk.Frame(root, bg="gray15")
loading_label = tk.Label(loading_frame, text="Loading...", fg="white", bg="gray15")
loading_label.place(relx=0.5, rely=0.5, anchor="center")

loading = False
seek_start_pts = 0.0  # player PTS right after seek, so elapsed = get_pts() - seek_start_pts
_stale = None  # previous player, kept alive until the next transition so close_player() runs on an idle player

def show_loading():
    global loading
    loading = True
    loading_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
    loading_frame.lift()

def hide_loading():
    global loading, seek_start_pts
    loading = False
    seek_start_pts = player.get_pts()
    loading_frame.place_forget()

def loop():
    global player, paused, _stale
    if loading:
        return
    if paused:
        paused = False
        pause_btn.config(text="Pause")
    # Close the player from the previous transition — it has been paused/idle
    # for a full clip length by now, so close_player() is safe and fast
    if _stale:
        _stale.close_player()
    # Silence and pause the current player; defer its close to the next transition
    if player:
        player.set_volume(0)
        player.set_pause(True)
    _stale = player
    player = None
    show_loading()
    root.after(50, _do_load)

def _do_load(): #loads the video
    global player
    player = MediaPlayer(get_random_video(), ff_opts={'paused': True, 'out_fmt': 'rgb24'})
    player.set_volume(0.0 if muted else volume)
    root.after(100, _wait_for_metadata)

def _wait_for_metadata(): #gets duration of the video from metadata to calculate start point
    meta = player.get_metadata()
    duration = meta.get('duration')
    if not duration or duration < 0:
        root.after(100, _wait_for_metadata)
        return
    if duration > length:
        player.seek(random.uniform(0, duration - length), relative=False)
    player.set_pause(False)
    root.after(50, _wait_for_first_frame)

def _wait_for_first_frame(): #waits until the first frame of next loaded video is ready, checking every 50ms
    frame, val = player.get_frame()
    if frame is not None:
        _display(frame)
        hide_loading()
    elif val == 'eof':
        loop()
    else:
        root.after(50, _wait_for_first_frame)

def _display(frame):
    img, pts = frame
    w, h = img.get_size()
    pil_img = Image.frombuffer('RGB', (w, h), bytes(img.to_bytearray()[0]), 'raw', 'RGB', 0, 1)
    lw = video_label.winfo_width()
    lh = video_label.winfo_height()
    if lw > 1 and lh > 1:
        pil_img = ImageOps.contain(pil_img, (lw, lh))
    imgtk = ImageTk.PhotoImage(pil_img)
    video_label.config(image=imgtk)
    video_label._imgtk = imgtk  # keep reference to prevent garbage collection

def poll():
    if not loading and player:
        frame, val = player.get_frame()
        if frame is not None:
            _display(frame)
        pts = player.get_pts()
        # get_pts() only advances while playing, so pausing naturally freezes the elapsed count
        if val == 'eof' or (pts >= 0 and pts - seek_start_pts >= length):
            loop()
    root.after(16, poll)  # ~60fps poll

loop()
root.after(16, poll)
root.mainloop()
