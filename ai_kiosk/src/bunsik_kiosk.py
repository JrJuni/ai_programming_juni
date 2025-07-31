import os
import time
from menu_aiwizard import recommend_menu_with_llm, analyze_preference_with_llm, get_all_menu_items
from menu_schema import create_menu_database, insert_sample_menu_data, MENU_DB_PATH

def clear_screen():
    """화면 클리어 (Windows/Linux 호환)"""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    """키오스크 헤더 출력"""
    print("=" * 60)
    print("🍜 맛있는 분식집 키오스크 🍜")
    print("AI가 추천하는 맞춤 메뉴!")
    print("=" * 60)

def print_menu_categories():
    """메뉴 카테고리 출력"""
    menu_items = get_all_menu_items()
    if not menu_items:
        print("⚠️ 메뉴 데이터를 불러올 수 없습니다.")
        return
    
    categories = {}
    for item in menu_items:
        category = item[2]  # category name
        if category not in categories:
            categories[category] = []
        categories[category].append({
            'name': item[1],
            'price': item[3],
            'description': item[4]
        })
    
    print("\n📋 전체 메뉴판")
    print("-" * 40)
    for category, items in categories.items():
        print(f"\n🍽️ {category}")
        for item in items:
            print(f"   • {item['name']} - {item['price']:,}원")
            print(f"     {item['description']}")

def get_user_preference():
    """사용자 선호도 입력 받기"""
    print("\n💭 어떤 음식을 드시고 싶으신가요?")
    print("예시:")
    print("- '매운 음식이 좋아요'")
    print("- '가볍게 먹고 싶어요'") 
    print("- '든든하게 배불리 먹고 싶습니다'")
    print("- '시원한 음식이 먹고 싶어요'")
    print("- '바삭한 튀김이 좋아요'")
    print("-" * 40)
    
    while True:
        user_input = input("🎯 원하시는 음식의 특징을 말씀해주세요: ").strip()
        if user_input:
            return user_input
        print("⚠️ 선호하는 음식의 특징을 입력해주세요.")

def display_recommendations(recommendations):
    """추천 결과 출력"""
    if not recommendations or "recommendations" not in recommendations:
        print("❌ 추천 결과를 가져올 수 없습니다.")
        return False
    
    print("\n🤖 AI 추천 결과")
    print("=" * 50)
    
    if "comment" in recommendations:
        print(f"💬 {recommendations['comment']}")
    
    print(f"\n🏷️ 총 가격: {recommendations.get('total_price', 'N/A')}원")
    print("\n📝 추천 메뉴 TOP 3:")
    
    for i, rec in enumerate(recommendations["recommendations"], 1):
        print(f"\n{i}. 🍽️ {rec['menu_name']} ({rec['category']})")
        print(f"   💰 가격: {rec['price']:,}원")
        print(f"   📋 추천 이유: {rec['reason']}")
    
    return True

def show_preference_analysis(analysis):
    """선호도 분석 결과 출력"""
    if not analysis:
        return
    
    print("\n🔍 고객님의 선호도 분석")
    print("-" * 30)
    
    if "taste_preference" in analysis:
        print(f"맛 선호도: {analysis['taste_preference']}")
    if "spicy_level" in analysis:
        print(f"매운맛 단계: {analysis['spicy_level']}/5")
    if "food_type" in analysis:
        print(f"음식 유형: {analysis['food_type']}")
    if "price_range" in analysis:
        print(f"가격대: {analysis['price_range']}")
    if "special_request" in analysis:
        print(f"특별 요청: {analysis['special_request']}")
    if "mood" in analysis:
        print(f"현재 상황: {analysis['mood']}")

def main_menu():
    """메인 메뉴"""
    while True:
        clear_screen()
        print_header()
        
        print("\n📱 메뉴를 선택해주세요:")
        print("1. 🤖 AI 맞춤 메뉴 추천")
        print("2. 📋 전체 메뉴 보기")
        print("3. 🚪 종료")
        
        choice = input("\n선택 (1-3): ").strip()
        
        if choice == "1":
            ai_recommendation_flow()
        elif choice == "2":
            clear_screen()
            print_header()
            print_menu_categories()
            input("\n계속하려면 Enter를 누르세요...")
        elif choice == "3":
            print("\n👋 이용해 주셔서 감사합니다!")
            break
        else:
            print("⚠️ 올바른 번호를 입력해주세요.")
            time.sleep(1)

def ai_recommendation_flow():
    """AI 추천 플로우"""
    clear_screen()
    print_header()
    print_menu_categories()
    
    # 사용자 선호도 입력
    user_preference = get_user_preference()
    
    print("\n🤖 AI가 분석 중입니다...")
    print("잠시만 기다려주세요... ⏳")
    
    # 선호도 분석
    analysis = analyze_preference_with_llm(user_preference)
    
    # 메뉴 추천
    recommendations = recommend_menu_with_llm(user_preference)
    
    clear_screen()
    print_header()
    
    # 결과 출력
    show_preference_analysis(analysis)
    
    if display_recommendations(recommendations):
        print("\n" + "=" * 50)
        print("🛒 주문하시겠습니까?")
        print("1. 네, 주문할게요")
        print("2. 다시 추천받기")
        print("3. 메인 메뉴로")
        
        while True:
            choice = input("\n선택 (1-3): ").strip()
            if choice == "1":
                process_order(recommendations["recommendations"])
                break
            elif choice == "2":
                ai_recommendation_flow()
                break
            elif choice == "3":
                break
            else:
                print("⚠️ 올바른 번호를 입력해주세요.")
    else:
        input("\n계속하려면 Enter를 누르세요...")

def process_order(recommended_items):
    """주문 처리"""
    print("\n🛍️ 주문 처리")
    print("-" * 20)
    
    selected_items = []
    total_price = 0
    
    for i, item in enumerate(recommended_items, 1):
        while True:
            choice = input(f"{i}. {item['menu_name']} ({item['price']:,}원) - 주문하시겠습니까? (y/n): ").strip().lower()
            if choice in ['y', 'yes', '네', 'ㅇ']:
                selected_items.append(item)
                total_price += item['price']
                print(f"   ✅ {item['menu_name']} 추가되었습니다.")
                break
            elif choice in ['n', 'no', '아니오', 'ㄴ']:
                print(f"   ❌ {item['menu_name']} 제외되었습니다.")
                break
            else:
                print("   ⚠️ y(네) 또는 n(아니오)로 답해주세요.")
    
    if selected_items:
        print(f"\n📝 최종 주문 내역:")
        print("-" * 30)
        for item in selected_items:
            print(f"• {item['menu_name']} - {item['price']:,}원")
        print("-" * 30)
        print(f"💰 총 금액: {total_price:,}원")
        print("\n🎉 주문이 완료되었습니다!")
        print("조리 시간: 약 10-15분")
        print("맛있게 드세요! 🍽️")
    else:
        print("\n❌ 주문된 메뉴가 없습니다.")
    
    input("\n메인 메뉴로 돌아가려면 Enter를 누르세요...")

def initialize_system():
    """시스템 초기화"""
    print("시스템을 초기화합니다...")
    
    # 메뉴 데이터베이스 확인 및 생성
    if not os.path.exists(MENU_DB_PATH):
        print("메뉴 데이터베이스를 생성합니다...")
        create_menu_database()
        insert_sample_menu_data()
        print("✅ 메뉴 데이터베이스 생성 완료!")
    else:
        print("✅ 메뉴 데이터베이스 확인 완료!")
    
    # 메뉴 로딩 테스트
    menu_items = get_all_menu_items()
    if menu_items:
        print(f"✅ 총 {len(menu_items)}개의 메뉴를 로드했습니다!")
    else:
        print("⚠️ 메뉴 데이터를 불러오지 못했습니다.")
    
    print("초기화 완료!\n")
    time.sleep(2)

if __name__ == '__main__':
    try:
        initialize_system()
        main_menu()
    except KeyboardInterrupt:
        print("\n\n👋 키오스크를 종료합니다. 감사합니다!")
    except Exception as e:
        print(f"\n❌ 오류가 발생했습니다: {e}")
        print("시스템 관리자에게 문의해주세요.")