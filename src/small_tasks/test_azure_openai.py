import requests

# 設定端點與金鑰
endpoint = "https://dhp.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"
api_key = "＊＊＊＊＊"

# 定義請求的資料
headers = {
    "Content-Type": "application/json",
    "api-key": api_key,
}
data = {
    "messages": [
        {"role": "system", "content": "You are an AI assistant."},
        {"role": "user", "content": "你好，幫我解決問題吧！"}
    ],
    "max_tokens": 100,
    "temperature": 0.7,
}

# 發送請求
response = requests.post(endpoint, headers=headers, json=data)

# 檢視結果
if response.status_code == 200:
    print("回應內容:", response.json())
else:
    print("錯誤:", response.status_code, response.text)
