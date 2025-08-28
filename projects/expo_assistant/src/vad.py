# VAD(webrtcvad 또는 silero-vad)
# src/vad.py
"""
VAD(무음/잡음 제거 & 세그먼트 검출) 모듈
- webrtcvad 기반
- 입력이 WAV(16k/mono/16bit)일 때만 적용. 그 외 포맷이면 원본 그대로 반환/전체구간 처리.
- 외부 의존 최소화를 위해 포맷 변환은 수행하지 않음.

공개 함수:
    trim_silence(wav_bytes, aggressiveness=2, frame_ms=30) -> wav_bytes
    detect_segments(wav_bytes, aggressiveness=2, frame_ms=30, max_silence_ms=600) -> List[(start_sec, end_sec)]
"""

from __future__ import annotations
import io
import wave
import contextlib
from typing import List, Tuple

try:
    import webrtcvad  # type: ignore
except Exception as e:  # pragma: no cover
    webrtcvad = None
    _vad_import_err = e

# ---- 내부 유틸 ----
def _is_wav_16k_mono_16bit(wav_bytes: bytes) -> bool:
    try:
        with contextlib.closing(wave.open(io.BytesIO(wav_bytes), "rb")) as wf:
            return (wf.getnchannels() == 1 and wf.getframerate() == 16000 and wf.getsampwidth() == 2)
    except Exception:
        return False

def _read_wav_pcm(wav_bytes: bytes) -> Tuple[int, int, int, bytes]:
    """WAV(16k/mono/16bit) 전제. (sr, ch, sampwidth, pcm) 반환"""
    with contextlib.closing(wave.open(io.BytesIO(wav_bytes), "rb")) as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        pcm = wf.readframes(wf.getnframes())
    return sr, ch, sw, pcm

def _write_wav_pcm(pcm: bytes, sr: int = 16000, ch: int = 1, sw: int = 2) -> bytes:
    buf = io.BytesIO()
    with contextlib.closing(wave.open(buf, "wb")) as out_wav:
        out_wav.setnchannels(ch)
        out_wav.setsampwidth(sw)
        out_wav.setframerate(sr)
        out_wav.writeframes(pcm)
    return buf.getvalue()

def _split_frames(pcm: bytes, sr: int, frame_ms: int) -> List[bytes]:
    frame_bytes = int(sr * frame_ms / 1000) * 2  # 16-bit mono 기준
    return [pcm[i:i + frame_bytes] for i in range(0, len(pcm), frame_bytes) if len(pcm[i:i + frame_bytes]) == frame_bytes]

# ---- 공개 API ----
def trim_silence(wav_bytes: bytes, aggressiveness: int = 2, frame_ms: int = 30) -> bytes:
    """
    webrtcvad로 무음/잡음 구간 제거한 WAV 바이트 반환.
    - 입력이 16k/mono/16bit WAV가 아니면 원본 반환.
    - 너무 과도하게 제거되는 경우가 있으면 후처리로 원본 반환 고려.
    """
    if webrtcvad is None:
        return wav_bytes
    if not _is_wav_16k_mono_16bit(wav_bytes):
        return wav_bytes

    sr, ch, sw, pcm = _read_wav_pcm(wav_bytes)
    assert sr == 16000 and ch == 1 and sw == 2
    vad = webrtcvad.Vad(int(aggressiveness))

    frames = _split_frames(pcm, sr, frame_ms)
    voiced = bytearray()
    for fr in frames:
        if vad.is_speech(fr, sr):
            voiced.extend(fr)

    # 발화가 거의 없으면 원본 유지(과컷 방지)
    if len(voiced) < (len(pcm) * 0.1):
        return wav_bytes

    return _write_wav_pcm(bytes(voiced), sr=sr, ch=ch, sw=sw)

def detect_segments(
    wav_bytes: bytes,
    aggressiveness: int = 2,
    frame_ms: int = 30,
    max_silence_ms: int = 600
) -> List[Tuple[float, float]]:
    """
    webrtcvad로 발화 세그먼트 구간(초 단위) 반환.
    - 입력이 16k/mono/16bit WAV가 아니면 [0, 전체길이] 1개 세그먼트 반환.
    - max_silence_ms: 해당 길이 이상의 연속 무음이 나오면 세그먼트 종료로 간주.
    """
    if webrtcvad is None or not _is_wav_16k_mono_16bit(wav_bytes):
        # 전체 길이를 계산하여 단일 세그먼트 반환
        try:
            with contextlib.closing(wave.open(io.BytesIO(wav_bytes), "rb")) as wf:
                dur = wf.getnframes() / float(wf.getframerate())
        except Exception:
            dur = 0.0
        return [(0.0, max(dur, 0.0))]

    sr, ch, sw, pcm = _read_wav_pcm(wav_bytes)
    vad = webrtcvad.Vad(int(aggressiveness))
    frames = _split_frames(pcm, sr, frame_ms)

    segs: List[Tuple[float, float]] = []
    in_speech = False
    seg_start = 0
    silence_cnt = 0
    max_silence_frames = max(1, int(max_silence_ms / frame_ms))

    for i, fr in enumerate(frames):
        is_sp = vad.is_speech(fr, sr)
        if is_sp:
            if not in_speech:
                in_speech = True
                seg_start = i
            silence_cnt = 0
        else:
            if in_speech:
                silence_cnt += 1
                if silence_cnt >= max_silence_frames:
                    # 세그먼트 종료
                    start_sec = seg_start * frame_ms / 1000.0
                    end_sec = (i - silence_cnt + 1) * frame_ms / 1000.0
                    if end_sec > start_sec:
                        segs.append((start_sec, end_sec))
                    in_speech = False
                    silence_cnt = 0

    # 끝까지 말하는 경우 꼬리 처리
    if in_speech:
        start_sec = seg_start * frame_ms / 1000.0
        end_sec = len(frames) * frame_ms / 1000.0
        if end_sec > start_sec:
            segs.append((start_sec, end_sec))

    # 세그먼트가 너무 없으면 전체 반환
    if not segs:
        dur = len(pcm) / 2 / sr  # 16-bit mono
        return [(0.0, dur)]

    return segs


# ---- 스모크 테스트 ----
if __name__ == "__main__":
    import os
    path = os.environ.get("VAD_TEST_WAV", "")
    if not path:
        print("환경변수 VAD_TEST_WAV에 16k/mono/16bit WAV 경로를 지정하세요.")
    else:
        with open(path, "rb") as f:
            b = f.read()
        tb = trim_silence(b)
        print("원본 길이:", len(b), "트리밍 길이:", len(tb))
        print("세그먼트:", detect_segments(b))
        print("OK ✔")
