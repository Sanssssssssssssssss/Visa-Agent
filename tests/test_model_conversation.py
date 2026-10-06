"""Regression for colloquial mail, customer corrections and visible failures."""
from email.message import EmailMessage

import pytest
from pydantic_ai.models.test import TestModel

from visa_agent.config import load_environment
from visa_agent.conversation import reply_for
from visa_agent.evidence import Evidence, apply_proposal
from visa_agent.mime_mail import clean_body, new_body
from visa_agent.service import VisaService
from visa_agent.types import Candidate, Case, CaseEvent, Guidance, Proposal, Status


def test_env_loads_utf8_without_overwriting_shell(tmp_path, monkeypatch):
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '0')
    path = tmp_path / '.env'
    path.write_text('VISA_MODEL=file-model\nVISA_MAIL_INTERVAL=18\n', encoding='utf-8-sig')
    monkeypatch.setenv('VISA_MODEL', 'shell-model')
    monkeypatch.delenv('VISA_MAIL_INTERVAL', raising=False)
    monkeypatch.setenv('VISA_ENV_FILE', str(path))
    assert load_environment()
    import os
    assert os.environ['VISA_MODEL'] == 'shell-model'
    assert os.environ['VISA_MAIL_INTERVAL'] == '18'
    os.environ.pop('VISA_MAIL_INTERVAL')  # dotenv writes outside monkeypatch tracking


@pytest.mark.parametrize('body', ['去玩', '读书', '/reset', '我的邮箱是 me@example.com，电话后补'])
@pytest.mark.parametrize('html', [False, True])
def test_netease_reply_keeps_only_new_text(body, html):
    text = body + '\n\n| |\nExample\n|\n|\n邮箱：customer@example.com\n|\n\n---- 回复的原邮件 ----\n旅游还是读书？'
    message = EmailMessage()
    message.set_content(text.replace('\n', '<br>') if html else text, subtype='html' if html else 'plain')
    assert new_body(message) == body
    assert clean_body('A | B\nmy email: me@example.com') == 'A | B\nmy email: me@example.com'


def test_source_grounded_colloquial_plan_correction_keeps_audit():
    case = Case(id='c')
    for event, route, purpose, replace in [('1', 'visitor', '去玩', False), ('2', 'student', '读书', True)]:
        source = 'message:' + event
        proposal = Proposal(replace_plan=replace, facts=[
            Candidate(key='route', value=route, source_id=source, quote=purpose),
            Candidate(key='purpose', value=purpose, source_id=source, quote=purpose)])
        assert not apply_proposal(case, proposal, {source: purpose}, current_source=source)
        assert Evidence(case).get('route') == route
    assert len(case.facts) == 4 and sum(f.active for f in case.facts) == 2
    assert case.reviews[-1]['decision'] == 'customer_plan_update'
    bad = Proposal(facts=[Candidate(key='route', value='visitor', source_id='message:missing', quote='去玩')])
    assert apply_proposal(case, bad, {}, current_source='message:missing')
    assert Evidence(case).get('route') == 'student'


def test_model_words_reach_customer_without_route_template():
    wording = '明白，是去读书。先看看学校有没有给你 CAS；还没有也没关系。'
    case = Case(id='c', application_forms=True)
    reply = reply_for(case, guidance=Guidance(reply=wording))
    assert reply.startswith(wording)
    assert '旅游、读书还是工作' not in reply
    assert '材料进度' in reply


def test_reply_model_failure_preserves_fact_and_still_answers(tmp_path):
    from pydantic_ai.models.function import FunctionModel
    def unavailable(messages, info):
        raise RuntimeError('private tool trace')
    model = TestModel(call_tools=[], custom_output_args={'facts': [
        {'key': 'route', 'value': 'visitor', 'source_id': 'message:e', 'quote': '去玩'}]})
    app = VisaService(tmp_path, 'offline', hitl=False, model_override=model,
                      guidance_model_override=FunctionModel(unavailable))
    app.create_case('c')
    result = app.handle_event(CaseEvent(case_id='c', event_id='e', text='去玩'))
    assert result.reply and 'private tool trace' not in result.reply
    assert result.status == Status.WAIT_USER and Evidence(app.store.get('c')).get('route') == 'visitor'
    assert app.store.traces('c')[-1]['reply_error'] == 'RuntimeError'
