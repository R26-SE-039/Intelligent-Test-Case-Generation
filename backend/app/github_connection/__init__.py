"""
Per-project GitHub credentials + workflow installer.

The dashboard's Settings → GitHub Connection screen drives this module. Users
paste a Personal Access Token, pick a repo they own, and we encrypt the
token (Fernet) into project_github_connections, then install the
NextGenQA workflow file on the repo's default branch.

The Execution & Report pipeline calls `load_connection(project_id)` to get
the decrypted token + repo at run-time. If no connection exists, the runner
falls back to the local subprocess path.
"""
from .crypto import encrypt_token, decrypt_token, mask_token
from .store import load_connection, ConnectionRecord

__all__ = [
    "encrypt_token", "decrypt_token", "mask_token",
    "load_connection", "ConnectionRecord",
]
