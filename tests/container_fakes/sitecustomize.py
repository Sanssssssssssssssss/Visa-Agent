"""CI-only transport replacement; mounted by compose.ci.yaml, never a live mode."""
from pydantic_ai import models
from visa_agent import qq_mail

models.ALLOW_MODEL_REQUESTS = False


class EmptyMailbox:
    uidvalidity = 1

    def __init__(self, mailbox, secret):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def uids(self, since, after):
        return []


qq_mail.QQConnection = EmptyMailbox
