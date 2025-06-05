import os
AI_KEY =  os.environ.get("OPENAI_API_KEY",None)
AI_MODEL = os.environ.get('AI_MODEL','gpt-4o-mini')
OPENAI_UPLOAD_STORAGE =  os.environ.get("OPENAI_UPLOAD_STORAGE",'/tmp/openaifiles')
os.makedirs(OPENAI_UPLOAD_STORAGE, exist_ok=True)
