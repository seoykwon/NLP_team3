# K-IFRS_통합_처리 — 파싱/청킹 코드 요약

다음은 노트북 내에서 파싱/청킹과 직접 관련된 코드 셀을 선별하여, 핵심 의도와 파라미터를 한국어 주석으로 보강한 것입니다.

---

## 셀 1

```python
# 텍스트 후처리 함수
# 함수: postprocess_text — 파싱/청킹 관련 서브루틴
def postprocess_text(text: str, *, has_next_para: bool) -> str:
    """
    규칙:
    1) (중복 줄 삭제) 줄바꿈 제거 전에:
       - [규칙 A] '내용.' + 줄바꿈 + '내용' + (다음 문단번호) 형태면 '두 번째 내용' 삭제
       - [규칙 B] '(숫자) 내용' + 줄바꿈 + '내용' + (다음 문단번호) 형태면 '두 번째 내용' 유지
    2) 본문 안의 '- 숫자 -' 패턴 제거 (헤더/푸터 제거)
    3) 줄바꿈 문자 제거 시 앞뒤를 붙여서 한 줄로 만들기
    """
    # 0) 라인 단위 정리
# 텍스트 분리(스플리팅) 단계: 문단/문장/토큰 기준으로 나눔
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # 1) 끝부분 중복 줄 삭제 (다음 문단번호가 실제로 존재할 때만)
    if has_next_para and len(lines) >= 2:
        a = lines[-2]  # 줄바꿈 '앞' 줄
        b = lines[-1]  # 줄바꿈 '뒤' 줄
        # 앞줄이 마침표로 끝나고, '(숫자) '로 시작하지 않으면 비교
        if a.endswith('.') and not re.match(r'^\(\d+\)\s+', a):
            a_base = re.sub(r'\.\s*$', '', a).strip()  # 마침표만 제거한 a
            if b == a_base:
                lines = lines[:-1]  # b 삭제

    s = "\n".join(lines)

    # 2) '- 숫자 -' 패턴 제거 (예: '- 12 -', '-12-', '- 3 -')
    s = re.sub(r'\s*-\s*\d+\s*-\s*', ' ', s)

    # 3) 줄바꿈 제거(붙여쓰기) + 다중 공백 정리
    s = s.replace('\n', '')
    s = re.sub(r'\s{2,}', ' ', s).strip()

# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return s
```
---

## 셀 2

```python
# PDF 페이지 추출 및 문단 파싱 함수
# 함수: extract_pages — 파싱/청킹 관련 서브루틴
def extract_pages(pdf_path: Path) -> Tuple[str, List[Tuple[int, int, int]]]:
    """
    각 페이지 텍스트를 추출해 하나의 큰 문자열로 합치고,
    페이지별 (start_offset, end_offset, page_no) 리스트를 반환.
    """
    texts = []
    ranges = []
    offset = 0
    page_count = get_page_count(pdf_path)
    for p in range(page_count):
        try:
            t = extract_text(str(pdf_path), page_numbers=[p]) or ''
        except Exception:
            t = ''
        t = clean_text(t)
        start = offset
        texts.append(t)
        offset += len(t) + 1   # 페이지 사이에 '\n' 하나 넣음
        end = offset
        ranges.append((start, end, p + 1))  # 1-based page
    full = "\n".join(texts)
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return full, ranges

# 함수: page_of_pos — 파싱/청킹 관련 서브루틴
def page_of_pos(pos: int, page_ranges: List[Tuple[int, int, int]]) -> int:
    for (s, e, page) in page_ranges:
        if s <= pos < e:
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
            return page
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return page_ranges[-1][2] if page_ranges else 1

# 함수: parse_pdf_into_paragraphs — 파싱/청킹 관련 서브루틴
def parse_pdf_into_paragraphs(pdf_path: Path) -> Dict[str, Any]:
    # 제목/번호: 1~2쪽 샘플 + 파일명 백업
    try:
        sample = (extract_text(str(pdf_path), page_numbers=[0]) or '') + \
                 (extract_text(str(pdf_path), page_numbers=[1]) or '')
    except Exception:
        sample = ''
    std_no, title = extract_title_and_no_from_text(sample, pdf_path.name)

    # 전체 텍스트 + 페이지 오프셋 맵
    full, pranges = extract_pages(pdf_path)
    if not full:
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
        return {
            'standard_no': std_no,
            'title': title,
            'source_file': pdf_path.name,
            'paragraphs': []
        }

    # 문단 경계: 문단번호 토큰 매칭 위치 ~ 다음 토큰 직전까지
    paragraphs = []
    matches = list(RE_PARA_NUM.finditer(full))
    for i, m in enumerate(matches):
        para_id = m.group('num')  # 괄호 없는 숫자 계열만
        start_text = m.end()
        end_text = matches[i+1].start() if i + 1 < len(matches) else len(full)
        raw_para = clean_text(full[start_text:end_text])
        if not raw_para:
            continue

        page = page_of_pos(m.start(), pranges)

        # 다음 문단번호가 실제로 존재하는지 플래그 (중복줄 삭제 규칙 활성화 여부)
        has_next = (i + 1 < len(matches))
        para_text = postprocess_text(raw_para, has_next_para=has_next)

        paragraphs.append({
            'para_id': para_id,
            'page': page,
            'text': para_text
        })

# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return {
        'standard_no': std_no,
        'title': title,
        'source_file': pdf_path.name,
        'paragraphs': paragraphs
    }
```
---

## 셀 3

```python
# JSON 파일 생성 함수
# 함수: run_to_single_json — 파싱/청킹 관련 서브루틴
def run_to_single_json(pdf_dir: Path = config.pdf_dir, out_path: Path = config.json_path):
    """
    폴더 내 모든 PDF를 파싱해 하나의 JSON 파일로 저장.
    구조:
    {
      "documents": [
        {
          "standard_no": "1116",
          "title": "리스",
          "source_file": "K-IFRS_제1116호_리스.pdf",
          "paragraphs": [
            {"para_id":"1","page":5,"text":"..."},
            ...
          ]
        },
        ...
      ]
    }
    """
    pdfs = sorted([p for p in pdf_dir.glob('*.pdf')], key=lambda p: p.name)
    combined = {'documents': []}
    for i, pdf in enumerate(pdfs, 1):
        try:
            doc = parse_pdf_into_paragraphs(pdf)
            combined['documents'].append(doc)
            print(f"[{i}/{len(pdfs)}] parsed: {pdf.name} (paras: {len(doc['paragraphs'])})")
        except Exception as e:
            print(f"[ERROR] {pdf.name}: {e}")

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    print("Saved ->", out_path)

# PDF -> JSON 변환 실행
run_to_single_json()
```
---

## 셀 4

```python
# 전처리 패턴 정의
# 1) 부분 삭제: [ ... 삭제됨 ] / [ ... 삭제함 ]
DEL_BRACKET_PATTERN = re.compile(r"\[[^\]]*삭제(?:됨|함)\]", re.UNICODE)

# 2) 문장 존재 여부: 간단히 '.' 포함 여부로 판단
# 함수: has_sentence — 파싱/청킹 관련 서브루틴
def has_sentence(text: str) -> bool:
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return '.' in text

# 3) 꼬리 허용 표식
COLON_ANY = re.compile(r":|：")  # 콜론 유니코드 포함
CIRCLED_ANY = re.compile(r"[⑴-⑽①-⑳㉠-㉿]")  # 특수 번호 기호
PAREN_NUMBER_START = re.compile(r"^\s*[\(（]\s*\d+\s*[\)）]")  # (1), （1） 등
PAREN_LETTER_START = re.compile(r"^\s*[\(（]\s*[A-Za-z가-힣一-龥]\s*[\)）]")  # (A)/(가)/(一) 등

# 함수: allow_tail — 파싱/청킹 관련 서브루틴
def allow_tail(tail: str) -> bool:
    # 꼬리에 콜론/특수기호가 '어디든' 포함되면 허용
    if COLON_ANY.search(tail):
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
        return True
    if CIRCLED_ANY.search(tail):
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
        return True
    # 괄호 번호/문자는 '시작'에 있으면 허용
    if PAREN_NUMBER_START.search(tail):
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
        return True
    if PAREN_LETTER_START.search(tail):
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
        return True
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return False
```
---

## 셀 5

```python
# JSON 전처리 함수
# 함수: clean_json_data — 파싱/청킹 관련 서브루틴
def clean_json_data(input_path: Path = config.json_path, 
                   output_path: Path = config.cleaned_json_path):
    from copy import deepcopy

    # 원본 JSON 로드
    with open(input_path, encoding='utf-8') as f:
        data = json.load(f)
    orig = deepcopy(data)
    
    # 통계 카운터
    removed_no_sentence = 0
    removed_short = 0
    removed_empty_after_cut = 0
    trimmed_tail = 0
    modified_del_marks = 0

    # 모든 문서에 대해 전처리 수행
    for doc in data.get('documents', []):
        new_paras = []
        for p in doc.get('paragraphs', []):
            text = (p.get('text') or '')
            
            # (1) 부분 삭제: [ ... 삭제됨/삭제함 ] -> 부분 문자열 제거
            new_text = DEL_BRACKET_PATTERN.sub("", text)
            if new_text != text:
                modified_del_marks += 1
            # 공백 정리
            new_text = re.sub(r"\s{2,}", " ", new_text).strip()

            # (2) 부분 삭제 후 완전 비면 drop
            if not new_text:
                removed_empty_after_cut += 1
                continue

            # (3) 문장이 있는지 확인 ('.' 포함)
            if not has_sentence(new_text):
                removed_no_sentence += 1
                continue

            # (4) 마지막 '.' 이후의 꼬리 처리
            last_dot = new_text.rfind('.')
            if last_dot >= 0 and last_dot + 1 < len(new_text):
                tail = new_text[last_dot + 1:].strip()
                if tail and not allow_tail(tail):
                    new_text = new_text[:last_dot + 1].strip()
                    trimmed_tail += 1

            # (5) 너무 짧은 문단은 제거 (10자 이하)
            if len(new_text) <= 10:
                removed_short += 1
                continue

            # 최종 정제된 텍스트로 업데이트
            p['text'] = new_text
            new_paras.append(p)

        # 정제된 문단으로 교체
        doc['paragraphs'] = new_paras

    # 통계 출력
    print('=== 전처리 통계 ===')
    print(f'[삭제됨] 표시 제거: {modified_del_marks:,}')
    print(f'제거된 빈 문단: {removed_empty_after_cut:,}')
    print(f'제거된 무문장: {removed_no_sentence:,}')
    print(f'제거된 짧은문단: {removed_short:,}')
    print(f'꼬리 정리: {trimmed_tail:,}')

    # 저장
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료 -> {output_path}")

# 전처리 실행
clean_json_data()
```
---

## 셀 6

```python
# 임베딩 생성을 위한 기본 설정
from sentence_transformers import SentenceTransformer
import numpy as np

# 임베딩 캐시 파일 경로
TITLE_EMB_PATH = config.cache_dir / f'title_emb_{config.embedding_model.replace("/", "_")}.npy'
PARA_EMB_PATH = config.cache_dir / f'para_emb_{config.embedding_model.replace("/", "_")}.npy'

# JSON 로드 & 인덱스 구성
with config.cleaned_json_path.open(encoding='utf-8') as f:
    data = json.load(f)

docs = data.get('documents', [])
title_keys = []
title_texts = []
title_to_para_indices = defaultdict(list)
paragraphs = []

for d in docs:
    std = d.get('standard_no')
    ttl = d.get('title') or ''
    src = d.get('source_file') or ''
    key = (std, ttl, src)
    if key not in title_keys:
        title_keys.append(key)
        head = (d.get('paragraphs', [{}])[:3])
        head_txt = " ".join([(p.get('text') or '') for p in head])
        title_texts.append(f"{ttl}\n{src}\n{head_txt[:1000]}")
    base_idx = len(paragraphs)
    for p in d.get('paragraphs', []):
        paragraphs.append({
            "std": std, "title": ttl, "source": src,
            "page": p.get('page'), "para_id": p.get('para_id'), "text": p.get('text') or ''
        })
        title_to_para_indices[key].append(base_idx); base_idx += 1

print('제목:', len(title_keys), '| 문단:', len(paragraphs))
```
---

## 셀 7

```python
# 임베딩 생성 함수
# 함수: create_embeddings — 파싱/청킹 관련 서브루틴
def create_embeddings(model_name: str = config.embedding_model, rebuild: bool = config.rebuild):
    """임베딩을 생성하거나 캐시에서 로드"""
    if not rebuild and TITLE_EMB_PATH.exists() and PARA_EMB_PATH.exists():
        print('캐시된 임베딩 로드 중...')
        title_emb = np.load(TITLE_EMB_PATH)
        para_emb = np.load(PARA_EMB_PATH)
        print(f'제목 임베딩: {title_emb.shape} | 문단 임베딩: {para_emb.shape}')
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
        return title_emb, para_emb

    print(f'새로운 임베딩 생성 중 (모델: {model_name})...')
    model = SentenceTransformer(model_name)
    
    print('제목 임베딩 생성...')
# 토큰 단위 제어: 모델 컨텍스트 길이를 넘지 않도록 안전 가드
    title_emb = model.encode(title_texts, show_progress_bar=True, 
                           batch_size=32, normalize_embeddings=True)
    np.save(TITLE_EMB_PATH, title_emb)
    
    print('문단 임베딩 생성...')
    para_texts = [p['text'] for p in paragraphs]
# 토큰 단위 제어: 모델 컨텍스트 길이를 넘지 않도록 안전 가드
    para_emb = model.encode(para_texts, show_progress_bar=True,
                          batch_size=32, normalize_embeddings=True)
    np.save(PARA_EMB_PATH, para_emb)
    
    print(f'제목 임베딩: {title_emb.shape} | 문단 임베딩: {para_emb.shape}')
    print(f'캐시 저장 완료 -> {TITLE_EMB_PATH}, {PARA_EMB_PATH}')
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return title_emb, para_emb

# 임베딩 생성 또는 로드
title_embeddings, para_embeddings = create_embeddings()
```
---

## 셀 8

```python
# BM25 기반 단어 가중치 검색(옵션)
# BM25 검색 구현
# 함수: normalize — 파싱/청킹 관련 서브루틴
def normalize(t: str) -> str:
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return t.strip().lower()

HAN_ENG_NUM = re.compile(r'[가-힣A-Za-z0-9]+', re.UNICODE)
STOP = set(['그리고','등','및','또는','그러나','이는','그','이','저','것','수','등의'])

# 함수: tokenize — 파싱/청킹 관련 서브루틴
def tokenize(t: str):
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return HAN_ENG_NUM.findall(normalize(t))

# 함수: filter_tokens — 파싱/청킹 관련 서브루틴
def filter_tokens(tokens: List[str]) -> List[str]:
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return [w for w in tokens if w not in STOP and len(w) > 1]

# BM25 기반 단어 가중치 검색(옵션)
class BM25:
# 함수: __init__ — 파싱/청킹 관련 서브루틴
    def __init__(self, docs_tokens, k1=1.5, b=0.75):
        self.docs_tokens = docs_tokens
        self.N = len(docs_tokens)
        self.k1 = k1; self.b = b
        self.avgdl = sum(len(d) for d in docs_tokens) / max(1, self.N)
        self.df = Counter()
        for doc in docs_tokens:
            for term in set(doc):
                self.df[term] += 1
        self.idf = {t: math.log(1 + (self.N - df + 0.5)/(df + 0.5)) 
                   for t, df in self.df.items()}
        self.tf = [Counter(doc) for doc in docs_tokens]

# 함수: _score_doc — 파싱/청킹 관련 서브루틴
    def _score_doc(self, q_tokens, i):
        score, tf, dl = 0.0, self.tf[i], len(self.docs_tokens[i])
        for term in q_tokens:
            idf = self.idf.get(term)
            if idf is None: continue
            f = tf.get(term, 0)
            if f == 0: continue
            denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            score += idf * (f * (self.k1 + 1)) / denom
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
        return score

# 함수: search — 파싱/청킹 관련 서브루틴
    def search(self, q_tokens, topk=50):
        scores = []
        for i in range(self.N):
            s = self._score_doc(q_tokens, i)
            if s != 0.0:
                scores.append((i, s))
        scores.sort(key=lambda x: x[1], reverse=True)
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
        return scores[:topk]

# 함수: search_subset — 파싱/청킹 관련 서브루틴
    def search_subset(self, q_tokens, allowed: set, topk=50):
        scores = []
        for i in allowed:
            s = self._score_doc(q_tokens, i)
            if s != 0.0:
                scores.append((i, s))
        scores.sort(key=lambda x: x[1], reverse=True)
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
        return scores[:topk]

# BM25 기반 단어 가중치 검색(옵션)
# BM25 인덱스 구축
para_tokens = [filter_tokens(tokenize(p['text'])) for p in paragraphs]
# BM25 기반 단어 가중치 검색(옵션)
bm25 = BM25(para_tokens)
# BM25 기반 단어 가중치 검색(옵션)
print('BM25 인덱스 구축 완료')
```
---

## 셀 9

```python
# 벡터 검색 및 하이브리드 검색 구현
class SearchEngine:
# 함수: __init__ — 파싱/청킹 관련 서브루틴
    def __init__(self, model_name: str = config.embedding_model):
        self.model = SentenceTransformer(model_name)
        self.title_emb = title_embeddings
        self.para_emb = para_embeddings
# BM25 기반 단어 가중치 검색(옵션)
        self.bm25 = bm25

# 함수: _vector_sim — 파싱/청킹 관련 서브루틴
    def _vector_sim(self, q_emb, emb_matrix, topk=50):
        scores = (emb_matrix @ q_emb).squeeze()
        idxs = np.argsort(scores)[-topk:][::-1]
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
        return [(int(i), float(scores[i])) for i in idxs]

# 함수: search — 파싱/청킹 관련 서브루틴
    def search(self, query: str, mode: str = 'hybrid', topk: int = 10):
        # 쿼리 임베딩
# 토큰 단위 제어: 모델 컨텍스트 길이를 넘지 않도록 안전 가드
        q_emb = self.model.encode([query], normalize_embeddings=True)
        
        # 제목 검색 (벡터)
        title_matches = self._vector_sim(q_emb, self.title_emb, topk=3)
        title_para_ids = set()
        for idx, _ in title_matches:
            title_para_ids.update(title_to_para_indices[title_keys[idx]])

# BM25 기반 단어 가중치 검색(옵션)
        # BM25 검색 (해당 제목 내에서만)
        q_tokens = filter_tokens(tokenize(query))
# BM25 기반 단어 가중치 검색(옵션)
        if mode in ('bm25', 'hybrid') and q_tokens:
# BM25 기반 단어 가중치 검색(옵션)
            bm_matches = self.bm25.search_subset(q_tokens, title_para_ids, topk=topk)
# BM25 기반 단어 가중치 검색(옵션)
            if bm_matches:  # BM25 결과가 있으면 사용
                results = bm_matches
            else:  # 없으면 벡터 검색으로 폴백
                results = self._vector_sim(q_emb, self.para_emb, topk=topk)
        else:  # 벡터 검색만 사용
            results = self._vector_sim(q_emb, self.para_emb, topk=topk)

        # 결과 포매팅
        formatted = []
        for idx, score in results:
            p = paragraphs[idx]
            formatted.append({
                'score': round(score, 3),
                'standard_no': p['std'],
                'title': p['title'],
                'para_id': p['para_id'],
                'page': p['page'],
                'text': p['text']
            })
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
        return formatted

# 검색 엔진 초기화
search_engine = SearchEngine()
print('검색 엔진 준비 완료')
```