"""Microsoft's public-client login and encrypted token cache; no mailbox passwords."""
import os
from pathlib import Path
import re
import uuid

import msal
from msal_extensions import PersistedTokenCache, build_encrypted_persistence

from .inbox import normalize_sender


class OutlookAuth:
    def __init__(self, root: Path, *, send_replies=False):
        client_id = os.getenv("VISA_MS_CLIENT_ID", "")
        try:
            uuid.UUID(client_id)
        except ValueError:
            raise ValueError("Set VISA_MS_CLIENT_ID to your Microsoft application (client) ID") from None
        self.mailbox = normalize_sender("email", os.getenv("VISA_OUTLOOK_MAILBOX", ""))
        tenant = os.getenv("VISA_MS_TENANT", "common")
        if tenant not in {"common", "consumers", "organizations"} and not re.fullmatch(r"[0-9a-fA-F-]{36}", tenant):
            raise ValueError("Use common, consumers, organizations or your tenant UUID")
        self.scopes = ["User.Read", "Mail.Read"] + (["Mail.Send"] if send_replies else [])
        directory = Path(root) / "outlook-auth"
        directory.mkdir(parents=True, exist_ok=True)
        # DPAPI on Windows; system keyring on supported Unix installations.
        # Failure to encrypt is an error, not permission to save plaintext tokens.
        cache = PersistedTokenCache(build_encrypted_persistence(str(directory / "tokens.bin")))
        self.app = msal.PublicClientApplication(client_id, authority=f"https://login.microsoftonline.com/{tenant}",
                                                 token_cache=cache)

    def login(self):
        flow = self.app.initiate_device_flow(scopes=self.scopes)
        if "user_code" not in flow:
            raise RuntimeError("Microsoft did not start device login: " + flow.get("error", "unknown_error"))
        print(flow["message"], flush=True)  # User-facing code, never a token.
        result = self.app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError("Microsoft login failed: " + result.get("error", "unknown_error"))
        # Account selection is checked by token() and Graph /me before processing.
        return {"authenticated": True, "mailbox_configuration": self.mailbox, "send_scope": "Mail.Send" in self.scopes}

    def token(self):
        accounts = self.app.get_accounts(username=self.mailbox)
        if len(accounts) != 1:
            raise ValueError("Run outlook login for VISA_OUTLOOK_MAILBOX before polling")
        result = self.app.acquire_token_silent(self.scopes, account=accounts[0])
        if not result or "access_token" not in result:
            raise RuntimeError("Microsoft authorization needs renewal; run outlook login with the same send option")
        return result["access_token"]
