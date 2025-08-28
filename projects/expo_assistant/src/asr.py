# STT 래퍼(faster-whisper), 언어/신뢰도/세그먼트
# src/asr.py
"""
ASR(STT) 래퍼 - faster-whisper (+ model_config 연동)
- Whisper 모델 로드는 model_config의 레지스트리를 통해 수행
- (옵션)VAD: vad.trim_silence() 사용(입력이 WAV 16k/mono/16bit일 때만 실효)
- 폴백 체인: small -> base -> tiny

공개 함수:
    transcribe_bytes(..., override: dict|None)  # override로 model_name/path/device 등 일시 변경
    transcribe_file(...)
"""

from __future__ import annotations
import os
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# 내부 모듈
from model_config import get_registry
try:
    from .vad import trim_silence
except Exception:
    trim_silence = None  # type: ignore

# ----- 유틸 -----
def _bytes_to_tempfile(b: bytes, suffix: str = ".wav") -> str:
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tf.write(b); tf.flush(); tf.close()
    return tf.name

def _do_transcribe_with_model(path: str, model, lang_hint: Optional[str], beam_size: int, temperature: float) -> Dict[str, Any]:
    segments, info = model.transcribe(
        path,
        language=lang_hint if lang_hint else None,
        task="transcribe",
        beam_size=beam_size,
        vad_filter=False,
        word_timestamps=False,
        temperature=temperature
    )
    seg_list = list(segments)
    text = "".join(s.text for s in seg_list).strip()
    confs = []
    for s in seg_list:
        p = getattr(s, "no_speech_prob", None)
        if p is not None:
            confs.append(max(0.0, min(1.0, 1.0 - float(p))))
    avg_conf = float(sum(confs) / len(confs)) if confs else 0.0
    lang = getattr(info, "language", None) or (lang_hint or "unknown")
    return {
        "text": text,
        "segments": [{"id": i, "start": float(s.start), "end": float(s.end), "text": s.text} for i, s in enumerate(seg_list)],
        "lang": lang,
        "avg_conf": avg_conf
    }

# ----- 공개 API -----
def transcribe_bytes(
    audio_bytes: bytes,
    *,
    lang_hint: str = "ko",
    use_vad: Optional[bool] = None,
    vad_aggressiveness: Optional[int] = None,
    beam_size: Optional[int] = None,
    temperature: Optional[float] = None,
    override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    STT 실행.
    - model_config.yaml 설정을 기본으로 사용
    - override로 일시적 변경 가능: {"model_name": "base", "model_path": "...", "device": "cpu", "compute_type": "int8"}
    """
    if not audio_bytes:
        raise ValueError("audio_bytes가 비어 있습니다.")

    reg = get_registry()
    stt_cfg = reg.cfg.stt

    # VAD 적용 여부/민감도 결정
    use_vad_final = stt_cfg.use_vad if use_vad is None else use_vad
    vad_aggr_final = stt_cfg.vad_aggressiveness if vad_aggressiveness is None else vad_aggressiveness

    processed = audio_bytes
    if use_vad_final and trim_silence is not None:
        try:
            processed = trim_silence(audio_bytes, aggressiveness=int(vad_aggr_final))
        except Exception as e:
            logger.warning(f"[ASR] VAD 선처리 실패 → 원본 사용: {e}")

    path = _bytes_to_tempfile(processed, suffix=".wav")

    # 모델 파라미터
    name = (override or {}).get("model_name", stt_cfg.model_name)
    path_override = (override or {}).get("model_path", stt_cfg.model_path)
    device = (override or {}).get("device", stt_cfg.device)
    ctype = (override or {}).get("compute_type", stt_cfg.compute_type)
    beam = int((override or {}).get("beam_size", stt_cfg.beam_size if beam_size is None else beam_size))
    temp = float((override or {}).get("temperature", stt_cfg.temperature if temperature is None else temperature))

    try:
        model = reg.get_asr_model(model_name=name, model_path=path_override, device=device, compute_type=ctype)
        return _do_transcribe_with_model(path, model, lang_hint, beam, temp)
    except Exception as e:
        # 폴백 체인
        fallback = {"small": "base", "base": "tiny"}
        cur = name
        while cur in fallback:
            nxt = fallback[cur]
            logger.warning(f"[ASR] 실패로 폴백 시도: {cur} → {nxt}. 원인: {e}")
            try:
                model = reg.get_asr_model(model_name=nxt, model_path=None, device=device, compute_type=ctype)
                return _do_transcribe_with_model(path, model, lang_hint, max(1, beam // 2), temp)
            except Exception as e2:
                e = e2
                cur = nxt
        raise RuntimeError(f"[ASR] STT 실패: {e}") from e
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def transcribe_file(
    file_path: str,
    **kwargs
) -> Dict[str, Any]:
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"오디오 파일이 없습니다: {file_path}")
    with open(p, "rb") as f:
        b = f.read()
    return transcribe_bytes(b, **kwargs)


# ---- 스모크 테스트 ----
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    wav_path = os.environ.get("ASR_TEST_WAV", "")
    if not wav_path:
        print("환경변수 ASR_TEST_WAV에 테스트 WAV 경로를 지정하면 스모크 테스트가 수행됩니다.")
    else:
        from model_config import reload_registry
        # 테스트용으로 YAML 갱신을 읽고 싶으면 reload_registry() 사용
        reload_registry()
        with open(wav_path, "rb") as f:
            audio = f.read()
        out = transcribe_bytes(audio, lang_hint="ko")
        print("lang:", out["lang"], "avg_conf:", out["avg_conf"])
        print("text:", out["text"][:120], "...")
        print("segments:", len(out["segments"]))
        print("OK ✔")
