import sqlite3

conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()

# 1) 현장 상담(엑셀 1시트 기준)
CREATE TABLE IF NOT EXISTS consultations (
  id               INTEGER PRIMARY KEY AUTOINCREMENT, -- No
  date_time        TEXT NOT NULL,                     -- ISO8601: "YYYY-MM-DD HH:MM"
  source           TEXT,                              -- 전시회/부스명 등
  company_id       INTEGER,                           -- FK → companies.id (NULL 허용)
  company_name     TEXT,                              -- 입력 당시 문자열 보관(변경 이력 방지)
  comments         TEXT,                              -- 현장 코멘트
  field            TEXT,                              -- 산업/도메인
  ai_functions     TEXT,                              -- 예: "불량검사"
  requirements_json TEXT,                             -- ["해상도 1080...", "20fps"] 등
  ai_models_json    TEXT,                             -- ["Yolo_v12", ...]
  next_action      TEXT,                              -- 다음 액션(자유기입)
  contact_id       INTEGER,                           -- FK → contacts.id (NULL 허용)
  stt_conf         REAL,                              -- STT 평균 신뢰도(옵션)
  transcript       TEXT,                              -- 원문(옵션)
  lang             TEXT,                              -- "ko"|"en" 등(옵션)
  created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at       TEXT
);

# 2) 담당자(명함/사후)
CREATE TABLE IF NOT EXISTS contacts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,
  job_title   TEXT,
  phone       TEXT,
  email       TEXT,
  company_id  INTEGER,            -- FK → companies.id (NULL 허용)
  created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

# 3) 회사정보(비활성화: 테이블만 생성)
CREATE TABLE IF NOT EXISTS companies (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  name                TEXT NOT NULL UNIQUE,
  status              TEXT,               -- 리서치/진행상태
  description         TEXT,
  priority            INTEGER,            -- 1(High)…5(Low) 등
  industry            TEXT,
  company_size        TEXT,
  sales_volume_usd_m  REAL,
  website             TEXT,
  country             TEXT,
  state_city          TEXT,
  created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

# 인덱스
CREATE INDEX IF NOT EXISTS idx_consultations_date ON consultations(date_time);
CREATE INDEX IF NOT EXISTS idx_consultations_company ON consultations(company_id);
CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_id);
