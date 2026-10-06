"""Versioned preparation worksheet; it is not the UKVI online application form."""
from dataclasses import dataclass

VERSION = "application-info-2026-10-07-v1"
VISITOR = "https://www.gov.uk/standard-visitor/apply-standard-visitor-visa"
STUDENT = "https://www.gov.uk/student-visa/documents-you-must-provide"
WORKER = "https://www.gov.uk/skilled-worker-visa/documents-you-must-provide"
PREPARATION = "project:application-preparation"  # Operational questions, not a universal legal mandate.


@dataclass(frozen=True)
class Question:
    key: str
    label: str
    hint: str = "请如实填写 / Answer accurately"
    kind: str = "text"
    source: str = PREPARATION
    when: tuple[str, tuple[str, ...]] | None = None


COMMON = [
    Question("applicant_name", "护照姓名 / Full name", "按护照英文拼写 / As on passport"),
    Question("date_of_birth", "出生日期 / Date of birth", "YYYY-MM-DD", "date"),
    Question("birth_place", "出生城市 / Place of birth"),
    Question("birth_country", "出生国家 / Country of birth"),
    Question("other_names", "曾用名 / Other names", "无则填 none / Enter none if none"),
    Question("nationality", "国籍 / Nationality", "例如 China / e.g. China"),
    Question("email_address", "联系邮箱 / Email", "仅用于联系，不改变收件线程归属 / Does not change thread ownership", "email"),
    Question("phone_number", "联系电话 / Phone", "含国家区号，例如 +8613800000000 / Include country code", "phone"),
    Question("home_address", "现居住地址 / Home address", source=VISITOR),
    Question("home_since", "何时入住 / Living there since", "YYYY-MM-DD", "date", VISITOR),
    Question("application_location", "申请地点 / Application location", "outside_uk（英国境外）或 inside_uk（英国境内）", "location"),
    Question("application_date", "预计申请日 / Planned application date", "YYYY-MM-DD", "date"),
    Question("passport_number", "护照号码 / Passport number", "自填不能代替护照原件 / Self-report does not replace the passport"),
    Question("passport_expiry", "护照到期日 / Passport expiry", "YYYY-MM-DD；仍需证件 / Passport still required", "date"),
    Question("marital_status", "婚姻状况 / Marital status", "single / married / civil_partner / unmarried_partner / divorced / widowed", "marital"),
    Question("partner_details", "伴侣信息 / Partner details", "姓名、生日、护照号 / Name, DOB, passport number", source=VISITOR,
             when=("marital_status", ("married", "civil_partner", "unmarried_partner"))),
    Question("dependants", "是否有随行家属 / Dependants", "yes / no（是/否）；家属分支未覆盖", "bool"),
    Question("previous_refusal", "是否有拒签记录 / Previous refusals", "yes / no（是/否）", "bool"),
    Question("refusal_details", "拒签说明 / Refusal details", "日期、国家、原因 / Date, country, reason", when=("previous_refusal", ("true",))),
    Question("travel_history_10y", "近十年旅行记录 / Travel history", "国家、入出境日期、目的；没有填 none / Country, dates, purpose, or none", source=VISITOR),
    Question("offences", "刑事、民事或移民违法记录 / Offences", "yes / no（是/否）", "bool", VISITOR),
    Question("offence_details", "记录详情 / Offence details", "说明日期和情况 / Dates and circumstances", source=VISITOR, when=("offences", ("true",))),
    Question("residence_country", "近期居住国家 / Recent residence country", "用于结核检查条件 / Used for TB conditions"),
    Question("residence_months", "已居住月数 / Months of residence", "填数字 / Number", "number"),
    Question("travel_start", "预计入境日 / Intended arrival", "YYYY-MM-DD", "date"),
    Question("stay_months", "计划停留月数 / Intended months in UK", "填数字 / Number", "number"),
    Question("funding", "费用来源 / Funding", "self（本人）/ employer（雇主）；其他资助请说明", "funding"),
    Question("sponsor_contact", "资助人联系信息 / Sponsor contact", "姓名和地址 / Name and address", source=VISITOR, when=("funding", ("employer", "other"))),
]
BY_ROUTE = {
    "visitor": [
        Question("purpose", "访问目的 / Purpose", "说明旅游、探亲等具体安排 / Describe the visit", source=VISITOR),
        Question("travel_end", "预计离境日 / Departure", "YYYY-MM-DD", "date", VISITOR),
        Question("trip_budget", "行程预算 GBP / Trip budget GBP", "数字 / Number", "number", VISITOR),
        Question("uk_accommodation", "英国住宿安排 / UK accommodation", "地址和住宿安排，不要求先付款预订 / Intended address and arrangements; no paid booking required", source=VISITOR),
        Question("return_reason", "旅行后的安排 / Plans after the visit", source=VISITOR),
        Question("employment_status", "工作情况 / Employment status", "employed / self_employed / student / unemployed / retired", "employment", VISITOR),
        Question("employer_contact", "雇主地址与电话 / Employer contact", source=VISITOR, when=("employment_status", ("employed",))),
        Question("annual_income", "年收入 / Annual income", "数字；无收入填 0 / Number, 0 if no income", "number", VISITOR),
        Question("income_currency", "收入币种 / Income currency", "GBP / CNY / USD 等三位币种 / Three-letter code", "currency", VISITOR),
        Question("parent_one", "父/母一信息 / Parent 1", "姓名和出生日期；不详请填 unknown 并说明 / Name, DOB or explain if unknown", source=VISITOR),
        Question("parent_two", "父/母二信息 / Parent 2", "姓名和出生日期；不详请填 unknown 并说明 / Name, DOB or explain if unknown", source=VISITOR),
        Question("uk_family", "是否有英国亲属 / UK family", "yes / no（是/否）", "bool", VISITOR),
        Question("uk_family_details", "英国亲属信息 / UK family details", "姓名、地址、护照号 / Name, address, passport number", source=VISITOR, when=("uk_family", ("true",))),
    ],
    "student": [
        Question("financial_evidence_requested", "UKVI 是否已要求提交资金证明 / Has UKVI requested financial evidence", "yes / no（是/否）", "bool", STUDENT),
        Question("cas_reference", "CAS 编号 / CAS reference", "仍需学校提供的 CAS 信息 / School-issued details also needed", source=STUDENT),
        Question("school_name", "学校名称 / School", source=STUDENT),
        Question("course_name", "课程名称 / Course", source=STUDENT),
        Question("course_start", "开课日期 / Course start", "YYYY-MM-DD", "date", STUDENT),
        Question("course_end", "课程结束日 / Course end", "YYYY-MM-DD", "date", STUDENT),
        Question("sponsored_last12m", "过去12个月学费和生活费是否受官方资助 / Recent official sponsorship", "yes / no；政府或国际资助机构 / Government or international agency", "bool", STUDENT),
        Question("sponsor_details", "资助详情 / Sponsorship details", "机构、资助时间和范围 / Organisation, dates, coverage", source=STUDENT, when=("sponsored_last12m", ("true",))),
    ],
    "skilled_worker": [
        Question("cos_reference", "CoS 编号 / CoS reference", "仍需雇主提供的担保信息 / Employer-issued information also needed", source=WORKER),
        Question("sponsor_name", "担保雇主名称 / Sponsor name", source=WORKER),
        Question("sponsor_licence", "雇主担保执照号 / Sponsor licence", source=WORKER),
        Question("job_title", "岗位名称 / Job title", source=WORKER),
        Question("occupation_code", "职业代码 / Occupation code", source=WORKER),
        Question("salary", "年薪 GBP / Annual salary GBP", "数字 / Number", "number", WORKER),
        Question("job_start", "工作开始日 / Job start", "YYYY-MM-DD", "date", WORKER),
        Question("work_address", "工作地址 / Work address", source=WORKER),
        Question("worker_atas_required", "雇主是否说明需要 ATAS / Employer requires ATAS", "yes / no / 不清楚留空 / Leave blank if unknown", "bool", WORKER),
    ],
}
ALL_QUESTIONS = {q.key: q for q in COMMON + [q for values in BY_ROUTE.values() for q in values]}
NEW_KEYS = set(ALL_QUESTIONS) | {"sponsor_consent_confirmed"}


def questions(route):
    return COMMON + BY_ROUTE.get(route, [])
