# src/model_config.py
"""
모델/AI 설정 및 팩토리 (단일 소스)
- configs/model_config.yaml 이 없으면 '프로젝트 루트/configs'에 자동 생성
- STT(faster-whisper) 및 요약/정리 LLM(offline/openai/anthropic) 클라이언트/파라미터 중앙 관리
- 시크릿 해석 우선순위: streamlit.secrets > 환경변수 > keyring

필요 패키지:
  pip install pyyaml
  pip install faster-whisper
  # 선택
  pip install openai anthropic keyring streamlit
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Tuple, Any, Dict
from pathlib import Path
import logging
import os

# ---------- 의존성 ----------
try:
    import yaml
except ModuleNotFoundError as e:
    raise ModuleNotFoundError(
        "PyYAML이 필요합니다. 가상환경 활성화 후 `pip install pyyaml`을 실행하세요."
    ) from e

# streamlit.secrets 지원(있으면 사용)
try:
    import streamlit as st  # type: ignore
    _HAS_STREAMLIT = True
except Exception:
    st = None  # type: ignore
    _HAS_STREAMLIT = False

# keyring(선택)
try:
    import keyring  # type: ignore
except Exception:
    keyring = None

# faster-whisper(STT)
try:
    from faster_whisper import WhisperModel  # type: ignore
except Exception as e:
    WhisperModel = None  # type: ignore
    _FW_IMPORT_ERR = e

logger = logging.getLogger(__name__)


# =========================
# 경로 유틸
# =========================
def _project_root() -> Path:
    """프로젝트 루트: src/ 의 부모 디렉터리"""
    return Path(__file__).resolve().parents[1]

def _default_yaml_path(yaml_path: Optional[str]) -> Path:
    """
    model_config.yaml의 기본 경로를 결정.
    우선순위:
      1) 함수 인자 yaml_path
      2) EXPO_CONFIG_DIR 환경변수 + 'model_config.yaml'
      3) 프로젝트 루트/configs/model_config.yaml
    """
    if yaml_path:
        return Path(yaml_path)
    env_dir = os.getenv("EXPO_CONFIG_DIR")
    if env_dir:
        return Path(env_dir) / "model_config.yaml"
    return _project_root() / "configs" / "model_config.yaml"


# =========================
# 설정 데이터클래스
# =========================
@dataclass
class STTConfig:
    provider: str = "faster_whisper"   # 미래 교체 대비
    model_name: str = "small"          # "tiny"|"base"|"small"|"medium"|"large-v3"
    model_path: Optional[str] = None   # 로컬 CT2 변환 폴더(있으면 경로 우선)
    device: str = "cpu"                # "cpu"|"cuda"
    compute_type: str = "int8"         # cpu:int8, cuda:float16 권장
    beam_size: int = 5
    temperature: float = 0.0
    use_vad: bool = True
    vad_aggressiveness: int = 2

@dataclass
class OfflineLLMConfig:
    backend: str = "llama_cpp"         # "llama_cpp"|"ollama"|"llmcpp_http" 등
    model_path: Optional[str] = "models/EXAONE-3.5-2.4B-Instruct-Q8_0.gguf"
    endpoint: Optional[str] = None     # 예: http://localhost:8080/v1/chat/completions (서버형일 때)
    model_name: Optional[str] = "EXAONE-3.5-2.4B-Instruct-Q8_0"
    max_tokens: int = 1024
    temperature: float = 0.2

@dataclass
class OpenAIConfig:
    model: str = "gpt-4o-mini"
    api_key: Optional[str] = None      # 미설정 시 env/secrets/keyring에서 해석
    base_url: Optional[str] = None     # 사내 프록시/게이트웨이 사용 시
    request_timeout: int = 30

@dataclass
class AnthropicConfig:
    model: str = "claude-3-5-sonnet-latest"
    api_key: Optional[str] = None
    request_timeout: int = 30

@dataclass
class LLMConfig:
    mode: str = "offline"              # "offline"|"openai"|"anthropic"
    offline: OfflineLLMConfig = field(default_factory=OfflineLLMConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)

@dataclass
class ModelConfig:
    stt: STTConfig = field(default_factory=STTConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)


# =========================
# YAML 템플릿/로드
# =========================
_DEFAULT_YAML = """# configs/model_config.yaml (자동 생성 템플릿)
stt:
  provider: faster_whisper
  model_name: small
  model_path: null          # 예: models/whisper/small-int8 (CT2 변환 폴더)
  device: cpu
  compute_type: int8
  beam_size: 5
  temperature: 0.0
  use_vad: true
  vad_aggressiveness: 2

llm:
  mode: offline             # offline | openai | anthropic
  offline:
    backend: llama_cpp
    model_path: models/EXAONE-3.5-2.4B-Instruct-Q8_0.gguf   # 기본 로컬 요약 모델(요청 반영)
    endpoint: null
    model_name: EXAONE-3.5-2.4B-Instruct-Q8_0
    max_tokens: 1024
    temperature: 0.2
  openai:
    model: gpt-4o-mini
    api_key: null           # 미설정 → OPENAI_API_KEY / secrets / keyring에서 자동 해석
    base_url: null
    request_timeout: 30
  anthropic:
    model: claude-3-5-sonnet-latest
    api_key: null           # 미설정 → ANTHROPIC_API_KEY / secrets / keyring에서 자동 해석
    request_timeout: 30
"""

def _load_yaml(path: Path) -> Dict[str, Any]:
    """YAML 로드. 없으면 템플릿 생성 후 로드."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_DEFAULT_YAML, encoding="utf-8")
        logger.info(f"[model_config] 기본 템플릿 생성: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# =========================
# 시크릿 해석
# =========================
def _get_secret(name: str) -> Optional[str]:
    """
    시크릿 값 조회 우선순위:
      1) streamlit.secrets[name]
      2) os.environ[name]
      3) keyring.get_password("expo-agent", name)
    """
    # 1) streamlit.secrets
    if _HAS_STREAMLIT:
        try:
            val = st.secrets.get(name)  # type: ignore
            if val:
                return str(val)
        except Exception:
            pass
    # 2) 환경변수
    val = os.getenv(name)
    if val:
        return val
    # 3) keyring
    if keyring is not None:
        try:
            val = keyring.get_password("expo-agent", name)
            if val:
                return val
        except Exception:
            pass
    return None


# =========================
# 레지스트리 (팩토리/캐시)
# =========================
class ModelRegistry:
    """모든 모델/클라이언트를 중앙에서 생성/캐시하는 팩토리"""
    def __init__(self, cfg: ModelConfig):
        self.cfg = cfg
        self._asr_cache: Dict[Tuple[str, str, str, str], Any] = {}
        self._openai_client = None
        self._anthropic_client = None

    # ---- STT: faster-whisper ----
    def get_asr_model(
        self,
        model_name: Optional[str] = None,
        model_path: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
    ):
        """WhisperModel 인스턴스 반환(캐시 사용)."""
        if WhisperModel is None:
            raise RuntimeError(f"faster-whisper 로드 실패: {_FW_IMPORT_ERR}")

        stt = self.cfg.stt
        name = model_name or stt.model_name
        path = model_path or (stt.model_path or "")
        dev = device or stt.device
        ctype = compute_type or stt.compute_type

        key = (name, dev, ctype, path)
        if key in self._asr_cache:
            return self._asr_cache[key]

        # 로컬 경로 우선 사용(존재할 때), 아니면 모델명
        model_id = path if (path and Path(path).exists()) else name
        logger.info(f"[ASR] Load Whisper: id={model_id}, device={dev}, compute_type={ctype}")
        model = WhisperModel(model_id, device=dev, compute_type=ctype)
        self._asr_cache[key] = model
        return model

    # ---- Summarizer/LLM ----
    def get_summarizer_client(self) -> Tuple[str, Any]:
        """
        반환: (mode, client_or_params)
          - "offline": dict(params)  (summarizer.py에서 backend/endpoint/model_path를 사용해 직접 호출)
          - "openai": OpenAI Client 객체 또는 dict(params)
          - "anthropic": Anthropic Client 객체 또는 dict(params)
        """
        mode = (self.cfg.llm.mode or "offline").lower()

        if mode == "openai":
            if self._openai_client:
                return "openai", self._openai_client
            # 키 해석
            api_key = self.cfg.llm.openai.api_key or _get_secret("OPENAI_API_KEY")
            base_url = self.cfg.llm.openai.base_url or os.getenv("OPENAI_BASE_URL")
            if not api_key:
                logger.warning("[LLM] OPENAI_API_KEY 미설정. dict 파라미터만 반환합니다.")
                return "openai", {
                    "model": self.cfg.llm.openai.model,
                    "api_key": None,
                    "base_url": base_url,
                    "request_timeout": self.cfg.llm.openai.request_timeout,
                }
            # 실제 클라이언트 생성(선택 설치)
            try:
                from openai import OpenAI  # type: ignore
                client = OpenAI(api_key=api_key, base_url=base_url)
                self._openai_client = client
                return "openai", client
            except Exception as e:
                logger.warning(f"[LLM] openai 패키지 미설치/오류: {e}. dict 파라미터 반환.")
                return "openai", {
                    "model": self.cfg.llm.openai.model,
                    "api_key": api_key,
                    "base_url": base_url,
                    "request_timeout": self.cfg.llm.openai.request_timeout,
                }

        if mode == "anthropic":
            if self._anthropic_client:
                return "anthropic", self._anthropic_client
            api_key = self.cfg.llm.anthropic.api_key or _get_secret("ANTHROPIC_API_KEY")
            if not api_key:
                logger.warning("[LLM] ANTHROPIC_API_KEY 미설정. dict 파라미터만 반환합니다.")
                return "anthropic", {
                    "model": self.cfg.llm.anthropic.model,
                    "api_key": None,
                    "request_timeout": self.cfg.llm.anthropic.request_timeout,
                }
            try:
                import anthropic  # type: ignore
                client = anthropic.Anthropic(api_key=api_key)
                self._anthropic_client = client
                return "anthropic", client
            except Exception as e:
                logger.warning(f"[LLM] anthropic 패키지 미설치/오류: {e}. dict 파라미터 반환.")
                return "anthropic", {
                    "model": self.cfg.llm.anthropic.model,
                    "api_key": api_key,
                    "request_timeout": self.cfg.llm.anthropic.request_timeout,
                }

        # offline 모드: llama.cpp/ollama/로컬 서버 등 파라미터 묶어 반환
        off = self.cfg.llm.offline
        params = {
            "backend": off.backend,
            "model_path": off.model_path,
            "endpoint": off.endpoint,
            "model_name": off.model_name,
            "max_tokens": off.max_tokens,
            "temperature": off.temperature,
        }
        return "offline", params


# =========================
# 설정 로더/싱글톤
# =========================
_REGISTRY: Optional[ModelRegistry] = None

def load_model_config(yaml_path: Optional[str] = None) -> ModelConfig:
    """YAML → ModelConfig 로드(없으면 기본 템플릿 생성)."""
    path = _default_yaml_path(yaml_path)
    raw: Dict[str, Any] = _load_yaml(path)

    stt_raw = raw.get("stt", {}) or {}
    llm_raw = raw.get("llm", {}) or {}

    cfg = ModelConfig(
        stt=STTConfig(**stt_raw),
        llm=LLMConfig(
            mode=llm_raw.get("mode", "offline"),
            offline=OfflineLLMConfig(**(llm_raw.get("offline", {}) or {})),
            openai=OpenAIConfig(**(llm_raw.get("openai", {}) or {})),
            anthropic=AnthropicConfig(**(llm_raw.get("anthropic", {}) or {})),
        )
    )
    return cfg

def get_registry(yaml_path: Optional[str] = None) -> ModelRegistry:
    """전역 레지스트리 싱글톤 반환."""
    global _REGISTRY
    if _REGISTRY is None:
        cfg = load_model_config(yaml_path)
        _REGISTRY = ModelRegistry(cfg)
        logger.info(f"[model_config] using config: {_default_yaml_path(yaml_path)}")
    return _REGISTRY

def reload_registry(yaml_path: Optional[str] = None) -> ModelRegistry:
    """설정 변경 후 레지스트리 재생성."""
    global _REGISTRY
    cfg = load_model_config(yaml_path)
    _REGISTRY = ModelRegistry(cfg)
    logger.info(f"[model_config] reloaded config: {_default_yaml_path(yaml_path)}")
    return _REGISTRY

def config_path(yaml_path: Optional[str] = None) -> Path:
    """현재 사용할 model_config.yaml 경로 조회."""
    return _default_yaml_path(yaml_path)


# =========================
# 스모크 테스트
# =========================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = _default_yaml_path(None)
    print("Config path ->", path)
    reg = get_registry()
    print("STT:", reg.cfg.stt)
    mode, client = reg.get_summarizer_client()
    print("LLM mode:", mode, "client type:", type(client))
    print("model_config.py smoke test OK ✔")
