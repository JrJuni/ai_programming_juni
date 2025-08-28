# src/schema.py
"""
데이터 스키마(도메인 모델 + LLM 구조화 출력용 모델)
- DB 테이블과 1:1로 매핑되는 Pydantic 모델: Consultation, Contact, Company
- LLM 추출용 모델: ExtractedConsultation, ExtractedContact, ExtractionBundle
- 엑셀 내보내기에서 제외할 비공개 필드 상수: PRIVATE_FIELDS
- 유틸: 리스트 필드 자동 정규화, 전화/언어 검증, JSON Schema 제공

사용 예시는 파일 하단의 __main__ 스니펫 참조.
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr, field_validator
import re
import json

# 엑셀/외부 공유에서 숨길 비공개 필드
PRIVATE_FIELDS = {"stt_conf", "transcript", "lang"}

_PHONE_ALLOWED = re.compile(r"^[0-9+\-\s().]{5,30}$")
_LANG_ALLOWED = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")  # 예: ko, en, en-US

# Pydantic 버전 체커
try:
    from pydantic import field_validator  # v2
except ImportError:  # v1 fallback
    from pydantic import validator as field_validator  # 타입힌트 경고는 무시 가능

# ---------------------------
# 공통 유틸
# ---------------------------
def _normalize_str_list(v: Any) -> List[str]:
    """문자열/리스트 혼용 입력을 안전하게 리스트[str]로 변환."""
    if v is None or v == "":
        return []
    if isinstance(v, list):
        # 항목 별 공백 제거 + 빈 항목 필터
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        # ';' 또는 ',' 기준 분할 허용
        parts = re.split(r"[;,]", v)
        return [p.strip() for p in parts if p.strip()]
    # 기타 타입은 문자열로 캐스팅
    return [str(v).strip()]


def json_schema_for_llm(model: type[BaseModel]) -> Dict[str, Any]:
    """
    LLM에 넘길 JSON Schema(dict). pydantic v2의 json_schema()를 thin wrapper로 제공.
    """
    return model.model_json_schema()


# ---------------------------
# DB 매핑 모델
# ---------------------------
class Consultation(BaseModel):
    """현장 상담 레코드 (DB: consultations)"""
    id: Optional[int] = None
    source: Optional[str] = Field(default=None, description="전시회/부스명")
    company_id: Optional[int] = Field(default=None, description="companies.id")
    company_name: Optional[str] = Field(default=None, description="입력 당시 회사명 스냅샷")
    comments: Optional[str] = None
    field: Optional[str] = Field(default=None, description="산업/도메인")
    ai_functions: Optional[str] = Field(default=None, description="예: 불량검사")
    requirements: List[str] = Field(default_factory=list, description="요구 사양 리스트")
    ai_models: List[str] = Field(default_factory=list, description="언급된/제안된 AI 모델")
    next_action: Optional[str] = None
    contact_id: Optional[int] = None

    # 비공개(엑셀 제외)
    stt_conf: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    transcript: Optional[str] = None
    lang: Optional[str] = Field(default="ko", description="예: ko/en/en-US")

    # 메타
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # ---- 밸리데이터 ----
    @field_validator("company_name", "source", "field", "ai_functions", "next_action", mode="before")
    @classmethod
    def _strip_strings(cls, v: Any) -> Any:
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v

    @field_validator("requirements", "ai_models", mode="before")
    @classmethod
    def _to_list(cls, v: Any) -> List[str]:
        return _normalize_str_list(v)

    @field_validator("lang")
    @classmethod
    def _check_lang(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _LANG_ALLOWED.match(v):
            raise ValueError("lang 형식은 'ko', 'en', 'en-US' 등이어야 합니다.")
        return v


class Contact(BaseModel):
    """담당자 레코드 (DB: contacts)"""
    id: Optional[int] = None
    name: str
    job_title: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    company_id: Optional[int] = None
    created_at: Optional[datetime] = None

    @field_validator("name", "job_title", "phone", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not _PHONE_ALLOWED.match(v):
            raise ValueError("phone은 숫자/공백/+-(). 만 허용합니다.")
        return v

# 우선순위 범위 상수
PRIORITY_MIN = 0
PRIORITY_MAX = 3

class Company(BaseModel):
    """회사 레코드 (DB: companies)"""
    id: Optional[int] = None
    name: str
    status: Optional[str] = None
    description: Optional[str] = None
    # ▼ priority: 0~3으로 변경(기존 0~10 → 0~3)
    priority: Optional[int] = Field(
        default=None,
        ge=PRIORITY_MIN,
        le=PRIORITY_MAX,
        description="회사 우선순위 (0~3)"
    )
    industry: Optional[str] = None
    company_size: Optional[str] = None
    sales_volume_usd_m: Optional[float] = Field(default=None, ge=0)
    website: Optional[str] = None
    country: Optional[str] = None
    state_city: Optional[str] = None
    created_at: Optional[datetime] = None

    @field_validator("name", "status", "industry", "company_size", "country", "state_city", mode="before")
    @classmethod
    def _strip_basic(cls, v: Any) -> Any:
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v

    # ▼ priority 정규화(문자/None 허용, 0~3 클램프)
    @field_validator("priority", mode="before")
    @classmethod
    def _normalize_priority(cls, v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            i = int(v)
        except Exception:
            raise ValueError("priority는 0~3 정수여야 합니다.")
        if i < PRIORITY_MIN:
            i = PRIORITY_MIN
        if i > PRIORITY_MAX:
            i = PRIORITY_MAX
        return i


# ---------------------------
# LLM 구조화 출력용 모델
# ---------------------------
class ExtractedConsultation(BaseModel):
    """
    LLM이 추출해야 하는 상담 필드(오프라인/온라인 공통).
    - company_name은 자유기입(없는 경우 빈값 허용)
    - requirements/ai_models는 리스트 권장(문자열이면 세미콜론/콤마 분할)
    """
    source: Optional[str] = None
    company_name: Optional[str] = None
    comments: Optional[str] = None
    field: Optional[str] = None
    ai_functions: Optional[str] = None
    requirements: List[str] = Field(default_factory=list)
    ai_models: List[str] = Field(default_factory=list)
    next_action: Optional[str] = None
    lang: Optional[str] = "ko"

    @field_validator("requirements", "ai_models", mode="before")
    @classmethod
    def _to_list(cls, v: Any) -> List[str]:
        return _normalize_str_list(v)


class ExtractedContact(BaseModel):
    """LLM이 추출하는 담당자 정보(명함/사후 보완 가능)"""
    name: Optional[str] = None
    job_title: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        if not _PHONE_ALLOWED.match(v):
            raise ValueError("phone은 숫자/공백/+-(). 만 허용합니다.")
        return v


class ExtractionBundle(BaseModel):
    """
    LLM 출력 번들(권장): consultation + contact
    - contact는 선택(없으면 None)
    """
    consultation: ExtractedConsultation
    contact: Optional[ExtractedContact] = None


# ---------------------------
# 매핑 유틸 (LLM → DB 레코드용)
# ---------------------------
def bundle_to_consultation(
    bundle: ExtractionBundle,
    company_id: Optional[int] = None,
    contact_id: Optional[int] = None,
) -> Consultation:
    """LLM 번들을 DB 입력용 Consultation으로 변환."""
    c = bundle.consultation
    return Consultation(
        source=c.source,
        company_id=company_id,
        company_name=(c.company_name or None),
        comments=c.comments,
        field=c.field,
        ai_functions=c.ai_functions,
        requirements=c.requirements,
        ai_models=c.ai_models,
        next_action=c.next_action,
        contact_id=contact_id,
        lang=c.lang or "ko",
    )


def bundle_to_contact(bundle: ExtractionBundle, company_id: Optional[int] = None) -> Optional[Contact]:
    """LLM 번들을 DB 입력용 Contact으로 변환(없으면 None)"""
    if not bundle.contact:
        return None
    cc = bundle.contact
    if not any([cc.name, cc.email, cc.phone]):  # 완전히 비어 있으면 None
        return None
    return Contact(
        name=cc.name or "",
        job_title=cc.job_title,
        phone=cc.phone,
        email=cc.email,
        company_id=company_id,
    )


# ---------------------------
# LLM에 전달할 JSON Schema 헬퍼
# ---------------------------
def llm_json_schema() -> Dict[str, Any]:
    """
    ExtractionBundle의 JSON Schema(dict) 반환.
    - OpenAI/Anthropic/로컬(llama.cpp)에서 구조화 출력 강제에 사용.
    """
    return ExtractionBundle.model_json_schema()


# ---------------------------
# 간단 검증 스니펫
# ---------------------------
if __name__ == "__main__":
    # 1) 문자열 입력을 리스트로 자동 변환되는지 확인
    ec = ExtractedConsultation(
        source="ISEC2025",
        company_name="LG",
        comments="day 1 오전 - ai 추진중, 본주 명함 전달",
        field="스마트팩토리",
        ai_functions="불량검사",
        requirements="해상도 1080에서 Yolo_v12_seg 20fps; 최소 20fps",
        ai_models="Yolo_v12, YOLOv9",
        next_action="추가 미팅 조율",
        lang="ko",
    )
    assert ec.requirements == ["해상도 1080에서 Yolo_v12_seg 20fps", "최소 20fps"]
    assert ec.ai_models == ["Yolo_v12", "YOLOv9"]

    # 2) 연락처 밸리데이션
    ex_contact = ExtractedContact(name="정상화", job_title="부팀장", phone="+82 10-1234-5678")
    bundle = ExtractionBundle(consultation=ec, contact=ex_contact)

    # 3) 번들을 DB 모델로 변환(회사/담당자 id는 None 가정)
    consult = bundle_to_consultation(bundle)
    contact = bundle_to_contact(bundle)

    assert consult.company_name == "LG"
    assert "불량검사" in (consult.ai_functions or "")
    assert contact and contact.name == "정상화"

    # 4) JSON Schema 점검(LLM 전달용)
    schema_dict = llm_json_schema()
    assert isinstance(schema_dict, dict) and "properties" in schema_dict

    print("schema.py smoke test OK ✔")
