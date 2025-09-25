# mcp-playwright-gpt
lsof -i :8000
pkill next-server
lsof -ti :8000 | xargs kill -9
uvicorn web_app.app:app

http://localhost:8000/test-simple

npm install -g @google/gemini-cli