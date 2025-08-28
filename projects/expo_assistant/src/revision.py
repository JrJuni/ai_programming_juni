# 음성 수정 지시 → JSON Patch 생성(규칙+소형 LLM)
# src/revision.py
# 자연어 수정 지시 → JSON Patch 생성 + 적용
# - 간단 규칙 기반 파서(한글 위주)
# - 지원 필드: company_name, field, ai_functions, comments, next_action, requirements(list), ai_models(list)

from __future__ import annotations
import re
from typing import List, Dict, Any, Tuple

# 대상 필드 매핑(자연어 키워드 → 내부 키)
FIELD_ALIASES = {
    "회사": "company_name",
    "회사명": "company_name",
    "Company": "company_name",
    "도메인": "field",
    "필드": "field",
    "Field": "field",
    "AI 기능": "ai_functions",
    "기능": "ai_functions",
    "AI Functions": "ai_functions",
    "코멘트": "comments",
    "비고": "comments",
    "Comments": "comments",
    "다음 액션": "next_action",
    "Next Action": "next_action",
    "요구사양": "requirements",
    "요구 사항": "requirements",
    "Requirements": "requirements",
    "AI 모델": "ai_models",
    "모델": "ai_models",
    "AI Models": "ai_models",
}

LIST_FIELDS = {"requirements", "ai_models"}

# 유틸: 문자열→토큰 리스트(세미콜론/콤마 기준)
def _split_items(s: str) -> List[str]:
    parts = re.split(r"[;,]", s)
    return [p.strip() for p in parts if p.strip()]

# JSON Patch 적용기
def apply_patch(doc: Dict[str, Any], ops: List[Dict[str, Any]]) -> Dict[str, Any]:
    res = dict(doc)
    for op in ops:
        path = op.get("path", "")
        key = path.lstrip("/")

        if op["op"] == "replace":
            res[key] = op.get("value")
        elif op["op"] == "add":
            if key in LIST_FIELDS:
                lst = list(res.get(key) or [])
                v = op.get("value")
                if isinstance(v, list):
                    for item in v:
                        if item not in lst:
                            lst.append(item)
                else:
                    if v not in lst:
                        lst.append(v)
                res[key] = lst
            else:
                res[key] = op.get("value")
        elif op["op"] == "remove":
            if key in LIST_FIELDS:
                lst = list(res.get(key) or [])
                v = op.get("value")
                if isinstance(v, list):
                    lst = [x for x in lst if x not in v]
                else:
                    lst = [x for x in lst if x != v]
                res[key] = lst
            else:
                res.pop(key, None)
        else:
            # 미지원 op는 무시
            pass
    return res

# 규칙 기반 파서: 자연어 → patch ops
def parse_command_to_patch(command: str) -> List[Dict[str, Any]]:
    """
    입력 예:
      - "회사명을 현대자동차로 바꿔"
      - "요구사양에 25fps 추가"
      - "AI 모델에서 YOLOv9 삭제"
      - "코멘트에 '내주 데모 예정' 추가"
      - "다음 액션을 미팅 예약으로 변경"
    """
    text = command.strip()
    ops: List[Dict[str, Any]] = []

    # 1) "<필드>를/을 <값> (로|으로) (바꿔|변경|수정)"
    m = re.search(r"(회사명|회사|Company|도메인|필드|Field|AI 기능|기능|AI Functions|코멘트|비고|Comments|다음 액션|Next Action)\s*(?:을|를)?\s*['\"]?(.+?)['\"]?\s*(?:로|으로)?\s*(?:바꿔|변경|수정)", text)
    if m:
        field_kor, value = m.group(1), m.group(2)
        k = FIELD_ALIASES.get(field_kor, None)
        if k:
            ops.append({"op": "replace", "path": f"/{k}", "value": value})
        return ops

    # 2) "<필드>에 <값> 추가"
    m = re.search(r"(요구사양|요구 사항|Requirements|AI 모델|모델|AI Models)\s*에\s*['\"]?(.+?)['\"]?\s*(?:를|을)?\s*추가", text)
    if m:
        field_kor, value = m.group(1), m.group(2)
        k = FIELD_ALIASES.get(field_kor, None)
        if k:
            items = _split_items(value)
            ops.append({"op": "add", "path": f"/{k}", "value": items if len(items) > 1 else (items[0] if items else "")})
        return ops

    # 3) "<필드>에서 <값> 삭제"
    m = re.search(r"(요구사양|요구 사항|Requirements|AI 모델|모델|AI Models)\s*에서\s*['\"]?(.+?)['\"]?\s*(?:를|을)?\s*삭제", text)
    if m:
        field_kor, value = m.group(1), m.group(2)
        k = FIELD_ALIASES.get(field_kor, None)
        if k:
            items = _split_items(value)
            ops.append({"op": "remove", "path": f"/{k}", "value": items if len(items) > 1 else (items[0] if items else "")})
        return ops

    # 4) "<필드>를/을 <값>" (간단 할당)
    m = re.search(r"(회사명|회사|Company|도메인|필드|Field|AI 기능|기능|AI Functions|코멘트|비고|Comments|다음 액션|Next Action)\s*(?:을|를)\s*['\"]?(.+?)['\"]?$", text)
    if m:
        field_kor, value = m.group(1), m.group(2)
        k = FIELD_ALIASES.get(field_kor, None)
        if k:
            ops.append({"op": "replace", "path": f"/{k}", "value": value})
        return ops

    # 5) "키 = 값" 형태(예: Company=LG; Field=스마트팩토리)
    m = re.findall(r"([A-Za-z가-힣 ]+?)\s*=\s*([^;]+)", text)
    if m:
        for key_raw, value in m:
            key = key_raw.strip()
            k = FIELD_ALIASES.get(key, None)
            if k:
                if k in LIST_FIELDS:
                    items = _split_items(value)
                    ops.append({"op": "replace", "path": f"/{k}", "value": items})
                else:
                    ops.append({"op": "replace", "path": f"/{k}", "value": value.strip()})
        if ops:
            return ops

    # 못 알아듣는 경우 → no-op
    return ops

# 간단 검증
if __name__ == "__main__":
    base = {
        "company_name": "LG",
        "field": "스마트팩토리",
        "ai_functions": "불량검사",
        "requirements": ["1080p 20fps"],
        "ai_models": ["Yolo_v12"],
        "comments": "본주 명함 전달",
        "next_action": ""
    }
    cmds = [
        "회사명을 현대자동차로 바꿔",
        "요구사양에 25fps 추가",
        "AI 모델에서 Yolo_v12 삭제",
        "다음 액션을 미팅 예약으로 변경",
        "코멘트에 '내주 데모 예정' 추가",
        "Field = 스마트물류; Company = 현대오토에버",
    ]
    doc = dict(base)
    for c in cmds:
        ops = parse_command_to_patch(c)
        doc = apply_patch(doc, ops)
    assert doc["company_name"] in ("현대자동차", "현대오토에버")
    assert "25fps" in doc["requirements"]
    assert "Yolo_v12" not in doc["ai_models"]
    assert "미팅 예약" in doc["next_action"]
    print("revision.py smoke test OK ✔")
