"""Customer language and progress, built from checked state rather than model claims.

The model selects priorities after checks. This response catalogue owns factual
claims, official links and completion wording; it cannot override a check.
"""

import re

from .evidence import Evidence
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
    words = re.findall(r"\b[A-Za-z]+\b", text)
    return "en" if len(words) >= 3 or text.strip().lower().strip("!.?") in {"hello", "hi", "thanks", "thank you", "yes", "no", "okay", "ok"} else previous


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
    bar = "🟩" * complete + "⬜" * (10 - complete)
    if not p["route_known"]:
        return ("材料进度 " if zh else "Materials ") + bar + (
            " 清单待确认；先了解您的申请情况。" if zh else " Checklist pending; we need your circumstances first.")
    counts = (f"{p['checked']}/{p['total']} 项已收齐" if zh else f"{p['checked']}/{p['total']} categories collected")
    unresolved = any(c.status in {"fail", "unknown"} for c in case.checks) or bool(case.pending_error)
    if unresolved and complete == 10:
        bar = "🟩" * 9 + "⬜"
    suffix = ("另有信息待确认；清单会随申请情况更新。" if zh else
              "Some details still need clarification; the checklist may change.") if unresolved else (
              "按当前申请情况统计。" if zh else "Based on your current circumstances.")
    result = f"{'材料进度' if zh else 'Materials'} {bar} {counts}\n{suffix}"
    if case.application_forms:
        info = [c for c in case.checks if c.id.startswith("info:") and c.status != "not_applicable"]
        done = sum(c.status == "pass" for c in info)
        filled = int(10 * done / len(info)) if info else 0
        if any(c.id.startswith("form:") and c.status != "pass" for c in case.checks):
            filled = min(filled, 9)
        result += f"\n{'信息进度' if zh else 'Information'} {'🟩' * filled}{'⬜' * (10-filled)} {done}/{len(info)}"
    return result


def preparation_step(case):
    zh = case.language == "zh"
    if case.status == Status.COMPLETE:
        if not case.hitl_enabled:
            return "第 4 步：材料自动整理完成" if zh else "Step 4: document preparation completed automatically"
        return "第 4 步：材料包已确认" if zh else "Step 4: document pack confirmed"
    if case.status == Status.READY:
        if not case.hitl_enabled:
            return "第 4 步：确认材料是否齐备" if zh else "Step 4: confirm your pack is ready"
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
    "travel_end": ("您预计哪天离开英国？请包含年份，例如 2026-12-17；暂未订票也可以先告诉我计划日期。", "When do you plan to leave the UK? Please include the year (YYYY-MM-DD). A planned date is fine; you do not need to book a ticket now."),
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
    if family == "form":
        from .intake_schema import ALL_QUESTIONS
        question = ALL_QUESTIONS.get(check.id.split(":", 1)[1])
        label = question.label.split(" / ")[0 if zh else -1] if question else ("信息表" if zh else "worksheet")
        return check.id, (f"请检查信息表的“{label}”：答案或格式未通过检查，原有材料仍保留。请按表内提示修改并回传。" if zh else
                          f"Please check {label} in the worksheet: the answer or format could not be accepted. Your other documents are saved. Correct it using the cell instructions and return the file.")
    if family == "info":
        missing = [c.message.split(" / ")[0 if zh else -1] for c in case.checks if c.id.startswith("info:") and c.status in {"unknown", "fail"}]
        labels = ("、" if zh else ", ").join(missing[:3])
        return "information", (f"请填写附件信息表的 C 列并回传，目前还缺 {labels} 等信息；不清楚的可以先留空。" if zh else
                               f"Please fill column C of the attached worksheet and reply with the file. Missing details include {labels}; leave anything uncertain blank for now.")
    if check.id in {"sponsor_consent", "worker_atas"}:
        return check.id, check.message.split(" / ")[0 if zh else -1]
    if check.id == "application_location" and check.status == "fail" and case.hitl_enabled:
        return check.id, ("本清单覆盖英国境外申请，境内续签或转换需要顾问另行确认。请说明现有签证类型和到期日。" if zh else
                          "This checklist covers applications from outside the UK. An adviser needs to assess extensions or switching; please tell me your current visa type and expiry date.")
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
        unsupported = {
            "application_location": ("当前清单只覆盖英国境外申请，暂时不能确认境内续签或转换所需材料。", "This checklist covers applications from outside the UK; it cannot confirm extension or switching requirements."),
            "dependants": ("随行家属的材料清单尚未覆盖，暂时无法确认这类申请已经收齐。", "Dependant checklists are not covered, so I cannot confirm this application is complete."),
            "previous_refusal": ("有拒签记录时，需要按具体拒签原因准备说明；当前流程无法判断这部分材料是否齐全。", "Previous refusals need an explanation based on the refusal reasons; this workflow cannot confirm that part is complete."),
            "adult": ("当前清单只覆盖成年申请人，未成年人的监护及同意材料需要另行确认。", "This checklist covers adults; a minor's guardianship and consent documents need separate confirmation."),
            "country_scope": ("当前清单尚未覆盖您的国籍对应的条件，暂时无法确认所有适用材料。", "This checklist does not cover your nationality's conditions, so I cannot confirm all applicable documents."),
        }
        if check.id in unsupported:
            return check.id, unsupported[check.id][0 if zh else 1]
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


def known_details(case):
    """Short acknowledgement from resolved facts; conflicts never become a summary."""
    zh = case.language == "zh"
    evidence = Evidence(case)
    labels = {
        "applicant_name": ("姓名", "Name"), "nationality": ("国籍", "Nationality"),
        "application_location": ("申请地点", "Applying from"),
        "travel_start": ("出发日期", "Travel date"),
    }
    items = []
    route_names = {"visitor": ("英国访问签证", "UK visitor visa"),
                   "student": ("英国学生签证", "UK Student visa"),
                   "skilled_worker": ("英国工作签证", "UK Skilled Worker visa")}
    if case.route in route_names:
        items.append(route_names[case.route][0 if zh else 1])
    for key, pair in labels.items():
        value = evidence.get(key)
        if value is None:
            continue
        if key == "application_location":
            value = {"outside_uk": "英国境外" if zh else "outside the UK",
                     "inside_uk": "英国境内" if zh else "inside the UK"}.get(value, value)
        elif zh and value == "China":
            value = "中国"
        items.append(f"{pair[0 if zh else 1]}：{' '.join(str(value).split())[:80]}")
        if len(items) == 3:
            break
    return ("已了解：" if zh else "Noted: ") + ("；" if zh else "; ").join(items) if items else ""


def reply_for(case, *, text="", intent="continue", received_count=None, received_names=None, guidance=None):
    """Receipt, checklist, next action. Completion wording comes only from state."""
    zh = case.language == "zh"
    first = not case.history
    count = len([d for d in case.documents if not d.rejected]) if received_count is None else received_count
    if case.status == Status.COMPLETE:
        opening = "材料收集完成！✅ 感谢您配合整理。" if zh else "Document collection complete! ✅ Thanks for working through it with me."
    elif first:
        opening = "您好！我是签证材料助手 😊 我会帮您记好进度，一步步补齐材料。" if zh else "Hello! I'm your visa document assistant 😊 I'll keep track and help you gather what is needed, step by step."
    else:
        opening = "收到，谢谢您 😊" if zh else "Thanks, I've received your update 😊"
    paragraphs = [opening]
    if not case.route and case.application_forms:
        # Resolve purpose before requesting personal information or documents.
        paragraphs.append(QUESTIONS["route"][0 if zh else 1])
        if count:
            paragraphs.append("附件已经保存，确认类型后会继续检查。" if zh else "Your attachments are saved; we will continue checking them once your visa type is clear.")
        paragraphs.append(progress_text(case))
        if first:
            paragraphs.append("小提醒：请提供真实、完整的信息和材料；这里不进行真伪鉴定。" if zh else "Please use genuine, complete information and documents. This service does not authenticate them.")
        if re.search(r"伪造|造假|改.*余额|forge|falsify", text, re.I):
            paragraphs.append("虚假材料可能导致拒签并影响未来申请。" if zh else "False documents can lead to refusal and affect future applications.")
        return "\n\n".join(paragraphs)
    if case.test_mode:
        paragraphs.append("演示案件：测试材料仅供体验，不用于真实申请。" if zh else "Demo case: these test documents are for practice only.")
    if count:
        names = received_names if received_names is not None else [d.name for d in case.documents if not d.rejected][-count:]
        names = [" ".join(name.split())[:80] for name in names[:5]]
        receipt = (f"📥 本次已收到 {count} 个文件" if zh else f"📥 Received {count} file(s) this time")
        paragraphs.append(receipt + ("：" + "、".join(names) if names else ""))
    details = known_details(case)
    if details:
        paragraphs.append(details)
    if case.form_path and case.status not in {Status.COMPLETE, Status.READY}:
        paragraphs.append("📝 附件是中英双语信息表：填写 C 列，保存后直接作为附件回复。可先填会填的，其余我们逐步补齐。它是准备表，不能替代 GOV.UK 在线申请。" if zh else
                          "📝 The attached worksheet is bilingual (Chinese/English). Fill column C, save it and reply with the file. Start with what you know; we can complete the rest step by step. It prepares your information and does not replace the GOV.UK application.")

    progress = material_progress(case)
    done = [i["label"] for i in progress["items"] if i["status"] == "checked"]
    pending = [i["label"] for i in progress["items"] if i["status"] != "checked"]
    if done:
        paragraphs.append(("✅ 已收齐：" if zh else "✅ Collected: ") + ("、" if zh else ", ").join(done))
    if pending:
        paragraphs.append(("待补齐或确认：" if zh else "Still needed or to clarify: ") + ("、" if zh else ", ").join(pending))
    if count and not case.test_mode:
        samples = [d.name for d in case.documents if not d.rejected and d.content_role == "sample"]
        action_ids = guidance.actions if guidance else [c.id for c in case.checks if c.status in {"fail", "unknown"}]
        if samples and not any(key.startswith("sample:") for key in action_ids):
            names = ", ".join(samples[:5])
            paragraphs.append(f"{names} 是样例，不能作为您本人的正式申请证据；请换成本人的材料。" if zh else
                              f"{names} is a sample and cannot count as your application evidence. Please send your own document.")

    if guidance and guidance.explanation != "continue":
        intent = guidance.explanation
    process = intent == "how_to_apply" or bool(re.search(r"怎么申请|如何申请|how (?:do I|to) apply", text, re.I))
    materials = intent == "materials" or bool(re.search(r"什么材料|哪些材料|what (?:documents|evidence)|what do I need", text, re.I))
    if process:
        paragraphs.append(("申请顺序：确认类型 → 收集材料 → 在线申请及付款 → 按指引核验身份 → 等待决定。" if zh else
                           "The steps: choose your visa → collect documents → apply and pay online → follow identity-check instructions → await the decision.") +
                          f"\n{APPLICATION_GUIDE}")
    elif materials and case.status != Status.COMPLETE:
        outlines = {
            "visitor": ("先准备护照、旅行安排和费用来源说明；工作及资金材料按您的情况补充。", "Start with your passport, travel plans and funding details; work and financial evidence depend on your circumstances."),
            "student": ("先准备护照和学校的 CAS 录取确认信息，再确认资金、英语及适用的结核检查或 ATAS。", "Start with your passport and school CAS details, then funding, English and any applicable TB or ATAS evidence."),
            "skilled_worker": ("先准备护照和雇主的 CoS 担保信息，再确认英语、资金及适用的结核检查。", "Start with your passport and employer's CoS details, then English, funding and any applicable TB evidence."),
        }
        pair = outlines.get(case.route, ("先确认来英国的目的和申请地点，再列适用材料；您可以先准备护照个人信息页。", "First tell me your purpose and where you will apply, so I can build the checklist. You can start with your passport details page."))
        # Existing category + next-action lists already explain what to send.
        # Keep the source link without repeating that checklist in another paragraph.
        explanation = ("材料说明：" if zh else "Checklist guidance: ") if progress["items"] else pair[0 if zh else 1] + "\n"
        paragraphs.append(explanation + ROUTE_GUIDES.get(case.route, VISA_CHECK))

    if case.status == Status.COMPLETE:
        paragraphs.append(("当前清单需要的材料和信息已收齐，暂时不用补充。后续有变化，直接回复这封邮件即可。" if zh else
                           "The documents and information on the current checklist are collected. Nothing further is needed now; reply to this email if anything changes."))
        if case.hitl_enabled:
            paragraphs.append("顾问已确认当前版本材料包。" if zh else "An adviser has confirmed this version of the pack.")
        paragraphs.append("这里只确认收集完成，不代表签证获批，也未替您提交申请。" if zh else
                          "This confirms collection only. It is not a visa approval, and no visa application has been submitted for you.")
    elif case.status == Status.READY:
        paragraphs.append("当前清单材料已齐，等待您选择的顾问复核。" if zh else
                          "The current checklist is complete and awaits your selected adviser review.")
    else:
        blockers = [c for c in case.checks if c.status in {"fail", "unknown"}]
        ranks = {"sample": 0, "unrelated": 0, "pagination": 1, "read": 2, "context": 2,
                 "route": 3, "application_location": 4, "nationality": 5}
        actions, seen = [], set()
        ordered = ([c for key in guidance.actions for c in blockers if c.id == key] if guidance else
                   sorted(blockers, key=lambda c: ranks.get(c.id.split(":")[0], 6 if c.human else 7)))
        for check in ordered:
            if check.id.startswith("read:"):
                doc = next((d for d in case.documents if check.id.endswith(":" + d.id)), None)
                if doc and all(p.startswith(("Declared pagination", "Model context")) for p in doc.problems):
                    continue
            key, message = action_for(check, case)
            if key not in seen:
                actions.append(message)
                seen.add(key)
            if len(actions) >= 3:
                break
        if actions:
            paragraphs.append(("📌 下一步，先补充这几项：" if zh else "📌 Next, please help with:") + "\n" +
                              "\n".join(f"{i}. {a}" for i, a in enumerate(actions, 1)))
        if case.status == Status.NEEDS_HUMAN:
            paragraphs.append("有信息需要顾问核对，目前还不能确认收集完成。" if zh else "Some details need adviser review before collection can be confirmed complete.")
        elif case.status == Status.BLOCKED:
            paragraphs.append("还有信息无法确认，已收到的资料会保留，目前还不能确认收集完成。" if zh else "Some details cannot be confirmed yet. Your documents are saved, but collection is not complete.")

    paragraphs.append(progress_text(case))
    if case.status == Status.WAIT_USER:
        paragraphs.append("直接回复即可；暂时没有的材料告诉我一声，我们先处理手头有的。" if zh else
                          "Just reply here. If a document isn't available yet, let me know and we'll start with what you have.")
    risk_requested = bool(re.search(r"造假|假材料|改(?:一下)?(?:金额|余额)|(?:金额|余额).{0,4}改|伪造|fake|forg(?:e|ed)|fals(?:e|ify)", text, re.I))
    if risk_requested or (guidance and guidance.warn_material_risk):
        paragraphs.append(("请勿修改事实或伪造材料，虚假材料或陈述可能导致拒签，并影响后续申请。这里不进行真伪鉴定。" if zh else
                           "Please do not falsify information or documents. False evidence can lead to refusal and affect future applications. These checks do not authenticate documents.") + f"\n{SUITABILITY_GUIDE}")
    elif first:
        paragraphs.append("小提醒：请提供真实、完整的材料；这里协助收集，不进行真伪鉴定。" if zh else
                          "Please use genuine, complete documents. This service helps collect them; it does not authenticate them.")
    return "\n\n".join(paragraphs)
