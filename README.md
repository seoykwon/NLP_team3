# 자연어처리 수업 삼성전자 감사보고서 과제
## 파싱 방법
1. ```python -m venv .venv```   
2. ```pip install -r requirements.txt```   
3. ```source .venv/bin/activate```   
4. ```python parse.py```   
5. 정합성 규칙 확인: ```python integrity.py```   

## DB 생성 및 초기 구축
1. ```psql -U postgres -d postgres -p 5433```  
2. ```CREATE USER "user" WITH PASSWORD '0000';```  
3. ```GRANT CONNECT ON DATABASE auditdb TO "user"; \n GRANT ALL PRIVILEGES ON DATABASE auditdb TO "user";```   
4. 
```\c auditdb   -- auditdb로 전환 ```  
```-- 스키마에 접근권한  GRANT USAGE ON SCHEMA audit_finance TO "user";   GRANT CREATE ON SCHEMA audit_finance TO "user"; ```  
```-- 모든 테이블 권한  GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA audit_finance TO "user";```    
```-- 시퀀스(IDENTITY 컬럼) 권한   GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA audit_finance TO "user";```   

## DB 재접속
```psql -U user -d auditdb -h localhost -p 5433```    

## DB 내 테이블 생성
1. 방법 1: psql 안에서 실행  ```\i '절대경로'```, ```psql \i schema.sql \dn+ \dt audit_finance.*```   
2. 방법 2: 터미널에서 직접 실행   ```psql -U user -d auditdb -h localhost -p 5433 -f /절대경로/schema.sql```   
3. 실행 확인: psql에서   ```\dn            -- 스키마 목록 보기   \dt audit_finance.*   -- audit_finance 스키마의 테이블 목록 보기```   

## DB 내 .json 파일 데이터 삽입하기
```python pg_loader.py --schema ./schema.sql --data_dir ./staging```    
### 데이터 적재됐는지 확인하기
DB 접속 후, ```SELECT COUNT(*) FROM audit_finance.fact_financial;```

---

## 폴더 구조

```
NLP/
├── DBtactic.md                # DB 전략 문서
├── diagram.png                # 시스템 다이어그램
├── future_plan.md             # 향후 계획 문서
├── integrity.py               # 데이터 정합성 검사 스크립트
├── parse.py                   # 감사보고서 파싱 스크립트
├── pg_loader.py               # JSON 데이터 DB 적재 스크립트
├── README.md                  # 프로젝트 설명서
├── requirements.txt           # Python 패키지 목록
├── schema.sql                 # DB 스키마 정의
├── raw/                       # 원본 감사보고서(HTML)
│   ├── 감사보고서_2014.htm
│   ├── ...
│   └── 감사보고서_2024.htm
├── staging/                   # 파싱된 재무제표(JSON)
│   ├── financial_statements_dynamic_2014.json
│   ├── ...
│   └── financial_statements_dynamic_2024.json
```

## 주요 파일 설명
- `parse.py`: raw 폴더의 HTML 감사보고서를 파싱하여 staging 폴더에 JSON 파일로 저장합니다.
- `integrity.py`: staging 폴더의 JSON 데이터 정합성(규칙) 검사 스크립트입니다.
- `pg_loader.py`: staging 폴더의 JSON 데이터를 DB에 적재합니다.
- `schema.sql`: DB 테이블 및 스키마 정의 SQL 파일입니다.
- `requirements.txt`: 필요한 Python 패키지 목록입니다.
- `raw/`: 연도별 원본 감사보고서(HTML 파일) 저장 폴더입니다.
- `staging/`: 파싱된 재무제표(JSON 파일) 저장 폴더입니다.
- `diagram.png`, `DBtactic.md`, `future_plan.md`: 시스템 구조, DB 전략, 향후 계획 관련 문서입니다.