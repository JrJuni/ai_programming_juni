import os
import sys

def get_project_root():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        # 이 파일이 local_llm_tools_prjects/src 폴더 안에 있으므로, 부모의 부모 폴더가 프로젝트 루트입니다.
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = get_project_root()

# --- 데이터베이스 이름 설정 (Single Source of Truth) ---
# 이 부분의 값만 바꾸면 프로젝트 전체의 DB 파일이 변경됩니다.
DB_FILENAME = 'mobilint_crm.db' 
DB_PATH = os.path.join(PROJECT_ROOT, 'data', DB_FILENAME)

# --- 모델 파일 이름 설정 (Single Source of Truth) ---
# MODEL_FILENAME = "Midm-2.0-Mini-Instruct-Q8_0.gguf"
MODEL_FILENAME = "Midm-2.0-Mini-Instruct-Q4_K_M.gguf"
MODEL_PATH = os.path.join(PROJECT_ROOT, 'models', MODEL_FILENAME)