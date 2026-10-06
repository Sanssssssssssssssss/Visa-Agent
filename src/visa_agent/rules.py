"""Versioned material-readiness checks, not an immigration eligibility decision.

Every non-mechanical question remains in the final adviser review checklist.
New unsupported branches must return unknown/human, never silently pass.
"""

from datetime import date
from decimal import Decimal
import hashlib
from pathlib import Path

from .evidence import Evidence, comparable_value, normalized
from .types import Case, Check, Route, Status

SOURCES = {
    "visitor": "https://www.gov.uk/government/publications/visitor-visa-guide-to-supporting-documents/guide-to-supporting-documents-visiting-the-uk",
    "student": "https://www.gov.uk/student-visa/documents-you-must-provide",
    "student_money": "https://www.gov.uk/student-visa/money",
    "finance": "https://www.gov.uk/guidance/financial-evidence-for-student-and-child-student-route-applicants",
    "worker": "https://www.gov.uk/skilled-worker-visa/documents-you-must-provide",
    "worker_money": "https://www.gov.uk/skilled-worker-visa/how-much-it-costs",
    "english": "https://www.gov.uk/skilled-worker-visa/knowledge-of-english",
    "tb": "https://www.gov.uk/tb-test-visa",
    "scope": "project:adult-outside-uk-material-preparation-v1",
}
CHECKED_AT = "2026-10-07"
RULE_VERSION = "2026-10-07-" + hashlib.sha256(b"".join(
    Path(__file__).with_name(name).read_bytes()
    for name in ("rules.py", "intake.py", "intake_schema.py", "evidence.py", "documents.py")
)).hexdigest()[:12]

# Freeze the published rates rather than fetching policy during a customer conversation.
STUDENT_MONTHLY = {"london": Decimal("1529"), "outside_london": Decimal("1171")}
DIFFERENTIAL = {"China", "Japan", "Singapore", "United States", "Canada", "Australia"}
# Only these nationality/residence branches are implemented in v1. Others require review.
SUPPORTED_COUNTRIES = DIFFERENTIAL | {"India"}
FINAL_REVIEW = [
    "核对原件真实性、申请人与材料归属及翻译资质。",
    "确认路线资格、适用豁免及规则更新；本程序不作签证批准判断。",
    "Visitor：评估访问目的、资金来源及回国安排是否充分。",
    "Student：核对 CAS、课程/ATAS 和资金证明适用条件。",
    "Skilled Worker：核对担保资格、职业代码、薪资门槛和英语证据资质。",
]

SOP_CONTEXT = {
    "common": "Adult main applicant outside UK, no dependants or refusal explanation. Confirm route, identity, nationality, dates and funding. Non-English/Welsh evidence needs a complete verified translation. Unsupported circumstances go to an adviser. Unknown is never pass.",
    "visitor": "Routine employed self-funded visitor: travel purpose, dates, return ties and affordable trip supported by identity, work and financial evidence. No universal bank-balance threshold. Adviser judges sufficiency.",
    "student": "CAS information; tuition plus up to 9 months of maintenance (London GBP 1529/month, elsewhere GBP 1171/month). If financial documents required: 28 consecutive days, period end within 31 days of application. Differential evidence does not remove the financial condition. Conditional TB, ATAS and translations.",
    "skilled_worker": "CoS information, conditional English evidence (new application B2), TB and translations. Certified sponsor maintenance can replace funds submission; otherwise GBP 1270 held for 28 days ending within 31 days. Occupation other than 2134 and salary/eligibility judgments need adviser review.",
}


def evaluate(case: Case) -> list[Check]:
    e = Evidence(case)
    checks: list[Check] = []
    if case.extraction_issues:
        checks.append(Check(id="extraction_review", status="unknown", human=True,
                            source="project:source-grounding", message="部分字段无法核对来源，请顾问检查提取结果。"))

    def add(id, status, message, source="scope", *, human=False, keys=()):
        ids = [f.id for key in keys for f in e.facts(key)]
        checks.append(Check(id=id, status=status, message=message, source=SOURCES[source],
                            human=human, evidence=ids))

    def need(key, message, source="scope", kinds=None):
        value = e.get(key, kinds)
        add(key, "pass" if value is not None else "unknown", message, source, keys=(key,))
        return value

    route = e.get("route")
    case.route = Route(route) if route in set(Route) else None
    add("route", "pass" if case.route else "unknown", "请说明来英国的主要目的，以确认签证路线。", keys=("route",))
    need("applicant_name", "请提供与身份证件一致的申请人姓名。")
    for key, wanted, message in [
        ("application_location", "outside_uk", "请确认在英国境外申请；境内申请需要顾问处理。"),
        ("dependants", "false", "请确认是否有随行家属；家属申请需要顾问处理。"),
        ("previous_refusal", "false", "请说明是否有拒签记录；相关解释需要顾问处理。"),
    ]:
        value = e.get(key)
        add(key, "unknown" if value is None else "pass" if value == wanted else "fail",
            message, human=value is not None and value != wanted, keys=(key,))
    age = e.number("age")
    add("adult", "unknown" if age is None else "pass" if age >= 18 else "fail",
        "请确认年龄；未成年人材料由顾问处理。", human=age is not None and age < 18, keys=("age",))
    nationality = need("nationality", "请提供国籍，以判断材料和豁免条件。")
    if nationality is not None and nationality not in SUPPORTED_COUNTRIES:
        add("country_scope", "unknown", "该国籍的规则分支尚未覆盖，请顾问确认。", human=True)
    app_date = need("application_date", "请提供计划申请日期（YYYY-MM-DD），用于材料时效检查。")

    # Conflicts are never resolved by last-write-wins, including changed funding assertions.
    for key in sorted({f.key for f in case.facts if f.active}):
        if len({normalized(comparable_value(key, f.value)) for f in e.facts(key)}) > 1:
            add(f"conflict:{key}", "fail", f"{key} 存在多个不一致的值，请核对来源。",
                human=True, keys=(key,))
    for doc in case.documents:
        if doc.rejected or doc.kind == "intake":
            continue
        from .documents import content_role_for
        doc.content_role = content_role_for(doc)
        if doc.content_role == "unrelated" or (doc.content_role == "sample" and not case.test_mode):
            add(f"{doc.content_role}:{doc.id}", "fail", "此文件不能作为本人的申请证据，请补充实际材料。")
            continue
        if doc.content_role in {"self_report", "uncertain"}:
            add(f"{doc.content_role}:{doc.id}", "unknown",
                "附件是自填信息或证明类型尚未确认，不能替代护照、银行或签发机构的材料。请提供相应原件的清晰副本。")
            if doc.content_role == "self_report":
                continue
        if doc.problems:
            add(f"read:{doc.id}", "fail", f"{doc.name} 无法可靠读取，请上传清晰完整文件。")
        if any(p.startswith("Declared pagination incomplete") for p in doc.problems):
            add(f"pagination:{doc.id}", "unknown",
                f"{doc.name} 声明还有其他页。请将同一份文件的完整页面按顺序合成 PDF 上传，或交顾问确认页面归属。",
                human=True)
        if any(p.startswith("Model context capacity exceeded") for p in doc.problems):
            add(f"context:{doc.id}", "unknown", f"{doc.name} 超出本轮完整阅读容量，请顾问复核全文。", human=True)
        if doc.kind == "unknown":
            add(f"kind:{doc.id}", "unknown", f"请确认 {doc.name} 是什么材料。")
        if doc.language not in {"en", "cy"}:
            translations = [d for d in case.documents if d.kind == "translation" and e.admissible(d)]
            translated = False
            for td in translations:
                facts = {f.key: f.value for f in case.facts
                         if f.active and f.source_id == td.id and not td.problems
                         and (f.confidence == "high" or f.confirmed_by)}
                translated |= (facts.get("translation_for") in {doc.name, doc.sha256, doc.id}
                               and all(facts.get(k) for k in ("translator_name", "translator_contact",
                                                             "translation_date"))
                               and facts.get("translation_accurate") == "true"
                               and facts.get("translator_signed") == "true")
            add(f"translation:{doc.id}", "pass" if translated else "unknown",
                f"请为 {doc.name} 提供完整译文及译者声明、日期、签名和联系方式。", "visitor")

    if case.route is None:
        return checks
    if case.application_forms:
        from .intake import information_checks
        checks.extend(information_checks(case))
    source = "worker" if case.route == Route.WORKER else case.route.value
    need("passport_name", "请上传有效护照/旅行证件的个人信息页。", source, {"passport"})
    need("passport_number", "证件号码缺失或不可读，请补充。", source, {"passport"})
    expiry = e.day("passport_expiry", {"passport"})
    reference = e.day("travel_end") if case.route == Route.VISITOR else (
        e.day("travel_start") or e.day("application_date"))
    add("passport_valid", "unknown" if not expiry or not reference else (
        "pass" if expiry >= reference else "fail"),
        "请核对护照有效期及行程日期；证件必须在相应旅行期间有效。", source,
        keys=("passport_expiry",))
    identity = e.get("passport_name", {"passport"})
    name_keys = ("applicant_name", "bank_holder", "employment_name", "cas_name", "cos_name", "tb_name")
    for key in name_keys:
        other = e.get(key)
        if identity and other:
            matches = normalized(identity) == normalized(other)
            add(f"name:{key}", "pass" if matches else "fail",
                f"{key} 与证件姓名不一致时需顾问确认，不能用模糊匹配自动放行。", source,
                human=not matches, keys=("passport_name", key))

    funding = need("funding", "请说明资金来源：self（本人）或 employer（雇主）。", source)
    if case.route in {Route.VISITOR, Route.STUDENT} and funding not in {None, "self"}:
        add("funding_scope", "unknown", "第三方资助、贷款等分支需要顾问核对。", source, human=True)

    if case.route == Route.VISITOR:
        for key, message in [
            ("purpose", "请说明具体访问目的。"), ("travel_start", "请提供预计入境日期。"),
            ("travel_end", "请提供预计离境日期。"), ("return_reason", "请说明回国安排及相关联系。"),
            ("trip_budget", "请说明预计总行程费用（GBP），用于对照资金。"),
        ]:
            need(key, message, "visitor")
        start, end = e.day("travel_start"), e.day("travel_end")
        if start and end:
            add("trip_dates", "pass" if 0 < (end - start).days <= 180 else "fail",
                "请核对入境与离境日期；本演示覆盖不超过 180 天的普通访问。", human=True)
        need("employer", "本演示的在职自费访客分支需要工作支持材料；其他情况请顾问处理。",
             "scope", {"employment"})
        _finance(e, checks, e.number("trip_budget"), period=False, source="visitor")

    if case.route == Route.STUDENT:
        for key in ("cas_reference", "cas_name", "tuition_due", "study_months", "study_location",
                    "english_confirmed", "atas_required"):
            need(key, f"请补充 CAS/学校材料中的 {key} 信息。", "student", {"cas"})
        months, tuition = e.number("study_months", {"cas"}), e.number("tuition_due", {"cas"})
        location = e.get("study_location", {"cas"})
        amount = None
        if months is not None and tuition is not None and location in STUDENT_MONTHLY:
            if months > 0 and months == months.to_integral_value():
                amount = tuition + min(months, Decimal(9)) * STUDENT_MONTHLY[location]
            else:
                add("course_months", "fail", "课程月数必须是计入不足整月后的正整数。", "student_money")
        elif location is not None and location not in STUDENT_MONTHLY:
            add("study_location", "unknown", "请确认课程在 london 或 outside_london。", "student_money")
        requested = e.get("financial_evidence_requested")
        if nationality in DIFFERENTIAL:
            need("financial_evidence_requested", "UKVI 是否已要求提供财务证明？", "student_money")
        # Differential evidence concerns submission, not the underlying financial condition.
        if nationality in DIFFERENTIAL and requested == "false":
            add("finance_submission", "not_applicable",
                "当前按差异化材料要求处理；仍须备妥资金，UKVI 后续可能要求证明。", "student_money",
                keys=("nationality", "financial_evidence_requested"))
            if any(d.kind in {"bank_statement", "bank_letter"} and not d.rejected for d in case.documents):
                _finance(e, checks, amount, period=True, source="student_money")
        else:
            _finance(e, checks, amount, period=True, source="student_money")
        atas = e.get("atas_required", {"cas"})
        if e.get("english_confirmed", {"cas"}) == "false":
            add("student_english", "unknown", "学校尚未确认英语要求，请顾问核对证明方式。", "student", human=True)
        if atas == "true":
            need("atas_reference", "课程要求 ATAS，请提供证明。", "student", {"atas"})
        elif atas == "false":
            add("atas", "not_applicable", "CAS 表示无需 ATAS，顾问复核适用性。", "student")

    if case.route == Route.WORKER:
        for key in ("cos_reference", "cos_name", "sponsor_name", "sponsor_licence", "job_title",
                    "occupation_code", "salary", "maintenance_certified"):
            need(key, f"请补充 CoS/雇主材料中的 {key} 信息。", "worker", {"cos"})
        occupation = e.get("occupation_code", {"cos"})
        if occupation and occupation != "2134":
            add("occupation_scope", "unknown", "当前自动分支仅覆盖软件开发职业 2134；其他职业转顾问。",
                "worker", human=True)
        level = None
        if nationality in {"Australia", "Canada", "United States"}:
            add("english_level", "not_applicable", "按已覆盖的国籍分支处理英语证明豁免。", "english")
        else:
            level = need("english_level", "请提供英语证明；其他豁免方式转顾问确认。", "english", {"english"})
        if level and level not in {"B2", "C1", "C2"}:
            add("english_level_valid", "fail", "本演示的新申请分支要求至少 B2；豁免由顾问核对。", "english")
        maintenance = e.get("maintenance_certified", {"cos"})
        if maintenance == "true":
            add("finance_submission", "not_applicable", "CoS 记录雇主承担维持费用，顾问核对担保承诺。", "worker_money",
                keys=("maintenance_certified",))
        elif maintenance == "false":
            _finance(e, checks, Decimal("1270"), period=True, source="worker_money")
    if case.route in {Route.STUDENT, Route.WORKER}:
        residence = need("residence_country", "请说明近半年的居住国家，用于 TB 条件判断。", "tb")
        duration = e.number("residence_months")
        stay = e.number("stay_months")
        if residence is None or duration is None or stay is None:
            add("tb_applicability", "unknown", "请提供居住月数和计划在英国停留月数。", "tb")
        elif residence not in {"China", "India", "Japan", "Singapore"} or duration < 6:
            add("tb_applicability", "unknown", "该居住历史需要顾问核对 TB 条件。", "tb", human=True)
        elif residence in {"China", "India"} and stay >= 6:
            need("tb_name", "请提供获认可机构的 TB 证明。", "tb", {"tb"})
            expiry_tb = e.day("tb_expiry", {"tb"})
            clear = e.get("tb_clear", {"tb"})
            reference_tb = e.day("travel_start") or (date.fromisoformat(app_date) if app_date else None)
            ok = expiry_tb and reference_tb and expiry_tb >= reference_tb and clear == "true"
            add("tb_valid", "pass" if ok else "unknown", "请核对 TB 结果及有效期。", "tb")
        else:
            add("tb_applicability", "not_applicable", "当前已覆盖的居住和停留条件不要求 TB。", "tb")
    return checks


def _finance(e: Evidence, checks: list[Check], required: Decimal | None, *, period: bool, source: str):
    kinds = {"bank_statement", "bank_letter"}
    keys = ("bank_name", "bank_holder", "bank_currency", "bank_minimum", "bank_start", "bank_end")
    # All required fields must come from ONE admissible document. Substitution cannot
    # bypass field checks or assemble a fictitious complete statement from unrelated files.
    documents = [d for d in e.case.documents if d.kind in kinds and e.admissible(d)]
    reasons = []
    for doc in documents:
        values = {key: {f.value for f in e.facts(key, kinds) if f.source_id == doc.id} for key in keys}
        if not all(len(v) == 1 for v in values.values()):
            reasons.append("证明缺少银行、持有人、币种、最低余额或覆盖日期")
            continue
        data = {k: next(iter(v)) for k, v in values.items()}
        if data["bank_currency"] != "GBP":
            reasons.append("外币转换未自动实现，需要顾问确认")
            continue
        if required is None:
            reasons.append("尚缺所需资金金额的计算条件")
            continue
        if Decimal(data["bank_minimum"]) < required:
            reasons.append(f"覆盖期间最低余额低于所需 GBP {required}")
            continue
        start, end = date.fromisoformat(data["bank_start"]), date.fromisoformat(data["bank_end"])
        application = e.day("application_date")
        if end < start or not application or end > application:
            reasons.append("证明日期或申请日期不完整/不合理")
            continue
        if period and ((end - start).days + 1 < 28 or (application - end).days > 31):
            reasons.append("未覆盖连续 28 天，或期末距申请日超过 31 天")
            continue
        checks.append(Check(id="finance", status="pass", source=SOURCES[source],
                            message=f"已核对资金证明字段；所需金额 GBP {required}。",
                            evidence=[f.id for k in keys for f in e.facts(k, kinds)
                                      if f.source_id == doc.id]))
        return
    checks.append(Check(id="finance", status="fail" if documents else "unknown",
                        source=SOURCES[source], human=any("外币" in r for r in reasons),
                        message="请补充可核对的资金证明。" + "；".join(sorted(set(reasons))),
                        evidence=[f.id for key in (*keys, "application_date", "trip_budget", "tuition_due", "study_months", "study_location")
                                  for f in e.facts(key)]))


def status_for(checks: list[Check]) -> Status:
    blockers = [c for c in checks if c.status in {"fail", "unknown"}]
    if any(c.human for c in blockers):
        return Status.NEEDS_HUMAN
    return Status.WAIT_USER if blockers else Status.READY


def reply_for(case: Case, **kwargs) -> str:
    from .conversation import reply_for as compose_reply
    return compose_reply(case, **kwargs)
