"""`uv run finquery` entry point."""

import argparse

import uvicorn
from dotenv import load_dotenv

from finquery.app import create_app
from finquery.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="finquery", description="Run the FinQuery server.")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="API only with auto reload; run `npm run dev` in frontend/ for the UI (Vite proxies /api).",
    )
    args = parser.parse_args()

    load_dotenv()
    settings = Settings()
    if args.dev:
        uvicorn.run("finquery.main:dev_app", factory=True, host=settings.host, port=settings.port, reload=True)
    else:
        print(f"FinQuery on http://{settings.host}:{settings.port} (provider: {settings.provider})", flush=True)
        uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


def dev_app():
    load_dotenv()
    return create_app(Settings(), serve_frontend=False)


if __name__ == "__main__":
    main()
