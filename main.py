import os
import re
import requests
from collections import Counter

# GitHub Secrets에서 설정값 불러오기 / Fetch tokens from GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_msg(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("텔레그램 토큰 또는 Chat ID가 설정되지 않았습니다. / Telegram token or Chat ID is missing.")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    response = requests.post(url, data=payload)
    print("텔레그램 전송 결과 / Telegram send status:", response.status_code)

def run_trend_analysis():
    # ---------------------------------------------------------
    # [데이터 수집 샘플 / Sample Data Collection]
    # ---------------------------------------------------------
    sample_data = [
        # 네덜란드 현지 타겟 / Netherlands Local Target
        "Beste #sunscreen voor #gevoeligehuid in Nederland! Love #kbeautynl #snailmucin",
        "How to deal with #drogehuid during changing weather #skinbarrier #kbeauty",
        "Amazing #cica serum for #rosacea and redness. #huidverzorging #kbeautynl",
        "Best hydration for #glassskin using #niacinamide and #centella #skincarenl",
        
        # 아랍계 타겟 / Arab Audience Target
        "Best #halalbeauty product for #hyperpigmentation! #منتجات_كورية #kbeautyuae",
        "Dealing with dark spots and #pigmentation using #niacinamide and #retinol #العناية_بالبشرة",
        "Gentle #halalcosmetics for acne-prone skin #skinbarrier #cica",
        "Loving this Korean #sunscreen with SPF50. Perfect for #pigmentation prevention! #kbeauty"
    ]

    hashtags = []
    for caption in sample_data:
        found = re.findall(r"#[\w_]+", caption.lower())
        hashtags.extend(found)

    # 1. 전체 언급량 TOP 5 / Overall TOP 5
    top_overall = Counter(hashtags).most_common(5)

    # 2. 카테고리별 분류 / Categorization
    ingredient_tags = [t for t in hashtags if any(k in t for k in ['cica', 'niacinamide', 'snailmucin', 'centella', 'retinol', 'sunscreen'])]
    concern_tags = [t for t in hashtags if any(k in t for k in ['hyperpigmentation', 'pigmentation', 'rosacea', 'skinbarrier', 'drogehuid'])]

    top_ingredients = Counter(ingredient_tags).most_common(3)
    top_concerns = Counter(concern_tags).most_common(3)

    # ---------------------------------------------------------
    # 3. 한/영 병행 텔레그램 리포트 메시지 작성 / Bilingual Telegram Report
    # ---------------------------------------------------------
    report = "🇳🇱🇸🇦 *[NL/Arab] Daily K-Beauty Trend Alert / 매일 트렌드 알림*\n\n"
    
    report += "🔥 *Top 5 Keywords Overall / 전체 언급 TOP 5*\n"
    for rank, (tag, count) in enumerate(top_overall, 1):
        report += f"{rank}. `{tag}` ({count} mentions/회)\n"
    
    report += "\n🌿 *Top 3 Ingredients / 인기 성분 TOP 3*\n"
    for rank, (tag, count) in enumerate(top_ingredients, 1):
        report += f"• `{tag}` ({count} mentions/회)\n"

    report += "\n🎯 *Top 3 Skin Concerns / 주요 피부 고민 TOP 3*\n"
    for rank, (tag, count) in enumerate(top_concerns, 1):
        report += f"• `{tag}` ({count} mentions/회)\n"

    report += "\n💡 *Market Insights / 시장 인사이트*\n"
    report += "• **Dutch Local (네덜란드 현지):** High demand for sunscreens & barrier care for sensitive/dry skin (`gevoeligehuid`, `drogehuid`).\n"
    report += "  └ 민감성/건성 피부용 자외선 차단제 및 장벽케어 수요 증가\n"
    report += "• **Arab Audience (아랍계 고객):** Steady interest in hyperpigmentation products & halal cosmetics (`halalbeauty`).\n"
    report += "  └ 색소침착 관리 및 할랄 인증 성분 관심 지속\n"

    send_telegram_msg(report)

if __name__ == "__main__":
    run_trend_analysis()
