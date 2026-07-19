# O2N Engine Backend

Enterprise backend foundation for the O2N Engine software-modernization platform.

## Prerequisites

- Python 3.12 or 3.13 (recommended for the Tree-sitter, Semgrep, FAISS, and embedding dependencies)
- MongoDB 7+

## Install and run

```powershell
cd "F:\OpenAi Hackathone\backend"
# Configure the existing .env file. JWT_SECRET_KEY must be a cryptographically random value.
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify the service at `http://localhost:8000/health`; interactive OpenAPI documentation is at `http://localhost:8000/docs`.

Set `ENVIRONMENT=production` only after configuring both `MONGODB_URI` and a 32+ character `JWT_SECRET_KEY`.
