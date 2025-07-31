from llama_cpp import Llama
import json
import sqlite3
import os
from config import MODEL_PATH, PROJECT_ROOT

# 메뉴 데이터베이스 경로
MENU_DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'bunsik_menu.db')

# --- LLM 모델 로딩 ---
if os.path.exists(MODEL_PATH):
    print("LLM 모델을 로딩합니다...")
    llm = Llama(model_path=MODEL_PATH, n_ctx=2048, verbose=False)
    print("모델 로딩 완료.")
else:
    llm = None
    print(f"경고: 모델 파일을 찾을 수 없습니다. 경로: {MODEL_PATH}")

def _get_llm_json_response(prompt: str) -> dict:
    """
    LLM에 프롬프트를 보내고, 응답에서 JSON 객체만 안전하게 추출하여 반환하는 헬퍼 함수.
    """
    if llm is None:
        print("오류: LLM 모델이 로드되지 않았습니다.")
        return {}

    output = llm(
        prompt,
        max_tokens=512,
        stop=["```"],
        temperature=0.3,  # 메뉴 추천을 위해 약간의 창의성 허용
        echo=False
    )
    
    response_text = output["choices"][0]["text"]
    
    try:
        # 응답 텍스트에서 첫 '{'와 마지막 '}'를 찾아 그 사이의 내용만 추출
        start_index = response_text.find('{')
        end_index = response_text.rfind('}')
        
        if start_index != -1 and end_index != -1 and start_index < end_index:
            json_string = response_text[start_index : end_index + 1]
            return json.loads(json_string)
        else:
            raise json.JSONDecodeError("No valid JSON object found", response_text, 0)

    except json.JSONDecodeError as e:
        print(f"오류: LLM의 답변을 JSON으로 변환하는 데 실패했습니다. - {e}")
        print(f"--- LLM 원본 응답 ---\n{response_text}\n--------------------")
        return {}

# 메뉴 데이터 캐시
_menu_cache = None

def get_all_menu_items(force_reload=False):
    """데이터베이스에서 모든 메뉴 아이템 조회 (지연 로딩 + 캐싱)"""
    global _menu_cache
    
    # 캐시된 데이터가 있고 강제 리로드가 아니면 캐시 반환
    if _menu_cache is not None and not force_reload:
        return _menu_cache
    
    if not os.path.exists(MENU_DB_PATH):
        print("메뉴 데이터베이스가 존재하지 않습니다. menu_schema.py를 먼저 실행해주세요.")
        return []
    
    conn = sqlite3.connect(MENU_DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT m.id, m.name, c.name as category, m.price, m.description, 
               m.ingredients, m.taste_profile, m.spicy_level,
               GROUP_CONCAT(t.tag, ', ') as tags
        FROM menu_items m
        LEFT JOIN categories c ON m.category_id = c.id
        LEFT JOIN menu_tags t ON m.id = t.menu_id
        WHERE m.is_available = 1
        GROUP BY m.id
        ORDER BY m.category_id, m.name
    ''')
    
    items = cursor.fetchall()
    conn.close()
    
    # 캐시에 저장
    _menu_cache = items
    return items

def recommend_menu_with_llm(user_preference: str, include_details=True) -> dict:
    """
    사용자 선호도를 기반으로 메뉴를 추천하는 AI 함수
    
    Args:
        user_preference: 사용자 선호도 텍스트
        include_details: 상세 정보 포함 여부 (False시 이름, 카테고리, 가격만)
    """
    # 필요시에만 메뉴 정보 가져오기
    menu_items = get_all_menu_items()
    
    if not menu_items:
        return {"error": "메뉴 데이터를 불러올 수 없습니다."}
    
    # 메뉴 정보를 문자열로 변환 (간소화 옵션)
    menu_info = ""
    for item in menu_items:
        menu_info += f"- {item[1]} ({item[2]}): {item[3]}원\n"
        if include_details:
            menu_info += f"  설명: {item[4]}\n"
            menu_info += f"  재료: {item[5]}\n"
            menu_info += f"  맛: {item[6]}, 매운맛 단계: {item[7]}/5\n"
            if item[8]:
                menu_info += f"  태그: {item[8]}\n"
        menu_info += "\n"
    
    prompt = f"""<|system|>
당신은 분식집 키오스크의 메뉴 추천 전문가입니다. 
고객의 선호도를 분석하여 가장 적합한 메뉴 3개를 추천해주세요.

다음 분식집 메뉴 목록을 참고하세요:
{menu_info}

추천 기준:
1. 고객의 맛 선호도 (매운맛, 단맛, 담백함 등)
2. 요리 스타일 (국물, 볶음, 튀김 등)
3. 가격대 고려
4. 재료나 특별한 요구사항

응답은 반드시 다음 JSON 형식으로 해주세요:
{{
    "recommendations": [
        {{
            "menu_name": "메뉴명",
            "reason": "추천 이유 (한 문장으로 간단히)",
            "price": 가격,
            "category": "카테고리명"
        }},
        {{
            "menu_name": "메뉴명",
            "reason": "추천 이유",
            "price": 가격,
            "category": "카테고리명"
        }},
        {{
            "menu_name": "메뉴명", 
            "reason": "추천 이유",
            "price": 가격,
            "category": "카테고리명"
        }}
    ],
    "comment": "전체적인 추천 코멘트 (한 문장)"
}}

<|user|>
고객 선호도: {user_preference}

<|assistant|>
```json
"""
    return _get_llm_json_response(prompt)

def analyze_preference_with_llm(user_input: str, detailed=False) -> dict:
    """
    사용자 입력을 분석하여 선호도를 파악하는 함수
    
    Args:
        user_input: 사용자 입력 텍스트
        detailed: 상세 분석 여부 (False시 맛과 매운맛 단계만)
    """
    if detailed:
        prompt = f"""<|system|>
당신은 고객의 음식 선호도를 분석하는 전문가입니다.
고객의 입력을 분석하여 다음 정보를 JSON 형식으로 추출해주세요:

{{
    "taste_preference": "맛 선호도 (매운맛/단맛/담백함/고소함/새콤함 등)",
    "spicy_level": "매운맛 선호 단계 (0-5, 0이 안매움)",
    "food_type": "선호 음식 유형 (국물요리/볶음요리/튀김/면요리/밥요리 등)",
    "price_range": "가격대 선호 (저렴함/보통/비싸도됨)",
    "special_request": "특별 요청사항 (치즈추가/야채많이/든든함 등)",
    "mood": "현재 기분이나 상황 (출근전급함/든든하게/가볍게 등)"
}}

<|user|>
고객 입력: {user_input}

<|assistant|>
```json
"""
    else:
        # 간단한 분석만 수행
        prompt = f"""<|system|>
고객의 음식 선호도를 간단히 분석해주세요.

{{
    "taste_preference": "맛 선호도",
    "spicy_level": "매운맛 단계 (0-5)"
}}

<|user|>
고객 입력: {user_input}

<|assistant|>
```json
"""
    return _get_llm_json_response(prompt)

# 간단한 인터페이스 함수들
def quick_recommend(user_input: str) -> dict:
    """빠른 메뉴 추천 (최소 계산량)"""
    return recommend_menu_with_llm(user_input, include_details=False)

def simple_analysis(user_input: str) -> dict:
    """간단한 선호도 분석"""
    return analyze_preference_with_llm(user_input, detailed=False)

# --- 테스트 코드 ---
def run_specific_test(test_mode="basic"):
    """
    선택적 테스트 실행 함수
    
    Args:
        test_mode: "basic" (기본 추천만), "analysis" (선호도 분석만), "full" (전체)
    """
    # 메뉴 데이터베이스 초기화 확인
    from menu_schema import create_menu_database, insert_sample_menu_data
    
    if not os.path.exists(MENU_DB_PATH):
        print("메뉴 데이터베이스를 초기화합니다...")
        create_menu_database()
        insert_sample_menu_data()
    
    print("="*50)
    print(f"분식집 메뉴 AI 테스트 ({test_mode} 모드)")
    print("="*50)
    
    # 테스트 케이스 1개만 (빠른 테스트)
    test_case = "매운 음식이 좋아요. 특히 치즈가 들어간 음식을 좋아합니다."
    
    print(f"고객 입력: {test_case}")
    
    if test_mode in ["analysis", "full"]:
        print("\n[선호도 분석]:")
        preference_analysis = analyze_preference_with_llm(test_case, detailed=(test_mode=="full"))
        print(preference_analysis)
    
    if test_mode in ["basic", "full"]:
        print("\n[메뉴 추천]:")
        recommendations = recommend_menu_with_llm(test_case, include_details=(test_mode=="full"))
        
        if "recommendations" in recommendations:
            print(f"코멘트: {recommendations.get('comment', 'N/A')}")
            print("\n추천 메뉴:")
            for j, rec in enumerate(recommendations["recommendations"], 1):
                print(f"  {j}. {rec['menu_name']} ({rec['category']}) - {rec['price']}원")
                print(f"     이유: {rec['reason']}")
        else:
            print("추천 결과를 불러올 수 없습니다.")
            print(recommendations)
    
    print("\n테스트 완료!")
if __name__ == '__main__':
    import sys
    
    # 명령어 인수로 테스트 모드 선택
    test_mode = "basic"  # 기본은 빠른 추천만
    if len(sys.argv) > 1:
        test_mode = sys.argv[1]
    
    run_specific_test(test_mode)