"""
Stub for local development. In production this loads secrets from AWS Secrets Manager.
Locally, secrets are loaded from the .env file via load_dotenv in app.py.
"""


def load_aws_secrets():
    """No-op for local dev — secrets come from .env instead."""
    pass
