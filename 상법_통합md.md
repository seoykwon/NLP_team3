# 상법_통합 — 파싱/청킹 코드 요약

다음은 노트북 내에서 파싱/청킹과 직접 관련된 코드 셀을 선별하여, 핵심 의도와 파라미터를 한국어 주석으로 보강한 것입니다.

---

## 셀 1

```python
# 함수: parse_pdf_to_text — 파싱/청킹 관련 서브루틴
def parse_pdf_to_text(pdf_path: Path) -> str:
    """PDF 파일을 텍스트로 변환"""
    reader = PdfReader(str(pdf_path))
    pages = []
    for p in reader.pages:
        try:
            text = p.extract_text() or ""
        except Exception:
            text = ""
        pages.append(text)
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return "\n".join(pages)

# 함수: extract_main_text — 파싱/청킹 관련 서브루틴
def extract_main_text(raw_text: str) -> str:
    """부칙 이전까지의 본문만 추출"""
    import re
    m = re.search(r"(?:^|\n)\s*부칙\s*(?:\n|$)", raw_text)
    if m:
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
        return raw_text[:m.start()].strip()
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return raw_text.strip()

# 함수: parse_articles — 파싱/청킹 관련 서브루틴
def parse_articles(text: str) -> List[Dict]:
    """본문을 조문 단위로 파싱"""
    import re
    
    # 조문 구분 패턴
    rx_art = re.compile(r"""
        (?:제\s*)?(\d+)               # 기본 조문 번호
        (?:\s*의\s*(\d+))?           # 옵션: 의2, 의3 등
        \s*조                        # '조' 글자
        (?:\s*\(([^)]+)\))?         # 옵션: (제목)
        \s*(.+?)                    # 본문 (non-greedy)
        (?=\s*제\s*\d+\s*조|\s*$)   # 다음 조문 시작 또는 끝
    """, re.VERBOSE | re.DOTALL)
    
    blocks = []
    for m in rx_art.finditer(text):
        base = int(m.group(1))
        suffix = int(m.group(2)) if m.group(2) else None
        title = m.group(3)
        body = m.group(4).replace("\n", " ").strip()
        
        art_id = str(base) if suffix is None else f"{base}의{suffix}"
        blocks.append({
            "article_id": art_id,
            "article_number_base": base,
            "article_number_suffix": suffix,
            "title": title,
            "body": body,
            "part": None,  # TODO: 편/장/절 구조 파싱 (필요시)
            "chapter": None,
            "section": None
        })
    
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return blocks

# PDF 파싱 실행
raw_text = parse_pdf_to_text(PDF_PATH)
main_text = extract_main_text(raw_text)
articles = parse_articles(main_text)

# JSON 생성
output = {
    "meta": {
        "title_ko": "상법",
        "source_file": PDF_PATH.name,
        "note": "부칙 제외, 본문 줄바꿈 제거, '제n조의m' 지원"
    },
    "total_articles": len(articles),
    "articles": articles
}

# 저장
out_json = INDEX_DIR.parent / "상법_파싱.json"
with out_json.open("w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"총 {len(articles)}개 조문 파싱 완료")
print(f"저장 경로: {out_json} ({out_json.stat().st_size:,} bytes)")
```
---

## 셀 2

```python
# 함수: make_aliases — 파싱/청킹 관련 서브루틴
def make_aliases(base: int, suf: Optional[int], title: Optional[str]) -> List[str]:
    """조문 번호와 제목으로부터 다양한 검색용 별칭 생성"""
    aliases = []
    # 한국어 기본형
    if suf is None:
        ko_core = f"제{base}조"
    else:
        ko_core = f"제{base}조의{suf}"
    aliases.append(ko_core)
    aliases.append(f"상법 {ko_core}")
    aliases.append(f"상법 {base}조" if suf is None else f"상법 {base}조의{suf}")
    aliases.append(f"{base}조" if suf is None else f"{base}조의{suf}")
    if title:
        aliases.append(f"{ko_core}({title})")
        aliases.append(f"상법 {ko_core}({title})")
    
    # 하이픈 표기
    hyf = f"{base}" if suf is None else f"{base}-{suf}"
    aliases.append(hyf)
    aliases.append(f"제{hyf}조")
    aliases.append(f"상법 제{hyf}조")
    
    # 영어식
    en_core = f"Article {base}" if suf is None else f"Article {base}-{suf}"
    aliases.append(en_core)
    aliases.append(f"KCC {en_core}")
    aliases.append(f"Korean Commercial Code {en_core}")
    
    # 중복 제거 + 안정 정렬
    seen = set(); out = []
    for a in aliases:
        if a not in seen:
            seen.add(a); out.append(a)
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return out

# 함수: build_text — 파싱/청킹 관련 서브루틴
def build_text(rec: Dict) -> str:
    """검색용 텍스트 구성"""
    base = rec.get("article_number_base")
    suf  = rec.get("article_number_suffix")
    head = f"상법 제{base}조" if suf is None else f"상법 제{base}조의{suf}"
    if rec.get("title"):
        head += f" {rec['title']}"
    body = rec.get("body","").replace("\n", " ").strip()
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return f"[{head}] {body}".strip()

# JSON 로드
with open(INDEX_DIR.parent / "상법_파싱.json", "r", encoding="utf-8") as f:
    data = json.load(f)
    
articles = data.get("articles", [])
print(f"로드된 조문 수: {len(articles)}")

# 검색용 데이터 구성
docs = []
for rec in articles:
    base = rec.get("article_number_base")
    suf  = rec.get("article_number_suffix")
    art_id = rec.get("article_id") or (str(base) if suf is None else f"{base}의{suf}")
    title = rec.get("title")

    aliases = make_aliases(base, suf, title)
    text = build_text(rec)
    
    docs.append({
        "id": f"KCC-{art_id}",
        "article_id": art_id,
        "title": title,
        "aliases": aliases,
        "text": text,
        "raw_text": rec.get("body", ""),
        "meta": {
            "law": "상법",
            "source_file": data.get("meta",{}).get("source_file",""),
            "part": rec.get("part"),
            "chapter": rec.get("chapter"),
            "section": rec.get("section"),
        }
    })

print(f"검색용 문서 생성: {len(docs)}개")
print("샘플 문서:", {k:docs[0][k] for k in ["id","article_id","title"]})
```
---

## 셀 3

```python
# 검색 유틸리티
RX_ART_NUM = re.compile(r"(?:제\s*)?(\d+)(?:\s*조\s*의\s*(\\d+)|\\s*조)")

# 함수: normalize_query — 파싱/청킹 관련 서브루틴
def normalize_query(q: str) -> str:
    """검색어 정규화 (조문 번호 처리)"""
    qn = q.strip()
    m = re.search(r"(\d+)\s*의\s*(\d+)", qn)
    extra = []
    if m:
        extra.append(f"{m.group(1)}-{m.group(2)}")
        extra.append(f"제{m.group(1)}조의{m.group(2)}")
    m2 = RX_ART_NUM.search(qn)
    if m2:
        base = m2.group(1); suf = m2.group(2)
        if suf:
            extra += [f"{base}의{suf}", f"{base}-{suf}", 
                     f"제{base}조의{suf}", f"Article {base}-{suf}"]
        else:
            extra += [f"{base}", f"제{base}조", f"Article {base}"]
    if extra:
        qn = qn + " " + " ".join(sorted(set(extra)))
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return qn

# 함수: retrieve — 파싱/청킹 관련 서브루틴
def retrieve(query: str, top_k: int = 10) -> List[Dict]:
    """임베딩 기반 1차 검색"""
    qv = client.embeddings.create(model=EMB_MODEL, input=[query]).data[0].embedding
    qv = np.array(qv, dtype=np.float32)
    D, I = index.search(qv.reshape(1, -1), top_k)
    I, D = I[0], D[0]
    
    results = []
    for i, s in zip(I, D):
        if i < 0:  # FAISS의 패딩
            continue
        m = METAS[i]
        results.append({
            "index": int(i),
            "score": float(s),
            "text": m["raw_text"],
            "meta": m["meta"]
        })
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return results

# 리랭크 단계(옵션): 초기 검색 결과를 재정렬
# 함수: llm_rerank — 파싱/청킹 관련 서브루틴
def llm_rerank(query: str, candidates: List[Dict], take: int = 6, 
               model: str = LLM_MODEL) -> List[Dict]:
    """LLM 기반 후보 재정렬"""
    # 컨텍스트 구성
    bullet = []
    for i, c in enumerate(candidates):
        snippet = c["text"].replace("\n", " ").strip()
        if len(snippet) > 600:
            snippet = snippet[:600] + " ..."
        bullet.append(f"[{i}] {snippet}")
    
    # LLM 프롬프트
    prompt = f"""당신은 문서검색 재랭킹을 담당하는 평가자입니다.
사용자 질문: {query}

아래 후보 발췌문들 중에서, 질문에 대한 **정답 근거**가 가장 잘 담긴 순서로 재정렬하세요.
가능하면 숫자/연도/표 제목 일치 여부를 중시하세요.

후보:
{chr(10).join(bullet)}

출력 형식:
- 상위 {take}개의 인덱스만 콤마로 나열 (예: 3,0,5,1,2,4)
- 다른 설명은 쓰지 말 것
"""
    msg = [
# 리랭크 단계(옵션): 초기 검색 결과를 재정렬
        {"role":"system","content":"You are a rigorous re-ranker that only outputs indices."},
        {"role":"user","content": prompt}
    ]
    
    # LLM 호출 및 파싱
    resp = client.chat.completions.create(model=model, messages=msg, temperature=0)
    line = resp.choices[0].message.content.strip()
    idxs = []
# 텍스트 분리(스플리팅) 단계: 문단/문장/토큰 기준으로 나눔
    for tok in line.replace(" ", "").split(","):
        if tok.isdigit():
            idxs.append(int(tok))
    
    # 안전장치
    if not idxs:
        idxs = list(range(min(take, len(candidates))))
    idxs = idxs[:take]
    
    # 재정렬된 결과 반환
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return [candidates[i] for i in idxs]

# 함수: build_context_snippets — 파싱/청킹 관련 서브루틴
def build_context_snippets(chunks: List[Dict], max_chars: int = 1800) -> str:
    """LLM 답변용 컨텍스트 구성"""
    ctx_lines = []
    for rank, c in enumerate(chunks, start=1):
        tag = f"[E{rank}]"
        snippet = c["text"].strip()
        if len(snippet) > 1200:
            snippet = snippet[:1200] + " ..."
        ctx_lines.append(f"{tag} {snippet}")
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return "\n\n".join(ctx_lines)

# 리랭크 단계(옵션): 초기 검색 결과를 재정렬
# 함수: answer_with_rag_llm — 파싱/청킹 관련 서브루틴
def answer_with_rag_llm(query: str, retrieve_k: int = 12, rerank_take: int = 6, 
                       model: str = LLM_MODEL, temperature: float = 0.0, 
                       debug: bool = False) -> Dict:
    """RAG + LLM 기반 질의응답"""
    # 1) 초기 검색
    cand = retrieve(query, top_k=retrieve_k)
    
    # 2) LLM 재정렬
# 리랭크 단계(옵션): 초기 검색 결과를 재정렬
    top = llm_rerank(query, cand, take=rerank_take, model=model)
    
    # 3) 컨텍스트 구성
    ctx = build_context_snippets(top)
    
    # 4) 답변 생성
    prompt = f"""당신은 정확한 회계/법률 문서 QA 어시스턴트입니다.
아래 '근거 발췌문'만을 **사실 근거**로 사용하여 질문에 답하세요.
근거에 없는 내용은 추정하지 말고, '근거 부족'이라고 밝혀주세요.
필요하면 답변 문장 끝에 [E1], [E2]처럼 근거 번호를 달아주세요.

[질문]
{query}

[근거 발췌문]
{ctx}
"""
    msgs = [
        {"role":"system","content":"You are a precise, Korean-speaking assistant for financial/legal documents."},
        {"role":"user","content": prompt}
    ]
    resp = client.chat.completions.create(
        model=model, messages=msgs, temperature=temperature
    )
    answer = resp.choices[0].message.content.strip()
    
# 반환: 청킹 결과(문자열 리스트/문서 리스트/메타데이터 포함 구조)
    return {
        "answer": answer,
        "evidence": top,
        "raw_candidates": cand if debug else None
    }
```