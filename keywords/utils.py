import requests
from urllib.parse import quote  # 키워드를 안전하게 URL 인코딩

# ✅ 공통 User-Agent 헤더
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CapstoneBot/1.0; +http://yourdomain.com/bot)"
}

def get_keyword_info(keyword):
    """Wikipedia API를 사용하여 키워드 정의 및 관련 분야 가져오기"""
    # ✅ 키워드를 URL 인코딩
    encoded_keyword = quote(keyword)

    # ✅ Wikipedia 요약 정보 가져오기
    wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_keyword}"
    # print(f"📡 요청 URL: {wiki_url}")
    
    wiki_response = requests.get(wiki_url, headers=HEADERS)  # ✅ 헤더 추가
    # print(f"📡 응답 코드: {wiki_response.status_code}")

    keyword_summary = "정의를 찾을 수 없습니다."
    
    if wiki_response.status_code == 200:
        wiki_data = wiki_response.json()
        # print(f"📦 응답 내용: {wiki_data}")
        keyword_summary = wiki_data.get("extract", "정의를 찾을 수 없습니다.")
    else:
        print(f"❌ 요약 정보 없음")

    # ✅ Wikipedia Categories API에서 관련 분야 가져오기
    keyword_categories = get_wikipedia_categories(keyword)

    return keyword_summary, keyword_categories

def get_wikipedia_categories(keyword):
    """Wikipedia API를 사용하여 키워드 관련 분야(카테고리) 가져오기"""
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "prop": "categories",
        "titles": keyword
    }

    response = requests.get(url, params=params, headers=HEADERS)  # ✅ 헤더 추가

    if response.status_code == 200:
        data = response.json()
        pages = data.get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            if "categories" in page_data:
                return [category["title"].replace("Category:", "") for category in page_data["categories"]]
    
    return ["관련 분야를 찾을 수 없습니다."]
