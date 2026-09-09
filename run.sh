#!/usr/bin/env bash
# Start the dashboard on http://localhost:8501
cd "$(dirname "$0")"
exec .venv/bin/streamlit run app/Home.py "$@"
