import sqlite3
import os
from config import PROJECT_ROOT

# 분식집 메뉴 데이터베이스 파일 경로
MENU_DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'bunsik_menu.db')

def create_menu_database():
    """분식집 메뉴 데이터베이스 및 테이블 생성"""
    
    # data 디렉토리가 없으면 생성
    os.makedirs(os.path.dirname(MENU_DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(MENU_DB_PATH)
    cursor = conn.cursor()
    
    # 메뉴 카테고리 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT
        )
    ''')
    
    # 메뉴 아이템 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category_id INTEGER,
            price INTEGER NOT NULL,
            description TEXT,
            ingredients TEXT,
            taste_profile TEXT,
            spicy_level INTEGER DEFAULT 0,
            is_available BOOLEAN DEFAULT 1,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    ''')
    
    # 메뉴 태그 테이블 (검색용)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS menu_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_id INTEGER,
            tag TEXT NOT NULL,
            FOREIGN KEY (menu_id) REFERENCES menu_items (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"메뉴 데이터베이스가 생성되었습니다: {MENU_DB_PATH}")

def insert_sample_menu_data():
    """샘플 분식집 메뉴 데이터 삽입"""
    conn = sqlite3.connect(MENU_DB_PATH)
    cursor = conn.cursor()
    
    try:
        # 카테고리 데이터
        categories = [
            ("떡볶이", "매콤달콤한 떡볶이류"),
            ("김밥", "간편하고 든든한 김밥류"), 
            ("튀김", "바삭한 튀김류"),
            ("국물요리", "따뜻한 국물요리"),
            ("면요리", "쫄깃한 면요리"),
            ("밥요리", "든든한 밥요리")
        ]
        
        cursor.executemany("INSERT OR IGNORE INTO categories (name, description) VALUES (?, ?)", categories)
        
        # 메뉴 아이템 데이터
        menu_items = [
            # 떡볶이류
            ("떡볶이", 1, 3000, "매콤달콤한 기본 떡볶이", "떡, 고추장, 설탕, 양파", "매콤달콤", 2),
            ("치즈떡볶이", 1, 4000, "치즈가 들어간 부드러운 떡볶이", "떡, 고추장, 치즈, 설탕", "매콤크리미", 2),
            ("로제떡볶이", 1, 4500, "크림이 들어간 부드러운 떡볶이", "떡, 고추장, 크림, 우유", "부드러운매콤", 1),
            ("곱창떡볶이", 1, 5000, "곱창이 들어간 진한 떡볶이", "떡, 고추장, 곱창, 양파", "매콤진한", 3),
            
            # 김밥류
            ("참치김밥", 2, 3500, "참치와 야채가 들어간 김밥", "김, 밥, 참치, 단무지, 계란", "고소담백", 0),
            ("소고기김밥", 2, 4000, "소고기가 들어간 든든한 김밥", "김, 밥, 소고기, 단무지, 계란", "고소진한", 0),
            ("김치김밥", 2, 3000, "김치가 들어간 매콤한 김밥", "김, 밥, 김치, 단무지, 계란", "매콤새콤", 1),
            ("누드김밥", 2, 4500, "김 없는 특별한 김밥", "밥, 소고기, 계란, 시금치, 단무지", "고소담백", 0),
            
            # 튀김류
            ("오징어튀김", 3, 2000, "바삭한 오징어튀김", "오징어, 튀김가루", "바삭고소", 0),
            ("새우튀김", 3, 2500, "통새우가 들어간 튀김", "새우, 튀김가루", "바삭달콤", 0),
            ("야채튀김", 3, 1500, "각종 야채 튀김", "야채, 튀김가루", "바삭담백", 0),
            ("김말이튀김", 3, 2000, "김말이 튀김", "김, 당면, 야채, 튀김가루", "바삭쫄깃", 0),
            
            # 국물요리
            ("어묵국물", 4, 2000, "따뜻한 어묵국물", "어묵, 무, 파", "시원담백", 0),
            ("라면", 4, 3000, "매콤한 라면", "라면, 계란, 파", "매콤진한", 2),
            ("치즈라면", 4, 3500, "치즈가 들어간 라면", "라면, 치즈, 계란", "매콤크리미", 2),
            ("떡라면", 4, 3500, "떡이 들어간 든든한 라면", "라면, 떡, 계란", "매콤쫄깃", 2),
            
            # 면요리
            ("냉면", 5, 4500, "시원한 냉면", "냉면, 육수, 계란, 오이", "시원새콤", 0),
            ("비빔냉면", 5, 4500, "매콤한 비빔냉면", "냉면, 고추장, 계란, 오이", "매콤새콤", 2),
            ("잔치국수", 5, 3000, "따뜻한 잔치국수", "소면, 멸치육수, 파", "시원담백", 0),
            ("비빔국수", 5, 3500, "매콤한 비빔국수", "소면, 고추장, 야채", "매콤새콤", 2),
            
            # 밥요리
            ("볶음밥", 6, 4000, "고소한 볶음밥", "밥, 계란, 야채, 햄", "고소담백", 0),
            ("김치볶음밥", 6, 4500, "매콤한 김치볶음밥", "밥, 김치, 계란, 햄", "매콤고소", 1),
            ("오므라이스", 6, 5000, "달걀로 감싼 볶음밥", "밥, 계란, 케찹, 야채", "달콤고소", 0),
            ("제육덮밥", 6, 5500, "매콤한 제육덮밥", "밥, 제육, 양파, 고추장", "매콤진한", 2)
        ]
        
        cursor.executemany('''
            INSERT OR IGNORE INTO menu_items 
            (name, category_id, price, description, ingredients, taste_profile, spicy_level) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', menu_items)
        
        # 태그 데이터 (검색용)
        menu_tags_data = [
            # 떡볶이 관련 태그
            (1, "매운맛"), (1, "달콤"), (1, "쫄깃"), (1, "분식"),
            (2, "치즈"), (2, "부드러운"), (2, "크리미"),
            (3, "로제"), (3, "부드러운"), (3, "크림"),
            (4, "곱창"), (4, "진한맛"), (4, "얼큰"),
            
            # 김밥 관련 태그
            (5, "참치"), (5, "든든"), (5, "담백"),
            (6, "소고기"), (6, "든든"), (6, "고소"),
            (7, "김치"), (7, "매콤"), (7, "새콤"),
            (8, "누드"), (8, "특별한"), (8, "색다른"),
            
            # 튀김 관련 태그
            (9, "바삭"), (9, "오징어"), (9, "고소"),
            (10, "새우"), (10, "바삭"), (10, "달콤"),
            (11, "야채"), (11, "건강"), (11, "담백"),
            (12, "김말이"), (12, "쫄깃"), (12, "바삭"),
            
            # 국물요리 관련 태그
            (13, "어묵"), (13, "따뜻"), (13, "시원"),
            (14, "라면"), (14, "매운맛"), (14, "진한맛"),
            (15, "치즈라면"), (15, "크리미"), (15, "부드러운"),
            (16, "떡라면"), (16, "든든"), (16, "쫄깃"),
            
            # 면요리 관련 태그
            (17, "냉면"), (17, "시원"), (17, "새콤"),
            (18, "비빔냉면"), (18, "매콤"), (18, "새콤"),
            (19, "잔치국수"), (19, "따뜻"), (19, "담백"),
            (20, "비빔국수"), (20, "매콤"), (20, "새콤"),
            
            # 밥요리 관련 태그
            (21, "볶음밥"), (21, "고소"), (21, "든든"),
            (22, "김치볶음밥"), (22, "매콤"), (22, "고소"),
            (23, "오므라이스"), (23, "달콤"), (23, "부드러운"),
            (24, "제육덮밥"), (24, "매콤"), (24, "진한맛")
        ]
        
        cursor.executemany("INSERT OR IGNORE INTO menu_tags (menu_id, tag) VALUES (?, ?)", menu_tags_data)
        
        conn.commit()
        print("샘플 메뉴 데이터가 삽입되었습니다.")
        
    except Exception as e:
        conn.rollback()
        print(f"데이터 삽입 중 오류 발생: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    print("분식집 메뉴 데이터베이스를 초기화합니다...")
    create_menu_database()
    insert_sample_menu_data()
    print("초기화 완료!")