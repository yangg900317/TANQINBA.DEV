from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

import numpy as np

from app.engine import Engine
from app.synth import SAMPLE_RATE

winmm = ctypes.WinDLL("winmm", use_last_error=True)

WAVE_MAPPER = 0xFFFFFFFF
WHDR_DONE = 0x00000001
WHDR_PREPARED = 0x00000002


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", wintypes.WORD),
        ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD),
        ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD),
        ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]


class WAVEHDR(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_void_p),
        ("dwBufferLength", wintypes.DWORD),
        ("dwBytesRecorded", wintypes.DWORD),
        ("dwUser", ctypes.c_size_t),
        ("dwFlags", wintypes.DWORD),
        ("dwLoops", wintypes.DWORD),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.c_void_p),
    ]


for _name, _args in {
    "waveOutOpen": [ctypes.POINTER(wintypes.HANDLE), wintypes.UINT, ctypes.POINTER(WAVEFORMATEX), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD],
    "waveOutPrepareHeader": [wintypes.HANDLE, ctypes.POINTER(WAVEHDR), wintypes.UINT],
    "waveOutUnprepareHeader": [wintypes.HANDLE, ctypes.POINTER(WAVEHDR), wintypes.UINT],
    "waveOutWrite": [wintypes.HANDLE, ctypes.POINTER(WAVEHDR), wintypes.UINT],
    "waveOutReset": [wintypes.HANDLE],
    "waveOutClose": [wintypes.HANDLE],
}.items():
    getattr(winmm, _name).argtypes = _args
    getattr(winmm, _name).restype = wintypes.UINT


class AudioOutput:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.ok = False
        self.error = ""
        self._handle = wintypes.HANDLE()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._frames = 1024
        self._channels = 2
        self._arrays = [
            np.zeros(self._frames * self._channels, dtype=np.int16)
            for _ in range(4)
        ]
        self._headers = [WAVEHDR() for _ in self._arrays]
        self._submitted = [False for _ in self._arrays]

    def start(self) -> bool:
        fmt = WAVEFORMATEX()
        fmt.wFormatTag = 1
        fmt.nChannels = self._channels
        fmt.nSamplesPerSec = SAMPLE_RATE
        fmt.wBitsPerSample = 16
        fmt.nBlockAlign = fmt.nChannels * fmt.wBitsPerSample // 8
        fmt.nAvgBytesPerSec = SAMPLE_RATE * fmt.nBlockAlign
        result = winmm.waveOutOpen(ctypes.byref(self._handle), WAVE_MAPPER, ctypes.byref(fmt), None, None, 0)
        if result != 0:
            self.error = f"声音设备打开失败（{result}）"
            return False
        for index, header in enumerate(self._headers):
            header.lpData = self._arrays[index].ctypes.data
            header.dwBufferLength = self._arrays[index].nbytes
            header.dwFlags = 0
            prepared = winmm.waveOutPrepareHeader(self._handle, ctypes.byref(header), ctypes.sizeof(header))
            if prepared != 0:
                self.error = f"音频缓冲准备失败（{prepared}）"
                winmm.waveOutClose(self._handle)
                return False
        self.ok = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="guitar-audio", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.5)
        if self.ok:
            winmm.waveOutReset(self._handle)
            for header in self._headers:
                if header.dwFlags & WHDR_PREPARED:
                    winmm.waveOutUnprepareHeader(self._handle, ctypes.byref(header), ctypes.sizeof(header))
            winmm.waveOutClose(self._handle)
            self.ok = False

    def _loop(self) -> None:
        index = 0
        while not self._stop.is_set():
            header = self._headers[index]
            if self._submitted[index] and not (header.dwFlags & WHDR_DONE):
                time.sleep(0.004)
                continue
            mono = self.engine.render(self._frames)
            pcm = np.clip(mono, -1.0, 1.0)
            pcm = (pcm * 32767.0).astype(np.int16)
            stereo = self._arrays[index]
            stereo[0::2] = pcm
            stereo[1::2] = pcm
            wrote = winmm.waveOutWrite(self._handle, ctypes.byref(header), ctypes.sizeof(header))
            if wrote != 0:
                self.error = f"音频写入失败（{wrote}）"
            self._submitted[index] = True
            index = (index + 1) % len(self._headers)
