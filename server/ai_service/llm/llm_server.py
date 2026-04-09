"""ShopPinkki LLM 자연어 상품 위치 검색 서버 (채널 D).

REST GET /query?name=<상품명>
→ {"zone_id": 3, "zone_name": "음료 코너"}
"""

from __future__ import annotations
import logging
import os
import re
import requests
from typing import Optional

from flask import Flask, jsonify, request
from sentence_transformers import SentenceTransformer
import psycopg2
import psycopg2.extras
import numpy as np
import warnings
warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('llm_server')

# ── 환경 변수 ──────────────────────────────────────────────────────────────────
PG_HOST = os.environ.get('PG_HOST', '127.0.0.1')
PG_PORT = int(os.environ.get('PG_PORT', '5432'))
PG_USER = os.environ.get('PG_USER', 'shoppinkki')
PG_PASSWORD = os.environ.get('PG_PASSWORD', 'shoppinkki')
PG_DATABASE = os.environ.get('PG_DATABASE', 'shoppinkki')
HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', '8000'))

# Ollama 설정 (host 모드 적용으로 127.0.0.1 사용)
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434/api/generate')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'qwen2.5:3b')

# ── Sentence-Transformers 모델 로드 ──────────────────────────────
EMBED_MODEL_NAME = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
logger.info("Sentence-Transformers 모델(%s) 로드 중...", EMBED_MODEL_NAME)
try:
    _embed_model = SentenceTransformer(EMBED_MODEL_NAME)
    logger.info("NLP 임베딩 모델 초기화 완료! (384차원)")
except Exception as e:
    logger.error("NLP 임베딩 초기화 에러: %s", e)
    _embed_model = None

def vector_to_string(values: np.ndarray) -> str:
    """PostgreSQL pgvector 형식을 위한 문자열 변환 [v1, v2, ...]"""
    return "[" + ", ".join(f"{v:.8f}" for v in values) + "]"

def get_db_connection():
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        dbname=PG_DATABASE,
        connect_timeout=3
    )

def ask_qwen(user_query: str, search_result: str, zone_type: str = 'product') -> str:
    """Ollama를 통해 Qwen 2.5 3B 모델에게 답변 생성 요청"""
    try:
        if zone_type == 'special':
            # 화장실, 입구, 출구 등 특수 구역은 상품 추천 없이 위치 안내만 수행, '코너' 단어 제외
            prompt = (
                f"당신은 ShopPinkki 매장의 베테랑 AI 점원입니다. 손님이 특수 구역(화장실, 입구 등)을 찾고 있습니다.\n"
                f"매장 정보: {search_result}\n"
                f"손님 질문: {user_query}\n\n"
                f"지침:\n"
                f"1. 상품 추천은 절대 하지 마세요.\n"
                f"2. 아주 친절하게 '해당 위치는 [구역명]에 있습니다. 안내를 시작할까요?' 형식으로 대답하세요. '코너'라는 단어는 절대 쓰지 마세요.\n"
                f"3. 반드시 100% 한국어로만 답변하고, 영어나 다른 언어, 기호는 절대 사용하지 마세요.\n\n"
                f"AI 점원의 답변:"
            )
        else:
            # 일반 상품 구역: 질문 유형에 따라 맞춤형 답변
            prompt = (
                f"당신은 ShopPinkki 매장의 베테랑 AI 점원입니다. 다음 형식에 맞춰 아주 친절하게 손님에게 답변해 주세요.\n\n"
                f"매장 정보: {search_result}\n"
                f"손님 질문: {user_query}\n\n"
                f"답변 가이드라인:\n"
                f"1. 손님이 특정 상품이 어디 있는지 명확하게 물어본 경우(예: '콜라 어딨어?', '휴지 파는 곳은?'), 상품 추천 없이 즉시 '해당 상품은 [구역명] 코너에 있습니다. 안내를 시작할까요?'라고만 깔끔하게 답변하세요.\n"
                f"2. 손님이 '목말라', '배고파'처럼 모호하게 기분이나 상황만 말한 경우에만, 구역에 어울리는 상품을 가볍게 1~2개 추천하고 '[구역명] 코너에 있습니다. 안내를 시작할까요?'라고 답변하세요.\n"
                f"3. 어떤 경우든 답변의 마지막 문장은 반드시 '[구역명] 코너에 있습니다. 안내를 시작할까요?' 형식으로 끝나야 합니다.\n"
                f"4. 반드시 100% 한국어로만 답변하고, 영어나 다른 언어, 특별한 기호(@ 등)는 절대 사용하지 마세요.\n\n"
                f"AI 점원의 답변:"
            )
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 150, "temperature": 0.7}
            },
            timeout=15
        )
        if response.status_code == 200:
            return response.json().get('response', '').strip()
    except Exception as e:
        logger.warning("Qwen 응답 생성 실패: %s", e)
    return f"네, 찾으시는 상품은 {search_result} 지역에 있습니다."

def search_context_in_db(name: str) -> Optional[dict]:
    """pgvector 기반 벡터 검색"""
    if _embed_model is None: return None
    try:
        query_vector = _embed_model.encode(name, normalize_embeddings=True)
        vec_str = vector_to_string(query_vector)
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        query = """
            SELECT type, display_name, zone_id, zone_name, zone_type, distance FROM (
                -- 1. 상품명 검색 (임계값 0.55)
                SELECT 'product' as type, p.product_name as display_name, z.zone_id, z.zone_name, z.zone_type,
                       (te.embedding <=> %s::vector) as distance
                FROM product_text_embedding te
                JOIN product p ON te.product_id = p.product_id
                JOIN zone z ON p.zone_id = z.zone_id
                WHERE (te.embedding <=> %s::vector) < 0.55
                
                UNION ALL
                
                -- 2. 구역 설명 검색 (임계값 0.55)
                SELECT 'zone' as type, z.zone_name as display_name, z.zone_id, z.zone_name, z.zone_type,
                       (ze.embedding <=> %s::vector) as distance
                FROM zone_text_embedding ze
                JOIN zone z ON ze.zone_id = z.zone_id
                WHERE (ze.embedding <=> %s::vector) < 0.55
            ) as combined_search
            ORDER BY distance ASC
            LIMIT 1;
        """
        cursor.execute(query, (vec_str, vec_str, vec_str, vec_str))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return row
    except Exception as e:
        logger.error('벡터 검색 중 에러: %s', e)
    return None

def extract_keywords(user_query: str) -> list[str]:
    """사용자 질문에서 핵심 카테고리 명사를 추출함"""
    try:
        prompt = (
            f"당신은 매장 상품 카테고리 분석기입니다. 다음 질문에서 검색에 필요한 핵심 '카테고리 명사'나 '상품명'을 최대 3개만 뽑으세요.\n"
            f"질문의 어미(-는데, -거 없어? 등)는 무시하고 '음료', '스낵', '화장실', '출구'와 같은 표준 명사 형태로만 출력하세요.\n"
            f"예: '목이 마른데 시원한거 없어?' -> '음료, 물, 주스'\n"
            f"예: '삼겹살 먹고 싶어' -> '삼겹살, 돼지고기, 육류'\n"
            f"예: '이제 집에 갈래' -> '출구, 퇴장'\n"
            f"질문: {user_query}\n"
            f"키워드:"
        )
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 30, "temperature": 0.1}
            },
            timeout=8
        )
        if response.status_code == 200:
            raw = response.json().get('response', '').strip()
            raw = re.sub(r"['\">:\-]|(->)", " ", raw)
            # 불용어 필터링 (검색 품질 저하 방지)
            stop_words = {'없어', '있어', '있나요', '찾아줘', '어디', '어디야', '건가요'}
            keywords = [k.strip() for k in re.split(r'[,\n]', raw) if k.strip() and k.strip() not in stop_words]
            return keywords
    except Exception as e:
        logger.warning("키워드 추출 실패: %s", e)
    return []

app = Flask(__name__)
app.json.ensure_ascii = False

@app.route('/query', methods=['GET'])
def query():
    name = request.args.get('name', '').strip()
    if not name: return jsonify({'error': 'name 필요'}), 400
    
    logger.info('검색 요청: "%s"', name)
    
    # 1. 키워드 추출 + 원본 질문 포함
    extracted_keywords = extract_keywords(name)
    search_candidates = list(dict.fromkeys(extracted_keywords + [name])) # 순서 유지하며 중복 제거
    
    logger.info('검색 후보 키워드: %s', search_candidates)
    
    best_result = None
    min_dist = 1.0
    
    # 2. 각 후보 키워드별 벡터 검색 수행
    for kw in search_candidates:
        res = search_context_in_db(kw)
        if res:
            dist = res['distance']
            zone_id = res['zone_id']
            
            # [특수 구역 방어 로직] 
            # 출구(120), 입구(110), 결제구역(150)은 검색어와 아주 명확히 일치하지 않으면 페널티 부여
            if zone_id in [110, 120, 150]:
                is_explicit = any(word in kw for word in ['출구', '퇴장', '집에', '나갈', '입구', '들어갈', '결제', '계산', '돈', '카운터'])
                if not is_explicit:
                    dist += 0.12 # 페널티 (다른 상품 매칭이 더 우선되도록 함)
            
            logger.info('  - 키워드 [%s] 매칭 후보: %s (Weight-Dist: %.4f, Original: %.4f)', kw, res['display_name'], dist, res['distance'])
            
            if dist < min_dist and dist < 0.55:
                min_dist = dist
                best_result = res
        else:
            logger.info('  - 키워드 [%s] 매칭 실패 (임계값 초과)', kw)
            
    if best_result:
        search_result_text = f"{best_result['display_name']} (구역: {best_result['zone_name']}, 번호: {best_result['zone_id']})"
        answer = ask_qwen(name, search_result_text, best_result.get('zone_type', 'product'))
        return jsonify({
            'zone_id': best_result['zone_id'],
            'zone_name': best_result['zone_name'],
            'display_name': best_result['display_name'],
            'distance': best_result['distance'],
            'answer': answer
        })
    
    return jsonify({'error': 'not_found', 'answer': "죄송합니다. 정보를 찾지 못했습니다."}), 404

if __name__ == '__main__':
    app.run(host=HOST, port=PORT, debug=False)
