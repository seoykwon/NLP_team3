
from pathlib import Path
import json
import math
from typing import Dict, Any, List, Tuple, Optional
import argparse
import re

TOL_ABS_DEFAULT = 1.0  # absolute tolerance in the same unit as the JSON (e.g., 백만원)
TOL_REL_DEFAULT = 1e-4 # relative tolerance for very large numbers (0.01%)
NUMBER_KEYS_LIKELY_POSITIVE = {
    # Balance sheet
    "자산총계","유동자산","비유동자산",
    "부채총계","유동부채","비유동부채",
    "자본총계","자본금","주식발행초과금","이익잉여금",
    # Income statement
    "매출액","매출원가","매출총이익","영업이익","법인세비용차감전순이익","당기순이익",
    "판매비와관리비","매출총이익_판매비와관리비",
    # Cash equivalents (ending should be >=0)
    "기말의현금및현금성자산","기초의현금및현금성자산",
    # Components
    "유동자산_현금및현금성자산","유동자산_재고자산",
    "유동부채_충당부채","비유동부채_장기충당부채",
}
# Keys that are typically allowed to be negative (so we won't flag them)
ALLOW_NEGATIVE_KEYS = {
    "기타자본항목","현금및현금성자산의감소(Ⅰ+Ⅱ+Ⅲ)",
    "투자활동현금흐름","재무활동현금흐름",
    "영업활동현금흐름_법인세납부액","영업활동현금흐름_이자의지급",
    "총포괄손익","기타포괄손익",
    "총포괄손익_매도가능금융자산평가_총계",
    "총포괄손익_순확정급여부채재측정요소_총계",
    "자본에직접인식된주주와의거래_배당_총계",
    "자본에직접인식된주주와의거래_자기주식의취득_총계",
    "총포괄손익_매각예정분류_기타자본항목",
}

ESSENTIAL_KEYS = [
    "fiscal_year","company","unit",
    "자산총계","유동자산","비유동자산",
    "부채총계","자본총계","부채와자본총계",
    "매출액","매출원가","매출총이익",
    "영업이익",
    "법인세비용차감전순이익","당기순이익",
    "영업활동현금흐름","투자활동현금흐름","재무활동현금흐름",
    "현금및현금성자산의감소(Ⅰ+Ⅱ+Ⅲ)",
    "기초의현금및현금성자산","기말의현금및현금성자산",
]

def near(a: Optional[float], b: Optional[float], tol_abs=TOL_ABS_DEFAULT, tol_rel=TOL_REL_DEFAULT) -> bool:
    if a is None or b is None:
        return False
    diff = abs(a - b)
    if diff <= tol_abs:
        return True
    denom = max(abs(a), abs(b), 1.0)
    return (diff / denom) <= tol_rel

def get(d: Dict[str, Any], key: str) -> Optional[float]:
    v = d.get(key, None)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.replace(",", "").strip()
        try:
            return float(s)
        except Exception:
            return None
    return None

def check_structural(json_obj: Dict[str, Any]) -> List[str]:
    issues = []
    for k in ESSENTIAL_KEYS:
        if k not in json_obj:
            issues.append(f"[구조적] 필수 키 누락: {k}")
    metas = json_obj.get("meta", [])
    if isinstance(metas, list):
        for m in metas:
            mk = m.get("key")
            mv = m.get("value")
            if mk is None:
                issues.append("[구조적] meta 항목에 key 누락")
                continue
            tv = json_obj.get(mk, None)
            if tv is None:
                issues.append(f"[구조적] meta.key='{mk}' 이(가) 상위 키에 없음")
            else:
                if isinstance(mv, (int,float)) and isinstance(tv, (int,float)) and not near(float(mv), float(tv)):
                    issues.append(f"[구조적] meta.key='{mk}' 값({mv})과 상위 값({tv}) 불일치")
    else:
        issues.append("[구조적] meta 필드가 리스트가 아님 혹은 없음")
    for k, v in json_obj.items():
        if k == "meta":
            continue
        if isinstance(v, str) and re.search(r"\d,\d", v):
            issues.append(f"[구조적] 숫자열에 구분기호(,)가 남아 있음: {k}='{v}'")
    return issues

def check_format(json_obj: Dict[str, Any]) -> List[str]:
    issues = []
    unit_top = json_obj.get("unit")
    metas = json_obj.get("meta", [])
    unit_mismatch = 0
    for m in metas if isinstance(metas, list) else []:
        mu = m.get("unit")
        if mu and unit_top and mu != unit_top:
            unit_mismatch += 1
    if unit_mismatch > 0:
        issues.append(f"[형식] unit 불일치 meta 건수: {unit_mismatch} (상위: {unit_top})")
    fy = json_obj.get("fiscal_year")
    try:
        fy_i = int(fy)
        if fy_i < 1990 or fy_i > 2100:
            issues.append(f"[형식] fiscal_year 비정상: {fy}")
    except Exception:
        issues.append(f"[형식] fiscal_year 숫자 아님: {fy}")
    return issues

def check_content(json_obj: Dict[str, Any], tol_abs=TOL_ABS_DEFAULT, tol_rel=TOL_REL_DEFAULT) -> List[str]:
    I = lambda k: get(json_obj, k)
    issues = []
    def assert_eq(lhs: float, rhs: float, label: str, left_expr: str, right_expr: str):
        if lhs is None or rhs is None:
            issues.append(f"[내용] {label}: 값 누락 (좌:{left_expr} 우:{right_expr})")
        elif not near(lhs, rhs, tol_abs, tol_rel):
            issues.append(f"[내용] {label}: 불일치 (좌={lhs:,} 우={rhs:,})  tol_abs={tol_abs}, tol_rel={tol_rel}")
    # 2
    assert_eq(I("12.31(전기말)_자본총계"), I("1.1(당기초)_자본총계"),
              "전기말=당기초(자본총계)", "12.31(전기말)_자본총계", "1.1(당기초)_자본총계")
    # 3
    assert_eq(I("자산총계"), (I("부채총계") or 0) + (I("자본총계") or 0),
              "자산=부채+자본", "자산총계", "부채총계+자본총계")
    # 5
    assert_eq(I("매출총이익"), (I("매출액") or 0) - (I("매출원가") or 0),
              "매출총이익=매출액-매출원가", "매출총이익", "매출액-매출원가")
    # 6
    sga = I("판매비와관리비") if I("판매비와관리비") is not None else I("매출총이익_판매비와관리비")
    if sga is None:
        issues.append("[내용] 판매비와관리비 값을 찾을 수 없습니다. ('판매비와관리비' 또는 '매출총이익_판매비와관리비')")
    else:
        assert_eq(I("영업이익"), (I("매출총이익") or 0) - sga,
                  "영업이익=매출총이익-판관비", "영업이익", "매출총이익-판관비")
    # 7
    nonop_income = (I("영업이익_기타수익") or 0) + (I("영업이익_금융수익") or 0)
    nonop_exp   = (I("영업이익_기타비용") or 0) + (I("영업이익_금융비용") or 0)
    assert_eq(I("법인세비용차감전순이익"), (I("영업이익") or 0) + nonop_income - nonop_exp,
              "법인세차감전순이익=영업이익+영업외수익-영업외비용",
              "법인세비용차감전순이익", "영업이익+영업외수익-영업외비용")
    # 8
    tax_exp_key = "법인세비용" if I("법인세비용") is not None else "법인세비용차감전순이익_법인세비용"
    assert_eq(I("당기순이익"), (I("법인세비용차감전순이익") or 0) - (I(tax_exp_key) or 0),
              "당기순이익=법인세차감전순이익-법인세비용", "당기순이익", f"법인세비용차감전순이익-{tax_exp_key}")
    # 9~10
    cf_sum = (I("영업활동현금흐름") or 0) + (I("투자활동현금흐름") or 0) + (I("재무활동현금흐름") or 0)
    assert_eq(I("현금및현금성자산의감소(Ⅰ+Ⅱ+Ⅲ)"), cf_sum,
              "CF합계=증감액", "현금및현금성자산의감소(Ⅰ+Ⅱ+Ⅲ)", "영업+투자+재무")
    assert_eq((I("기초의현금및현금성자산") or 0) + cf_sum, I("기말의현금및현금성자산"),
              "기초+흐름=기말현금", "기초+흐름", "기말")
    # 11~12
    assert_eq(I("자산총계"), (I("유동자산") or 0) + (I("비유동자산") or 0),
              "유동자산+비유동자산=자산총계", "유동+비유동", "자산총계")
    assert_eq(I("부채총계"), (I("유동부채") or 0) + (I("비유동부채") or 0),
              "유동부채+비유동부채=부채총계", "유동+비유동", "부채총계")
    # 15
    assert_eq(I("기말의현금및현금성자산"), I("유동자산_현금및현금성자산"),
              "CF기말=BS현금및현금성자산", "기말의현금및현금성자산", "유동자산_현금및현금성자산")
    # 18~19
    assert_eq(I("12.31(전기말)_이익잉여금"), I("1.1(당기초)_이익잉여금"),
              "전기말=당기초(이익잉여금)", "12.31(전기말)_이익잉여금", "1.1(당기초)_이익잉여금")
    # 20
    comp_sum = 0.0
    for k in json_obj.keys():
        if k.startswith("총포괄손익_") and k.endswith("_자본총계"):
            comp_sum += I(k) or 0.0
    owners_sum = 0.0
    for k in json_obj.keys():
        if k.startswith("자본에직접인식된주주와의거래_") and k.endswith("_자본총계"):
            owners_sum += I(k) or 0.0
    lhs = (I("1.1(전기초)_자본총계") or 0) + comp_sum + owners_sum
    rhs = I("12.31(당기말)_자본총계")
    assert_eq(lhs, rhs, "자본변동 연결(총계)", "전기초+총포괄손익+주주거래", "당기말 자본총계")
    # 22
    for k in NUMBER_KEYS_LIKELY_POSITIVE:
        v = I(k)
        if v is not None and v < 0 and k not in ALLOW_NEGATIVE_KEYS:
            issues.append(f"[내용] 음수가 나오면 안 되는 항목 음수 감지: {k}={v:,}")
    # 23
    for k in ESSENTIAL_KEYS:
        if json_obj.get(k, None) in (None, ""):
            issues.append(f"[내용] 핵심 항목 공란: {k}")
    return issues


def validate_file(path: Path, tol_abs=TOL_ABS_DEFAULT, tol_rel=TOL_REL_DEFAULT) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    objs = loaded if isinstance(loaded, list) else [loaded]
    all_issues: List[str] = []
    for idx, obj in enumerate(objs):
        if not isinstance(obj, dict):
            all_issues.append(f"[item{idx}] 객체가 dict가 아님: {type(obj)}")
            continue
        issues: List[str] = []
        issues += check_structural(obj)
        issues += check_format(obj)
        issues += check_content(obj, tol_abs=tol_abs, tol_rel=tol_rel)
        all_issues.extend([f"[item{idx}] " + it for it in issues])
    status = "PASS" if len(all_issues) == 0 else "FAIL"
    return {"file": str(path), "status": status, "issues": all_issues}
def scan_path(input_path: str, tol_abs=TOL_ABS_DEFAULT, tol_rel=TOL_REL_DEFAULT) -> List[Dict[str, Any]]:
    p = Path(input_path)
    targets: List[Path] = []
    if p.is_file():
        targets = [p]
    else:
        targets = sorted([x for x in p.rglob("*.json") if x.is_file()])
    reports = []
    for t in targets:
        try:
            reports.append(validate_file(t, tol_abs=tol_abs, tol_rel=tol_rel))
        except Exception as e:
            reports.append({"file": str(t), "status": "ERROR", "issues": [f"[런타임] {e}"]})
    return reports

def main():
    ap = argparse.ArgumentParser(description="재무제표 JSON 정합성 검사기")
    ap.add_argument("input", help="검사 대상 파일 또는 디렉터리 경로")
    ap.add_argument("--tol_abs", type=float, default=TOL_ABS_DEFAULT, help="절대 오차 허용치 (기본 1.0)")
    ap.add_argument("--tol_rel", type=float, default=TOL_REL_DEFAULT, help="상대 오차 허용치 (기본 1e-4 = 0.01%)")
    args = ap.parse_args()
    reports = scan_path(args.input, tol_abs=args.tol_abs, tol_rel=args.tol_rel)
    total = len(reports)
    fails = sum(r["status"] != "PASS" for r in reports)
    print(f"검사 대상: {total}개, FAIL: {fails}개, PASS: {total - fails}개")
    for r in reports:
        print("="*80)
        print(f"[{r['status']}] {r['file']}")
        for i, msg in enumerate(r["issues"], 1):
            print(f"  {i:02d}. {msg}")

if __name__ == "__main__":
    main()
