"""Customer handover for outside-UK applications; official pages checked 2026-10-07."""

APPLICATIONS = {
    "visitor": "https://www.gov.uk/standard-visitor/apply-standard-visitor-visa",
    "student": "https://www.gov.uk/student-visa/apply-online",
    "skilled_worker": "https://www.gov.uk/skilled-worker-visa/apply-from-outside-the-uk",
}
CENTRES = "https://www.gov.uk/find-a-visa-application-centre"


def submission_steps(route: str, language: str) -> str:
    """Describe next steps without asserting an application or booking exists."""
    zh = language == "zh"
    url = APPLICATIONS.get(route, "https://www.gov.uk/apply-to-come-to-the-uk")
    reminder = {
        "visitor": (
            "核对行程、费用来源和离境安排。访问签证没有统一的最低银行余额；是否足够取决于您的具体情况。",
            "Check your travel plans, funding and plans to leave the UK. Visitor visas have no single minimum bank balance; adequacy depends on your circumstances."),
        "student": (
            "核对学校 CAS、学费、生活费及适用的 TB/ATAS；资金条件与是否必须提交资金证明是两回事。",
            "Check your CAS, tuition, living costs and any applicable TB/ATAS evidence. Meeting the financial condition is separate from being required to submit financial evidence."),
        "skilled_worker": (
            "请雇主核对 CoS、担保资格、职业代码及按工时计算的薪资门槛。本服务收集薪资信息，尚未核验完整的薪资资格或担保登记。",
            "Ask your employer to check the CoS, sponsor eligibility, occupation code and salary threshold for your working hours. This service collects salary details but does not verify full salary eligibility or the sponsor register."),
    }.get(route, ("按官网确认适用条件。", "Check the applicable conditions on GOV.UK."))[0 if zh else 1]
    if zh:
        identity = ("访问签证需要预约签证申请中心采集指纹和照片。" if route == "visitor" else
                    "如果指定使用 UK Immigration: ID Check App，按 App 指引操作；只有要求到签证申请中心时才需要预约。")
        return (
            "📌 接下来，您可以这样提交申请：\n"
            "1. 解压材料包，先打开 START-HERE.html。核对信息表和原始材料；信息表用于准备答案，不是官方申请表。\n"
            f"2. 打开本路线的 GOV.UK 页面，从页面中的申请入口开始，填写在线表格：\n{url}\n"
            f"   {reminder}\n"
            "3. 确认答案后，按账户提示提交并支付申请费及适用的移民医疗附加费。保存申请编号、回执和官方材料清单。\n"
            f"4. 按申请账户提示完成身份核验。{identity}需要预约时，从申请账户进入预约网站，选择中心和可用时间（slot），保存确认函。中心查询：\n{CENTRES}\n"
            "5. 按官方清单和上传期限逐份上传解压后的文件，勿将整个 ZIP 或我们的内部检查报告当作申请证据上传。"
            "需要到场时，携带护照及预约确认函要求的材料，按时出席。之后在申请账户或通知邮件中查看进展。\n"
            "预约名额、费用和最终材料要求以官方账户为准；我们尚未替您提交申请或预约。"
        )
    identity = ("For a Visitor visa, book a visa application centre appointment for fingerprints and a photo. " if route == "visitor" else
                "If directed to the UK Immigration: ID Check App, follow its instructions. Only book a centre appointment if your application directs you to one. ")
    return (
        "📌 Your next steps:\n"
        "1. Unzip the pack and open START-HERE.html. Check the worksheet and originals. The worksheet prepares your answers; it is not the official application form.\n"
        f"2. Start your online application from the GOV.UK page for your route:\n{url}\n"
        f"   {reminder}\n"
        "3. Check your answers, submit and pay the application fee and any applicable immigration health surcharge as directed. Save the reference, receipt and official document checklist.\n"
        f"4. Follow your account's identity-check instructions. {identity}If an appointment is needed, use the link in your application account, choose the centre and an available slot, and save the confirmation. Find centres here:\n{CENTRES}\n"
        "5. Upload individual unpacked documents as requested, before the stated deadline. Do not upload the whole ZIP or our internal checking report as evidence. "
        "For an in-person appointment, bring your passport and the items listed in your appointment confirmation. Then follow updates in your account or notification emails.\n"
        "Available slots, fees and final requirements come from your official account. We have not submitted an application or booked an appointment for you."
    )


def bilingual_guide(route: str) -> str:
    return "英国境外申请指引 / Applying from outside the UK\nChecked: 2026-10-07\n\n" + submission_steps(route, "zh") + "\n\n" + submission_steps(route, "en") + "\n"
