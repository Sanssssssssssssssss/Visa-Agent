"""Customer language and progress, built from checked state rather than model claims.

The model selects priorities after checks. This response catalogue owns factual
claims, official links and completion wording; it cannot override a check.
"""

import re

from .types import Status

APPLICATION_GUIDE = "https://www.gov.uk/apply-to-come-to-the-uk"
VISA_CHECK = "https://www.gov.uk/check-uk-visa"
SUITABILITY_GUIDE = "https://www.gov.uk/guidance/immigration-rules/immigration-rules-part-suitability"
ROUTE_GUIDES = {
    "visitor": "https://www.gov.uk/standard-visitor",
    "student": "https://www.gov.uk/student-visa/documents-you-must-provide",
    "skilled_worker": "https://www.gov.uk/skilled-worker-visa/documents-you-must-provide",
}


def language_for(text, previous="zh"):
    if re.search(r"(?:reply|respond|answer|speak).*\bEnglish\b|用英文|用英语", text, re.I):
        return "en"
    if re.search(r"(?:reply|respond|answer|speak).*(?:Chinese|Mandarin)|用中文|用汉语", text, re.I):
        return "zh"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    return "en" if len(re.findall(r"\b[A-Za-z]+\b", text)) >= 3 else previous


def material_progress(case):
    """Group real checks into material categories; unanswered conditions stay pending.

    This denominator is provisional: a new condition can add a category. Unknown
    route and failed turns never display 100 percent readiness.
    """
    checks = {c.id: c for c in case.checks}
    groups = {
        "identity": ("护照", "Passport", ["passport_name", "passport_number", "passport_valid", "name:applicant_name"]),
        "funds": ("资金证明", "Funding evidence", ["finance", "finance_submission", "funding_scope", "name:bank_holder"]),
        "work": ("工作证明", "Employment", ["employer", "name:employment_name"]),
        "school": ("学校材料", "School evidence", ["cas_reference", "cas_name", "tuition_due", "study_months",
                                              "study_location", "english_confirmed", "atas_required", "student_english", "name:cas_name"]),
        "sponsor": ("雇主担保", "Sponsorship", ["cos_reference", "cos_name", "sponsor_name", "sponsor_licence",
                                            "job_title", "occupation_code", "salary", "maintenance_certified", "name:cos_name"]),
        "english": ("英语证明", "English evidence", ["english_level", "english_level_valid"]),
        "tb": ("结核检查", "TB evidence", ["tb_applicability", "tb_name", "tb_valid"]),
        "atas": ("学术技术审核", "ATAS", ["atas_reference", "atas"]),
        "translation": ("翻译件", "Translations", [k for k in checks if k.startswith("translation:")]),
    }
    items = []
    for group, (zh, en, keys) in groups.items():
        rows = [checks[k] for k in keys if k in checks]
        if not rows or all(c.status == "not_applicable" for c in rows):
            continue
        ok = all(c.status in {"pass", "not_applicable"} for c in rows) and not case.pending_error
        items.append({"id": group, "label": zh if case.language == "zh" else en,
                      "status": "checked" if ok else "pending"})
    return {"checked": sum(i["status"] == "checked" for i in items), "total": len(items),
            "items": items, "provisional": True, "reviewed": case.approval is not None,
            "automatic": case.automatic_completion is not None, "hitl_enabled": case.hitl_enabled,
            "route_known": case.route is not None, "turn_failed": bool(case.pending_error)}


def progress_text(case):
    p = material_progress(case)
    zh = case.language == "zh"
    complete = int(10 * p["checked"] / p["total"]) if p["total"] and p["route_known"] else 0
    bar = "[" + "■" * complete + "□" * (10 - complete) + "]"
    if not p["route_known"]:
        return ("材料进度 " if zh else "Materials ") + bar + (
            " 清单待确认；先了解您的申请情况。" if zh else " Checklist pending; we need your circumstances first.")
    counts = (f"{p['checked']}/{p['total']} 项已核对" if zh else f"{p['checked']}/{p['total']} categories checked")
    review = ("人工复核已确认" if zh else "Adviser review confirmed") if p["reviewed"] else (
        "人工复核待完成" if zh else "Adviser review pending")
    if not case.hitl_enabled:
        review = ("自动完成 · 未经人工审核" if zh else "Automatically completed; no human review") if p["automatic"] else (
            "自动处理 · HITL 已关闭" if zh else "Automatic processing; HITL off")
    suffix = "清单会随申请情况更新。" if zh else "The checklist may change with your circumstances."
    return f"{'材料进度' if zh else 'Materials'} {bar} {counts} · {review}\n{suffix}"


def preparation_step(case):
    zh = case.language == "zh"
    if case.status == Status.COMPLETE:
        if not case.hitl_enabled:
            return "第 4 步：材料自动整理完成" if zh else "Step 4: document preparation completed automatically"
        return "第 4 步：材料包已确认" if zh else "Step 4: document pack confirmed"
    if case.status == Status.READY:
        if not case.hitl_enabled:
            return "第 4 步：等待模型交付决策" if zh else "Step 4: awaiting the model's delivery decision"
        return "第 4 步：请顾问复核材料包" if zh else "Step 4: adviser review of your pack"
    intake = {"route", "applicant_name", "application_location", "nationality", "adult", "dependants", "previous_refusal", "application_date"}
    if not case.checks or any(c.id in intake and c.status == "unknown" for c in case.checks):
        return "第 1 步：了解您的申请情况" if zh else "Step 1: understand your application"
    if any(c.id.startswith("passport") and c.status != "pass" for c in case.checks):
        return "第 2 步：核对护照个人信息页" if zh else "Step 2: check your passport details page"
    return "第 3 步：补齐支持材料和未确认信息" if zh else "Step 3: complete supporting evidence and missing details"


# Plain questions, including why we need the answer. The finite SOP remains in rules.py.
QUESTIONS = {
    "route": ("您去英国主要是旅游、读书还是工作？这决定需要准备哪些材料。", "Are you visiting, studying or working in the UK? This determines your checklist."),
    "applicant_name": ("请提供姓名，与护照上的拼写一致，方便核对材料是否属于您。", "What is your full name as shown on your passport? This helps us match your documents."),
    "application_location": ("您准备从哪个国家申请？如果已在英国，请说明现在持有什么签证。", "Which country will you apply from? If you are already in the UK, what visa do you hold?"),
    "nationality": ("您持哪个国家的护照？国籍会影响签证和材料要求。", "Which country's passport do you hold? Nationality affects visa and evidence requirements."),
    "dependants": ("是否有伴侣或孩子一起申请？他们可能需要单独准备材料。", "Will a partner or children apply with you? They may need separate applications and documents."),
    "previous_refusal": ("以前是否被拒签过？如有，顾问需要了解原因。", "Have you had a visa refusal before? If so, an adviser will need the reasons."),
    "adult": ("您今年多大？未满 18 岁的申请需要额外核对。", "How old are you? Applications for people under 18 need additional review."),
    "application_date": ("您打算哪一天提交申请？请用年-月-日填写，用于检查材料是否仍有效。", "When do you plan to submit your application (YYYY-MM-DD)? We use this to check document dates."),
    "funding": ("这次费用由您自己、雇主还是其他人承担？这决定资金证明怎么准备。", "Who will pay: you, your employer or someone else? This determines the funding evidence."),
    "purpose": ("这次来英国具体做什么？简单说说您的计划即可。", "What will you do during your visit? A brief explanation is enough to start."),
    "travel_start": ("您预计哪天到英国？用来核对行程和材料有效期。", "When do you expect to arrive in the UK? We use this to check your travel and document dates."),
    "travel_end": ("您预计哪天离开英国？暂未订票也可以先告诉我计划日期。", "When do you plan to leave the UK? A planned date is fine; you do not need to book a ticket now."),
    "return_reason": ("旅行结束后有什么回国安排，比如继续工作或学业？", "What are your plans after the visit, such as returning to work or study?"),
    "trip_budget": ("这次交通、住宿和日常开销一共预计多少英镑？估算即可。", "What is your estimated total trip cost in pounds, including travel, accommodation and daily spending?"),
    "employer": ("请提供说明您工作情况的材料，例如在职证明；如果目前没有工作，告诉我您的实际情况即可。", "Please provide evidence of your employment, such as an employer letter. If you are not employed, tell me your circumstances."),
    "financial_evidence_requested": ("英国签证部门是否明确要求您提交资金证明？即使暂时不要求提交，也需要满足资金条件。", "Has UKVI asked you to submit financial evidence? You still need to meet the funding conditions if submission is not required."),
    "residence_country": ("过去半年您主要住在哪个国家、住了多久？这关系到是否需要结核检查。", "Where have you lived during the last six months, and for how long? This affects TB testing requirements."),
    "tb_applicability": ("请告诉我近期居住国家、住了多久，以及计划在英国待多久，以判断是否需要结核检查。", "Please tell me your recent countries of residence, time spent there and planned UK stay so we can check TB requirements."),
}


def action_for(check, case):
    zh = case.language == "zh"
    family = check.id.split(":")[0]
    if family in {"sample", "unrelated", "read", "pagination", "context", "translation", "kind"}:
        affected = [d for d in case.documents if check.id.endswith(":" + d.id)]
        name = affected[0].name if affected else "这个文件" if zh else "this file"
        if family in {"sample", "unrelated"}:
            name = ("、" if zh else ", ").join(d.name for d in case.documents
                                               if not d.rejected and d.content_role == family)
        messages = {
            "sample": (f"{name} 是样例或测试材料，不能用于您的正式申请。请提供属于您本人的实际材料；我可以继续说明怎么准备。",
                       f"{name} is a sample or test document, so it cannot support your application. Please send your own evidence; I can help explain what to prepare."),
            "unrelated": (f"{name} 不是所需的申请证明。请上传与申请有关的护照、银行或学校/雇主材料，并说一下您想证明什么。",
                          f"{name} does not provide the evidence we need. Please send a relevant passport, bank, school or employer document and tell me what it should show."),
            "read": (f"{name} 的部分内容无法可靠读取。请上传文字清楚、四角完整的原图或原始 PDF；也可以请顾问对照原件确认。",
                     f"I cannot reliably read part of {name}. Please send a clear original photo showing all four corners, or the original PDF. An adviser can also compare it with the original."),
            "pagination": ("多页材料的页面归属还需核对。请把同一份文件的完整页面按顺序合并为 PDF，或请顾问确认这些页面属于同一份文件。",
                           "The pages of a multi-page document still need to be matched. Please combine all pages in order into one PDF, or ask an adviser to confirm they belong together."),
            "context": ("这份材料本轮未能完整阅读，需要顾问核对全文；已收到的文件会保留。", "We could not read this entire document in this turn. It is saved, but an adviser needs to review the full document."),
            "translation": (f"{name} 需要完整的英文或威尔士文译本，附译者的准确性声明、日期、签名和联系方式。", f"Please provide a complete English or Welsh translation of {name}, with the translator's accuracy statement, date, signature and contact details."),
            "kind": (f"我还不能确定 {name} 是什么证明。您希望用它证明哪项情况？", f"I cannot yet identify what {name} supports. What would you like this document to show?"),
        }
        if not case.hitl_enabled:
            messages.update({
                "read": (f"{name} 的部分内容无法可靠读取。请上传文字清楚、四角完整的原图或原始 PDF。",
                         f"I cannot reliably read part of {name}. Please send a clear original photo with all four corners, or the original PDF."),
                "pagination": ("页面归属还未确认。请把同一份文件的完整页面按顺序合并为 PDF。",
                               "The pages have not been matched. Please combine all pages of the same document in order into one PDF."),
                "context": ("本轮未能完整读取这份材料，请拆分后重新上传；现有文件已保留。",
                            "This document could not be read in full this turn. Please split it and upload again; the existing file is saved."),
            })
        return family, messages[family][0 if zh else 1]
    if not case.hitl_enabled and check.human:
        if family in {"conflict", "name"}:
            return "conflict", ("现有材料中的信息不一致，暂时不能自动确认。请说明哪份是当前资料并提供清晰来源；本版不会自动裁定冲突。" if zh else
                                "The evidence contains inconsistent details. Please identify the current information and provide a clear source; this version cannot automatically resolve conflicts.")
        return check.id, ("这一条件暂时无法自动确认，已保留具体原因。您可以补充清晰原件或更完整的信息。" if zh else
                          "This condition cannot currently be confirmed automatically; the reason is recorded. You can supply clearer originals or more complete information.")
    if family in {"conflict", "name"}:
        return "conflict", ("材料中的姓名或其他信息对不上，需要顾问对照来源核对。请说明是否涉及改名或材料更新，并保留两份原件。" if zh else
                            "Some names or details do not match across your evidence. An adviser needs to compare the sources. Please explain any name change or updated document and keep both originals.")
    if check.id.startswith("passport"):
        return "passport", ("请上传护照个人信息页，确保姓名、号码和有效期清晰可见，用于核对身份和有效期。" if zh else
                            "Please upload your passport's personal details page with the name, number and expiry clearly visible so we can check identity and validity.")
    if check.id in {"cas_reference", "cas_name", "tuition_due", "study_months", "study_location", "english_confirmed", "atas_required", "student_english"}:
        return "cas", ("请提供学校发的录取确认信息（CAS）及相关说明，包括姓名、课程、费用和英语要求；邮件或文件都可以，不必专门制作 PDF。" if zh else
                       "Please send your school's Confirmation of Acceptance for Studies (CAS) details and supporting information, including your name, course, fees and English requirements. An email or document is fine; no special PDF is needed.")
    if check.id in {"cos_reference", "cos_name", "sponsor_name", "sponsor_licence", "job_title", "occupation_code", "salary", "maintenance_certified"}:
        return "cos", ("请提供雇主发的工作担保信息（CoS），包含姓名、岗位、薪资，以及雇主是否承担生活费用的说明；CoS 是电子记录，不必是纸质证书。" if zh else
                       "Please send your employer's Certificate of Sponsorship (CoS) details: your name, job, salary and whether maintenance is certified. A CoS is an electronic record, not necessarily a paper certificate.")
    if check.id == "finance":
        reason = check.message
        if "28 天" in reason:
            return "finance", ("资金证明的时间条件还不满足：请提供连续 28 天的记录，且期末距计划申请日不超过 31 天。请保留完整页面。" if zh else
                               "The funding evidence does not yet meet the timing conditions. Please provide 28 consecutive days, ending no more than 31 days before your planned application, with all pages included.")
        if "最低余额低于" in reason:
            return "finance", ("材料显示覆盖期间的最低余额不足以满足当前计算金额，需要先由顾问核对资金安排。" if zh else "The lowest balance shown is below the amount currently calculated. An adviser needs to check your funding arrangements.")
        if "外币" in reason:
            return "finance", ("已收到外币资金证明，折算金额需要顾问核对。请保留原始币种和完整文件。" if zh else "Your funding evidence uses a foreign currency. An adviser needs to verify the conversion; please keep the original currency and complete document.")
        return "finance", ("请提供能看清持有人、银行、币种、余额及覆盖日期的资金证明，例如银行流水或银行信，方便核对费用是否有来源。" if zh else
                           "Please send funding evidence, such as a bank statement or bank letter, showing the account holder, bank, currency, balances and dates so we can check how costs will be covered.")
    if check.id in QUESTIONS:
        return check.id, QUESTIONS[check.id][0 if zh else 1]
    return check.id, (check.message if zh and not re.search(r"[a-z]+_[a-z]+", check.message) else
                     "这项材料或适用条件需要顾问进一步核对；您可以继续补充已有材料。" if zh else
                     "An adviser needs to check this evidence or eligibility condition. You can continue sending the documents you have.")


def reply_for(case, *, text="", intent="continue", received_count=None, guidance=None):
    zh = case.language == "zh"
    paragraphs = [preparation_step(case)]
    if guidance:
        if guidance.explanation != "continue":
            intent = guidance.explanation
        approaches = {
            "step_by_step": ("我们一次处理几项就好，不需要您先了解所有签证术语。", "We can handle a few things at a time; you do not need to know all the visa terms."),
            "explain_material": ("我会说明每项材料用来核对什么，您可以先提供手头已有的文件。", "I'll explain what each document helps us check. You can start with the files you already have."),
        }
        if guidance.approach in approaches:
            paragraphs.append(approaches[guidance.approach][0 if zh else 1])
    if case.test_mode:
        paragraphs.append("演示案件：使用测试材料，生成的材料包仅供测试。" if zh else "Demo case: test materials and any resulting pack are for testing only.")
    count = len([d for d in case.documents if not d.rejected]) if received_count is None else received_count
    if count:
        paragraphs.append(f"已收到 {count} 个文件，我会逐项帮您核对。" if zh else f"I've received {count} file(s). I'll help you check them step by step.")
    first = not case.history
    process = intent in {"getting_started", "how_to_apply"} or bool(re.search(r"怎么申请|如何申请|how (?:do I|to) apply", text, re.I))
    materials = intent in {"getting_started", "materials"} or bool(re.search(r"什么材料|哪些材料|what (?:documents|evidence)|what do I need", text, re.I))
    if process or (first and not count):
        paragraphs.append(("可以，我们一步步来。通常先确认是否需要签证和申请类型，再准备材料、在线填写申请并支付费用，按申请指引完成身份核验，最后等待决定。" if zh else
                           "We can take this step by step. First check whether you need a visa and which type, then prepare evidence, apply and pay online, follow the identity-check instructions, and wait for a decision.") +
                          f"\n{'官方步骤' if zh else 'Official steps'}: {APPLICATION_GUIDE}\n{'签证或 ETA 查询' if zh else 'Visa or ETA checker'}: {VISA_CHECK}")
    if materials:
        choices = {
            "visitor": ("访问签证通常先准备有效护照，并说明旅行目的、费用来源和旅行结束后的安排；银行或工作材料可帮助支持这些说明，具体材料取决于您的情况。",
                        "For a visit, start with a valid passport and information about your plans, funding and arrangements after the visit. Bank or employment evidence can support these; the exact documents depend on your circumstances."),
            "student": ("学生申请先准备有效护照和学校发的 CAS 信息，再按情况核对资金、英语、结核检查或 ATAS。CAS 是学校提供的录取确认编号和信息。",
                        "For study, start with a valid passport and the CAS details from your school. Funding, English, TB and ATAS evidence depend on your circumstances. A CAS is your school's acceptance reference and information."),
            "skilled_worker": ("技术工作申请先准备有效护照、雇主发的 CoS 工作担保信息及适用的英语证明，再核对资金和结核检查要求。",
                               "For Skilled Worker applications, start with a valid passport, CoS sponsorship details from your employer and applicable English evidence, then check funding and TB requirements."),
        }
        pair = choices.get(case.route, ("先准备护照个人信息页；其余材料要根据来英国的目的、国籍和申请地点确定，不用一次把所有文件都找齐。",
                                       "Start with your passport's personal details page. The rest depends on your purpose, nationality and where you apply; you do not need to gather everything at once."))
        paragraphs.append(pair[0 if zh else 1] + (f"\n{ROUTE_GUIDES[case.route]}" if case.route in ROUTE_GUIDES else ""))
    inside = any(c.id == "application_location" and c.status == "fail" for c in case.checks)
    if inside:
        if case.hitl_enabled:
            paragraphs.append("您是在英国境内申请，需要先由顾问确认现有身份及能否续签或转换。当前自动材料流程覆盖境外申请；请告诉我现有签证类型和到期日。" if zh else
                              "As you are applying inside the UK, an adviser needs to check whether you can extend or switch. This checklist covers applications from outside the UK. Please tell me your current visa type and expiry date.")
        else:
            paragraphs.append("当前自动流程尚未实现英国境内续签或转换，暂时无法自动完成这个申请。" if zh else
                              "This automated workflow does not yet cover extensions or switching from inside the UK.")
    if case.status == Status.COMPLETE:
        if case.hitl_enabled:
            paragraphs.append("当前版本材料包已由顾问确认，可以进行下一步申请准备。签证决定由英国签证部门作出。" if zh else
                              "An adviser has confirmed this version of your document pack for the next application step. UKVI makes the visa decision.")
        else:
            paragraphs.append("当前版本的自动材料检查已完成，模型已决定交付材料包。此包未经人工审核，签证决定由英国签证部门作出。" if zh else
                              "The automated checks are complete and the model released this pack. It has not been reviewed by a person; UKVI makes the visa decision.")
    elif case.status == Status.READY:
        if case.hitl_enabled:
            paragraphs.append("当前材料检查已完成，材料包已生成，接下来需要顾问核对原件和适用条件。" if zh else
                              "The current material checks are complete and the pack is ready. An adviser still needs to review originals and applicable conditions.")
        else:
            paragraphs.append("当前材料检查满足，正在等待模型确认交付；HITL 已关闭。" if zh else
                              "Checks are satisfied; awaiting the model's delivery decision. HITL is off.")
    else:
        blockers = [c for c in case.checks if c.status in {"fail", "unknown"}]
        ranks = {"sample": 0, "unrelated": 0, "pagination": 1, "read": 2, "context": 2,
                 "route": 3, "application_location": 4, "nationality": 5}
        actions, seen = [], set()
        ordered = ([c for key in guidance.actions for c in blockers if c.id == key] if guidance else
                   sorted(blockers, key=lambda c: ranks.get(c.id.split(":")[0], 6 if c.human else 7)))
        for check in ordered:
            family = check.id.split(":")[0]
            if inside and check.id == "application_location":
                continue
            if family == "read":
                doc = next((d for d in case.documents if check.id.endswith(":" + d.id)), None)
                if doc and all(p.startswith(("Declared pagination", "Model context")) for p in doc.problems):
                    continue
            key, message = action_for(check, case)
            if key not in seen:
                actions.append(message)
                seen.add(key)
            if len(actions) >= (2 if inside else 3):
                break
        if actions:
            paragraphs.append(("我们先处理这几项：" if zh else "Let's start with these:") + "\n" +
                              "\n".join(f"{i}. {a}" for i, a in enumerate(actions, 1)))
        if case.status == Status.NEEDS_HUMAN and not inside:
            paragraphs.append("其中有信息需要顾问核对，暂时还不能确认材料齐备。" if zh else "Some details need adviser review, so I cannot yet confirm the pack is complete.")
        if case.status == Status.BLOCKED:
            paragraphs.append("当前有条件无法自动确认，材料包暂时不能完成；关闭 HITL 后不会进入人工审批队列。" if zh else "Some conditions cannot be confirmed automatically, so the pack remains blocked. HITL is off; no human approval is queued.")
    risk_requested = bool(re.search(r"造假|假材料|改(?:一下)?(?:金额|余额)|伪造|fake|forg(?:e|ed)|fals(?:e|ify)", text, re.I))
    if first or risk_requested or (guidance and guidance.warn_material_risk):
        paragraphs.append(("请使用真实、完整的材料并如实说明情况。虚假材料或陈述可能导致拒签、许可被取消，并影响后续申请。这里核对材料的完整性、一致性和字段来源，不进行真伪鉴定。" if zh else
                           "Please provide genuine, complete documents and accurate information. False documents or statements can lead to refusal, cancellation of permission and consequences for future applications. These checks cover completeness, consistency and field sources; they do not authenticate documents.") + f"\n{SUITABILITY_GUIDE}")
    paragraphs.append(progress_text(case))
    return "\n\n".join(paragraphs)
