
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL loader for Samsung audit JSONs (2014–2024) compatible with schema.sql
Schema: audit_finance (dim_* and fact_financial)
Requires: psycopg2-binary (pip install psycopg2-binary)

Usage:
  export PGHOST=127.0.0.1 PGPORT=5433 PGUSER=kwonseoyoung PGPASSWORD='***' PGDATABASE=auditdb
  python pg_loader.py --schema /absolute/path/schema.sql --data_dir /absolute/path/staging
"""
import os, json, glob, argparse, hashlib
import psycopg2

SCHEMA_NAME = "audit_finance"

SECTION_MAP = {
    "balance": "balance",
    "income": "income",
    "cashflow": "cashflow",
    "equity": "equity",
    "comprehensive": "comprehensive",
}
STMT_MAP = {
    "balance": "BS",
    "income": "PL",
    "cashflow": "CF",
    "equity": "EQ",
    "comprehensive": "OCI",
}

def read_file_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return raw.decode("utf-8")
    except Exception:
        return raw.decode("cp949", errors="ignore")

def apply_schema(conn, schema_path):
    sql_text = read_file_text(schema_path)
    with conn.cursor() as cur:
        cur.execute(sql_text)
    conn.commit()

def upsert_company(cur, company_name):
    cur.execute(f"""
        INSERT INTO {SCHEMA_NAME}.dim_company (company_name)
        VALUES (%s)
        ON CONFLICT (company_name) DO UPDATE SET company_name = EXCLUDED.company_name
        RETURNING company_id
    """, (company_name,))
    return cur.fetchone()[0]

def upsert_unit(cur, unit_name):
    cur.execute(f"""
        INSERT INTO {SCHEMA_NAME}.dim_unit (unit_name)
        VALUES (%s)
        ON CONFLICT (unit_name) DO UPDATE SET unit_name = EXCLUDED.unit_name
        RETURNING unit_id
    """, (unit_name,))
    return cur.fetchone()[0]

def upsert_section(cur, section_code):
    cur.execute(f"""
        INSERT INTO {SCHEMA_NAME}.dim_section (section_code)
        VALUES (%s)
        ON CONFLICT (section_code) DO UPDATE SET section_code = EXCLUDED.section_code
        RETURNING section_id
    """, (section_code,))
    return cur.fetchone()[0]

def upsert_period(cur, anchor_year, period_label="당기", period_order=0, start_date=None, end_date=None):
    cur.execute(f"""
        INSERT INTO {SCHEMA_NAME}.dim_period (anchor_year, period_label, period_order, start_date, end_date)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (anchor_year, period_order)
        DO UPDATE SET period_label = EXCLUDED.period_label,
                      start_date  = COALESCE({SCHEMA_NAME}.dim_period.start_date, EXCLUDED.start_date),
                      end_date    = COALESCE({SCHEMA_NAME}.dim_period.end_date, EXCLUDED.end_date)
        RETURNING period_id
    """, (anchor_year, period_label, period_order, start_date, end_date))
    return cur.fetchone()[0]

def upsert_account_chain(cur, account_path, section_code):
    """
    Ensure the full account_path hierarchy exists in dim_account (split by '_').
    Returns the leaf account_id.
    """
    tokens = account_path.split("_") if account_path else []
    parent_id, leaf_id = None, None
    for i, tok in enumerate(tokens):
        sub_path = "_".join(tokens[:i+1])
        cur.execute(f"""
            INSERT INTO {SCHEMA_NAME}.dim_account (account_name, statement_type, account_path, parent_account_id)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (account_path) DO UPDATE
                SET statement_type    = EXCLUDED.statement_type,
                    parent_account_id = COALESCE({SCHEMA_NAME}.dim_account.parent_account_id, EXCLUDED.parent_account_id)
            RETURNING account_id
        """, (tok, STMT_MAP.get(section_code), sub_path, parent_id))
        parent_id = cur.fetchone()[0]
        if i == len(tokens)-1:
            leaf_id = parent_id

    if not tokens and account_path:
        # single-token path
        cur.execute(f"""
            INSERT INTO {SCHEMA_NAME}.dim_account (account_name, statement_type, account_path, parent_account_id)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (account_path) DO UPDATE SET statement_type=EXCLUDED.statement_type
            RETURNING account_id
        """, (account_path, STMT_MAP.get(section_code), account_path, None))
        leaf_id = cur.fetchone()[0]
    return leaf_id

def upsert_source(cur, file_name, table_title=None, anchor_year=None, file_path=None, parser_version="json_v1"):
    sha256 = None
    try:
        with open(file_path or file_name, "rb") as f:
            sha256 = hashlib.sha256(f.read()).hexdigest()
    except Exception:
        pass

    cur.execute(f"""
        INSERT INTO {SCHEMA_NAME}.dim_source (file_name, file_path, anchor_year, table_tag, table_title, parser_version, sha256)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
        RETURNING source_id
    """, (os.path.basename(file_name), file_path, anchor_year, None, table_title, parser_version, sha256))
    row = cur.fetchone()
    if row:
        return row[0]
    # fallback: find existing
    cur.execute(f"""
        SELECT source_id FROM {SCHEMA_NAME}.dim_source
        WHERE file_name=%s AND COALESCE(file_path,'')=COALESCE(%s,'')
    """, (os.path.basename(file_name), file_path))
    got = cur.fetchone()
    return got[0] if got else None

def insert_fact(cur, company_id, account_id, period_id, unit_id, section_id, source_id,
                row_no, subject_id, value_num, value_text=None,
                consolidation=None, gaap_basis=None, note_inline=None):
    cur.execute(f"""
        INSERT INTO {SCHEMA_NAME}.fact_financial
            (company_id, account_id, period_id, unit_id, source_id, section_id,
             row_no, subject_id, value_text, value_num, consolidation, gaap_basis, note_inline)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_id, account_id, period_id, unit_id, section_id, source_id, row_no, subject_id)
        DO UPDATE SET value_num=EXCLUDED.value_num, value_text=EXCLUDED.value_text
    """, (company_id, account_id, period_id, unit_id, source_id, section_id,
          row_no, subject_id, value_text, value_num, consolidation, gaap_basis, note_inline))

def load_json_file(conn, path):
    # tolerant UTF-8/CP949
    with open(path, "rb") as f:
        raw = f.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        data = json.loads(raw.decode("cp949", errors="ignore"))
    rows = data if isinstance(data, list) else [data]

    with conn.cursor() as cur:
        for item in rows:
            fiscal_year = int(item.get("fiscal_year"))
            company     = item.get("company") or "삼성전자주식회사"
            unit_name   = item.get("unit") or "백만원"
            source_file = item.get("source_file") or os.path.basename(path)

            company_id = upsert_company(cur, company)
            unit_id    = upsert_unit(cur, unit_name)
            period_id  = upsert_period(cur, fiscal_year, "당기", 0, None, None)

            metas = item.get("meta") or []
            section_cache = {}
            for m in metas:
                fs = m.get("fs_type")
                sec = SECTION_MAP.get(fs)
                if not sec: 
                    continue
                if sec not in section_cache:
                    section_cache[sec] = upsert_section(cur, sec)

            table_title = metas[0].get("table_title") if metas and isinstance(metas[0], dict) else None
            source_id = upsert_source(cur, source_file, table_title=table_title, anchor_year=fiscal_year, file_path=source_file)

            # From meta[] (preferred)
            for m in metas:
                key        = m.get("key")
                val        = m.get("value")
                fs_type    = m.get("fs_type")
                row_no     = m.get("row_no")
                subject_id = m.get("subject_id")
                note_inline= m.get("note") or None
                consolidation = m.get("consolidation")
                gaap_basis    = m.get("gaap")

                sec = SECTION_MAP.get(fs_type)
                if not sec or key is None:
                    continue
                section_id = section_cache.get(sec) or upsert_section(cur, sec)
                account_id = upsert_account_chain(cur, key, sec)
                # Prefer numeric if it is number, else store as text
                if isinstance(val, (int, float)):
                    insert_fact(cur, company_id, account_id, period_id, unit_id, section_id, source_id,
                                row_no=row_no, subject_id=subject_id, value_num=val, value_text=None,
                                consolidation=consolidation, gaap_basis=gaap_basis, note_inline=note_inline)
                else:
                    insert_fact(cur, company_id, account_id, period_id, unit_id, section_id, source_id,
                                row_no=row_no, subject_id=subject_id, value_num=None, value_text=str(val) if val is not None else None,
                                consolidation=consolidation, gaap_basis=gaap_basis, note_inline=note_inline)

            # Defensive: scan top-level numeric keys not present in meta[]
            for k, v in item.items():
                if k in {"fiscal_year","company","unit","source_file","meta"}:
                    continue
                if isinstance(v, (int, float)):
                    if "현금흐름" in k:
                        sec = "cashflow"
                    elif any(x in k for x in ["자본","포괄","총포괄"]):
                        sec = "equity" if "변동" in k else "comprehensive" if "포괄" in k else "balance"
                    elif any(x in k for x in ["매출","영업이익","총이익","법인세","순이익","주당이익"]):
                        sec = "income"
                    elif any(x in k for x in ["자산","부채"]):
                        sec = "balance"
                    else:
                        sec = "income"
                    if sec not in section_cache:
                        section_cache[sec] = upsert_section(cur, sec)
                    section_id = section_cache[sec]
                    account_id = upsert_account_chain(cur, k, sec)
                    insert_fact(cur, company_id, account_id, period_id, unit_id, section_id, source_id,
                                row_no=None, subject_id=None, value_num=v, value_text=None)

    conn.commit()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", required=True, help="Path to schema.sql")
    ap.add_argument("--data_dir", required=True, help="Directory containing financial_statements_dynamic_*.json")
    args = ap.parse_args()

    conn = psycopg2.connect(
        host=os.getenv("PGHOST","127.0.0.1"),
        port=int(os.getenv("PGPORT","5433")),
        user=os.getenv("PGUSER","kwonseoyoung"),
        password=os.getenv("PGPASSWORD",""),
        dbname=os.getenv("PGDATABASE","auditdb"),
    )
    try:
        apply_schema(conn, args.schema)
        files = sorted(glob.glob(os.path.join(args.data_dir, "financial_statements_dynamic_*.json")))
        if not files:
            raise SystemExit("No JSON files found in --data_dir")
        for p in files:
            print(f"[LOAD] {p}")
            load_json_file(conn, p)
        print("DONE.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
