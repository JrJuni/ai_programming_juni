# src/db.py
"""
SQLite 마이그레이션/DAO 모듈
- 테이블: consultations, contacts, companies
- 날짜: date_time 컬럼 제거, created_at(CURRENT_TIMESTAMP)로 자동 기록
- 비공개 필드: stt_conf/transcript/lang (엑셀 내보내기에서 제외)

간단 검증 스니펫은 파일 맨 아래 '__main__' 참고.
"""

from __future__ import annotations
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Iterable, List, Dict, Any, Tuple, Union
from datetime import datetime
import json
import logging

# 외부 도메인 스키마 (Pydantic)
try:
    from .schema import Consultation, Contact, Company
except Exception:  # pragma: no cover - 스니펫 실행용(스키마 미구성일 때)
    Consultation = Dict[str, Any]  # type: ignore
    Contact = Dict[str, Any]       # type: ignore
    Company = Dict[str, Any]       # type: ignore

logger = logging.getLogger(__name__)

# === 경로/DB 설정 ===
DB_PATH = Path("data/app.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# 엑셀 내보내기에서 숨길 필드(안전장치)
PRIVATE_FIELDS = {"stt_conf", "transcript", "lang"}

# === 스키마 DDL ===
DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  name                TEXT NOT NULL UNIQUE,
  status              TEXT,
  description         TEXT,
  priority            INTEGER,
  industry            TEXT,
  company_size        TEXT,
  sales_volume_usd_m  REAL,
  website             TEXT,
  country             TEXT,
  state_city          TEXT,
  created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contacts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,
  job_title   TEXT,
  phone       TEXT,
  email       TEXT,
  company_id  INTEGER,
  created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (company_id) REFERENCES companies(id)
     ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS consultations (
  id                INTEGER PRIMARY KEY AUTOINCREMENT, -- No
  source            TEXT,                              -- 전시회/부스명
  company_id        INTEGER,                           -- companies.id
  company_name      TEXT,                              -- 입력 당시 문자열(스냅샷)
  comments          TEXT,                              -- 현장 코멘트
  field             TEXT,                              -- 산업/도메인
  ai_functions      TEXT,                              -- 예: "불량검사"
  requirements_json TEXT,                              -- ["해상도 1080...", "20fps"]
  ai_models_json    TEXT,                              -- ["Yolo_v12", ...]
  next_action       TEXT,                              -- 다음 액션
  contact_id        INTEGER,                           -- contacts.id

  -- 비공개/엑셀 제외
  stt_conf          REAL,
  transcript        TEXT,
  lang              TEXT,

  created_at        TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at        TEXT,
  FOREIGN KEY (company_id) REFERENCES companies(id)
     ON UPDATE CASCADE ON DELETE SET NULL,
  FOREIGN KEY (contact_id) REFERENCES contacts(id)
     ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_consultations_created ON consultations(created_at);
CREATE INDEX IF NOT EXISTS idx_consultations_company ON consultations(company_id);
CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_id);
"""


# === 커넥션 헬퍼 ===
@contextmanager
def get_conn(path: Optional[Path] = None):
    """SQLite 커넥션 컨텍스트. WAL, FK, row_factory 설정."""
    p = path or DB_PATH
    conn = sqlite3.connect(p.as_posix(), check_same_thread=False)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("DB error")
        raise
    finally:
        conn.close()


# === 마이그레이션 ===
def init_migrate(db_path: Optional[Path] = None) -> None:
    """테이블/인덱스 생성(존재 시 무시)"""
    with get_conn(db_path) as conn:
        conn.executescript(DDL)


# === 유틸 ===
def _json_dumps(v: Optional[Iterable[str]]) -> str:
    return json.dumps(list(v) if v else [], ensure_ascii=False)

def _json_loads(s: Optional[str]) -> List[str]:
    try:
        return list(json.loads(s or "[]"))
    except Exception:
        return []

def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}

def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# === Companies ===
def get_or_create_company_by_name(name: str) -> int:
    """회사명으로 companies.id 조회/생성."""
    if not name:
        raise ValueError("company name is required")
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO companies(name) VALUES(?);", (name,))
        cur = conn.execute("SELECT id FROM companies WHERE name=?;", (name,))
        row = cur.fetchone()
        if not row:
            raise RuntimeError("failed to get_or_create company")
        return int(row["id"])


def insert_company(company: Union[Company, Dict[str, Any]]) -> int:
    data = company if isinstance(company, dict) else company.model_dump(exclude_none=True)  # type: ignore
    cols = [
        "name", "status", "description", "priority", "industry",
        "company_size", "sales_volume_usd_m", "website", "country", "state_city"
    ]
    values = [data.get(c) for c in cols]
    placeholders = ",".join("?" for _ in cols)
    with get_conn() as conn:
        cur = conn.execute(
            f"INSERT INTO companies ({','.join(cols)}) VALUES ({placeholders});",
            values,
        )
        return int(cur.lastrowid)


def get_company(company_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM companies WHERE id=?;", (company_id,))
        row = cur.fetchone()
        return _row_to_dict(row) if row else None


# === Contacts ===
def insert_contact(contact: Union[Contact, Dict[str, Any]]) -> int:
    data = contact if isinstance(contact, dict) else contact.model_dump(exclude_none=True)  # type: ignore
    cols = ["name", "job_title", "phone", "email", "company_id"]
    values = [data.get(c) for c in cols]
    placeholders = ",".join("?" for _ in cols)
    with get_conn() as conn:
        cur = conn.execute(
            f"INSERT INTO contacts ({','.join(cols)}) VALUES ({placeholders});",
            values,
        )
        return int(cur.lastrowid)


def get_contact(contact_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM contacts WHERE id=?;", (contact_id,))
        row = cur.fetchone()
        return _row_to_dict(row) if row else None


# === Consultations ===
def insert_consultation(consult: Union[Consultation, Dict[str, Any]]) -> int:
    """
    상담 레코드 입력.
    - requirements / ai_models 는 JSON 배열로 직렬화
    - company_name이 비어있고 company_id가 있으면 companies.name 스냅샷 자동 채움
    """
    data = consult if isinstance(consult, dict) else consult.model_dump(exclude_none=True)  # type: ignore

    # 스냅샷 자동 채움
    if not data.get("company_name") and data.get("company_id"):
        comp = get_company(int(data["company_id"]))
        if comp and comp.get("name"):
            data["company_name"] = comp["name"]

    data["requirements_json"] = _json_dumps(data.get("requirements"))
    data["ai_models_json"] = _json_dumps(data.get("ai_models"))

    cols = [
        "source", "company_id", "company_name", "comments", "field", "ai_functions",
        "requirements_json", "ai_models_json", "next_action", "contact_id",
        "stt_conf", "transcript", "lang"
    ]
    values = [data.get(c) for c in cols]
    placeholders = ",".join("?" for _ in cols)

    with get_conn() as conn:
        cur = conn.execute(
            f"INSERT INTO consultations ({','.join(cols)}) VALUES ({placeholders});",
            values,
        )
        return int(cur.lastrowid)


def update_consultation(consult_id: int, patch: Dict[str, Any]) -> None:
    """
    부분 업데이트.
    - requirements/ai_models 들어오면 JSON 재직렬화
    - updated_at 자동 세팅
    """
    if not patch:
        return

    patch = dict(patch)
    if "requirements" in patch:
        patch["requirements_json"] = _json_dumps(patch.pop("requirements"))
    if "ai_models" in patch:
        patch["ai_models_json"] = _json_dumps(patch.pop("ai_models"))

    cols = []
    vals = []
    for k, v in patch.items():
        if k in {"id", "created_at"}:
            continue
        cols.append(f"{k}=?")
        vals.append(v)
    cols.append("updated_at=?")
    vals.append(_now_iso())
    vals.append(consult_id)

    with get_conn() as conn:
        conn.execute(f"UPDATE consultations SET {', '.join(cols)} WHERE id=?;", vals)


def get_consultation(consult_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM consultations WHERE id=?;", (consult_id,))
        row = cur.fetchone()
        if not row:
            return None
        d = _row_to_dict(row)
        d["requirements"] = _json_loads(d.pop("requirements_json", None))
        d["ai_models"] = _json_loads(d.pop("ai_models_json", None))
        return d


def list_consultations(
    limit: int = 100,
    offset: int = 0,
    source: Optional[str] = None,
    company_id: Optional[int] = None,
    company_name_like: Optional[str] = None,
    created_from: Optional[str] = None,  # "YYYY-MM-DD"
    created_to: Optional[str] = None,    # "YYYY-MM-DD"
) -> List[Dict[str, Any]]:
    """필터 목록. created_at은 날짜 문자열(UTC) 기반 범위 필터."""
    where = []
    params: List[Any] = []

    if source:
        where.append("source = ?")
        params.append(source)
    if company_id is not None:
        where.append("company_id = ?")
        params.append(company_id)
    if company_name_like:
        where.append("company_name LIKE ?")
        params.append(f"%{company_name_like}%")
    if created_from:
        where.append("date(substr(created_at,1,10)) >= date(?)")
        params.append(created_from)
    if created_to:
        where.append("date(substr(created_at,1,10)) <= date(?)")
        params.append(created_to)

    q = "SELECT * FROM consultations"
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_conn() as conn:
        cur = conn.execute(q, params)
        rows = cur.fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = _row_to_dict(r)
            d["requirements"] = _json_loads(d.pop("requirements_json", None))
            d["ai_models"] = _json_loads(d.pop("ai_models_json", None))
            out.append(d)
        return out


# === 엑셀 내보내기용 조회 ===
def fetch_consultations_for_export(
    ids: Optional[List[int]] = None
) -> List[Dict[str, Any]]:
    """
    엑셀 시트1(Consultations)용 정규화 레코드 목록.
    - PRIVATE_FIELDS 자동 제외
    - requirements/ai_models는 '; '로 조인하지 않고 원본 리스트를 반환
      (포맷팅은 export_xlsx.py에서 처리)
    """
    where = ""
    params: List[Any] = []
    if ids:
        placeholders = ",".join("?" for _ in ids)
        where = f"WHERE id IN ({placeholders})"
        params = list(ids)

    with get_conn() as conn:
        cur = conn.execute(f"SELECT * FROM consultations {where} ORDER BY id ASC;", params)
        rows = cur.fetchall()

    result: List[Dict[str, Any]] = []
    for r in rows:
        d = _row_to_dict(r)
        d["requirements"] = _json_loads(d.pop("requirements_json", None))
        d["ai_models"] = _json_loads(d.pop("ai_models_json", None))
        # 비공개 필드 제거(이중 안전장치)
        for pf in PRIVATE_FIELDS:
            d.pop(pf, None)
        result.append(d)
    return result


def fetch_contacts_for_export(ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    """엑셀 시트2(Contacts)용. company_name 조인 포함(있으면)."""
    where = ""
    params: List[Any] = []
    if ids:
        placeholders = ",".join("?" for _ in ids)
        where = f"WHERE c.id IN ({placeholders})"
        params = list(ids)

    q = """
    SELECT c.*, co.name AS company_name
    FROM contacts c
    LEFT JOIN companies co ON co.id = c.company_id
    {where}
    ORDER BY c.id ASC;
    """.format(where=where)

    with get_conn() as conn:
        cur = conn.execute(q, params)
        rows = cur.fetchall()
        return [_row_to_dict(r) for r in rows]


# === 간단 검증 스니펫 ===
if __name__ == "__main__":
    """
    간단 동작 검증:
    1) 마이그레이션 → 회사/담당자/상담 입력
    2) 조회/내보내기용 데이터 확인
    """
    logging.basicConfig(level=logging.INFO)
    print("[DB] init & smoke test")
    init_migrate()

    lg_id = get_or_create_company_by_name("LG")
    assert isinstance(lg_id, int) and lg_id > 0

    contact_id = insert_contact({
        "name": "정상화",
        "job_title": "부팀장",
        "company_id": lg_id
    })
    assert contact_id > 0

    consult_id = insert_consultation({
        "source": "ISEC2025",
        "company_id": lg_id,
        "company_name": "LG",
        "comments": "day 1 오전 - ai 추진중, 본주 명함 전달",
        "field": "스마트팩토리",
        "ai_functions": "불량검사",
        "requirements": ["해상도 1080에서 Yolo_v12_seg 20fps"],
        "ai_models": ["Yolo_v12"],
        "next_action": "",
        "contact_id": contact_id,
        "lang": "ko",
        "stt_conf": 0.92
    })
    assert consult_id > 0

    one = get_consultation(consult_id)
    assert one and one["company_name"] == "LG" and one["requirements"] == ["해상도 1080에서 Yolo_v12_seg 20fps"]

    lst = list_consultations(limit=5)
    assert any(r["id"] == consult_id for r in lst)

    export_rows = fetch_consultations_for_export([consult_id])
    assert export_rows and "stt_conf" not in export_rows[0] and "requirements" in export_rows[0]
    contacts_rows = fetch_contacts_for_export([contact_id])
    assert contacts_rows and contacts_rows[0].get("company_name") == "LG"

    print("OK ✔")
