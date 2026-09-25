web: PYTHONPATH=src uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
ui: PYTHONPATH=src streamlit run ui/streamlit_app.py --server.port ${PORT:-8502} --server.address 0.0.0.0 --server.headless true
