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
            # 화장실, 입구, 출구 등 특수 구역은 경로 설명 없이 매우 간결하게 안내
            prompt = (
                f"당신은 ShopPinkki 매장의 안내원입니다.\n"
                f"매장 정보: {search_result}\n"
                f"손님 질문: {user_query}\n\n"
                f"지침:\n"
                f"1. 가는 방법이나 경로(직진, 좌회전 등)를 절대 설명하지 마세요.\n"
                f"2. 불필요한 사족 없이 '해당 위치는 [위치명]입니다. 안내를 시작할까요?'라고만 짧고 친절하게 대답하세요.\n"
                f"3. 반드시 100% 한국어로만 답변하고, 숫자나 기호는 사용하지 마세요.\n\n"
                f"AI 점원의 답변:"
            )
        else:
            # 일반 상품 구역: 질문 유형에 따라 맞춤형 답변
            prompt = (
                f"당신은 ShopPinkki 매장의 친절한 안내원입니다. 제공된 매장 정보만을 근거로 대답하세요.\n"
                f"매장 정보: {search_result}\n"
                f"손님 질문: {user_query}\n\n"
                f"지침:\n"
                f"답변은 반드시 아래 제시된 네 가지 형식 중 하나만 정확하게 선택하세요. 절대 다른 사족을 붙이거나 지어내지 마세요.\n\n"
                f"유형 1. 명확한 상품/구역 검색 (예: 콜라 어딨어?, 고기 찾아):\n    '해당 상품은 [구역명] 코너에 있습니다. 안내를 시작할까요?'\n"
                f"유형 2. 목마름 관련 모호한 질문 (예: 목말라, 마실거):\n    '목마르시죠? [구역명] 코너로 안내해 드릴게요. 안내를 시작할까요?'\n"
                f"유형 3. 배고픔 관련 모호한 질문 (예: 배고파, 너무 굶었어, 식사):\n    '출출하시죠? [구역명] 코너로 안내해 드릴게요. 안내를 시작할까요?'\n"
                f"유형 4. 간단한 간식 관련 모호한 질문 (예: 간단하게 먹을거, 과자, 빵):\n    '간단한 간식을 찾으시나요? [구역명] 코너로 안내해 드릴게요. 안내를 시작할까요?'\n\n"
                f"주의사항:\n"
                f"- 제공된 매장 정보의 위치(구역명) 외에 가상의 아이템(주방, 라떼, 땅콩 등)이나 경로(좌회전 등)는 절대 언급하지 마세요.\n"
                f"- 구역 번호나 불필요한 기호(', \")는 사용하지 마세요.\n\n"
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
        
        # 동의어 처리 (카운터 등 -> 결제 구역)
        synonyms = {'카운터': '결제 구역', '계산대': '결제 구역', '캐셔': '결제 구역'}
        exact_match_name = synonyms.get(name, name)
        
        # 0. 텍스트 완전 일치 검색 (상품명 또는 구역명 우선)
        # 일치할 경우 거리(distance)를 최소값(0.0)으로 해서 즉시 반환
        exact_query = """
            SELECT 'product' as type, p.product_name as display_name, z.zone_id, z.zone_name, z.zone_type, 0.0 as distance
            FROM product p
            JOIN zone z ON p.zone_id = z.zone_id
            WHERE p.product_name = %s
            UNION ALL
            SELECT 'zone' as type, z.zone_name as display_name, z.zone_id, z.zone_name, z.zone_type, 0.01 as distance
            FROM zone z
            WHERE z.zone_name = %s
            LIMIT 1;
        """
        cursor.execute(exact_query, (exact_match_name, exact_match_name))
        row = cursor.fetchone()
        if row:
            logger.info('텍스트 완전 일치 검색 성공: "%s" (원본: "%s") -> %s', exact_match_name, name, row['display_name'])
            cursor.close()
            conn.close()
            return row

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
            f"절대 검색 단어를 임의로 바꾸지 마세요. (예: '입구'를 '출구'로, '화장실'을 '입구'로 바꾸면 안 됨)\n"
            f"매장의 유효한 구역: 화장실, 입구, 출구, 결제 구역, 가전제품, 과자, 해산물, 육류, 채소, 음료, 베이커리, 음식\n"
            f"질문의 어미(-는데, -거 없어? 등)는 무시하고 위 유효한 구역이나 표준 명사 형태로만 출력하세요.\n"
            f"예: '목이 마른데 시원한거 없어?' -> '음료, 주스'\n"
            f"예: '간단하게 먹을만한 거 없어?' -> '베이커리, 과자'\n"
            f"예: '너무 배고픈데 어디로 가야돼' -> '음식, 밥'\n"
            f"예: '카운터 어디야?', '결제할래' -> '결제 구역'\n"
            f"예: '삼겹살 먹고 싶어' -> '육류, 삼겹살, 돼지고기'\n"
            f"예: '입구 어디인가요?' -> '입구'\n"
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
    
    # 1. 원본 질문을 최우선 순위로, 추출 키워드를 부가 순위로 설정 (순서가 매우 중요)
    extracted_keywords = extract_keywords(name)
    # 원본 name을 리스트의 맨 처음에 배치하여 LLM 변조 방지 (입구 -> 출구 방어)
    search_candidates = list(dict.fromkeys([name] + extracted_keywords))
    
    logger.info('검색 후보 키워드: %s', search_candidates)
    
    best_result = None
    min_dist = 1.0
    
    # 2. 각 후보 키워드별 벡터 검색 수행
    for idx, kw in enumerate(search_candidates):
        res = search_context_in_db(kw)
        if res:
            dist = res['distance']
            zone_id = res['zone_id']
            
            # [특수 구역 방어 로직 - 개선] 
            # 입구(110), 출구(120), 화장실(100), 결제구역(150)은 각 전용 키워드와 명확히 일치하지 않으면 페널티 부여
            if zone_id in [100, 110, 120, 150]:
                keywords_map = {
                    110: ['입구', '들어', '진입', '마트 시작'],
                    120: ['출구', '퇴장', '집에', '나갈', '쇼핑 끝', '나가는 곳'],
                    100: ['화장실', '손 씻', 'restroom', 'toilet', '급해'],
                    150: ['결제', '계산', '돈', '카운터']
                }
                # 현재 검색어(kw)에 해당 구역 전용 키워드가 포함되어 있는지 확인
                is_explicit = any(word in kw for word in keywords_map.get(zone_id, []))
                if not is_explicit:
                    dist += 0.3 # 페널티 더욱 강화 (0.25 -> 0.3)
            
            logger.info('  - 후보 [%d] 키워드 [%s] 매칭 후보: %s (Weight-Dist: %.4f, Original: %.4f)', idx, kw, res['display_name'], dist, res['distance'])
            
            if dist < min_dist and dist < 0.55:
                min_dist = dist
                best_result = res
                
                # [조기 종료 로직]
                # 첫 번째 후보(원본 질문)가 특수 구역에 매우 명확히(0.3점 이하) 매칭되었다면
                # LLM이 지어낸 나머지 키워드들은 검색할 필요 없이 즉시 종료
                if idx == 0 and zone_id in [100, 110, 120, 150] and dist < 0.3:
                    logger.info('  - 특수 구역 고정 매칭 발견 (조기 종료): %s', res['display_name'])
                    break
        else:
            logger.info('  - 후보 [%d] 키워드 [%s] 매칭 실패 (임계값 초과)', idx, kw)
            
    if best_result:
        # LLM에게는 번호 정보를 주지 않음 (실수 방지)
        search_result_text = f"{best_result['display_name']} (위치: {best_result['zone_name']})"
        answer = ask_qwen(name, search_result_text, best_result.get('zone_type', 'product'))
        
        # 마지막 안전장치: 답변에서 모든 숫자(ID 등) 제거 (robustness 강화)
        if answer:
            answer = re.sub(r'\d+', '', str(answer)).replace('  ', ' ').strip()
        else:
            answer = "찾으시는 정보를 매장에서 안내해 드릴게요."
        
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
