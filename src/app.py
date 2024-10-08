# 匯入必要的套件
import os
import sys
import time
import shutil
import subprocess
import xml.etree.ElementTree as ET
import requests
import json
from collections import defaultdict
from pydantic import BaseModel
import pandas as pd
from datetime import datetime
import uuid
from celery import Celery
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from colorama import Fore, Style
start_time = time.time()
print(f"{Fore.GREEN}MedCAT package importing...{Style.RESET_ALL}", end="", flush=True)
from medcat.cat import CAT
import_time = time.time()
print(f"{Fore.GREEN} done. ({import_time - start_time:.2f} sec){Style.RESET_ALL}")

# 初始化 Flask 應用程式
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, methods=["GET", "POST", "PUT", "DELETE"])
app.config['UPLOAD_FOLDER'] = '../data/input'
app.config['PIPE_FOLDER'] = '../data/pipe_result'

print("app.import_name", app.import_name)

celery = Celery(
    "app",
    backend='redis://localhost:6379/0',
    broker='redis://localhost:6379/0'
)
celery.conf.update(app.config)
TaskBase = celery.Task

print("celery.main", celery.main)

class ContextTask(TaskBase):
    def __call__(self, *args, **kwargs):
        with app.app_context():
            return TaskBase.__call__(self, *args, **kwargs)

celery.Task = ContextTask

@celery.task
def process_medical_records_task(file_path, sqe_list=None):
    process_medical_records(file_path, sqe_list)

@celery.task
def process_medical_text_task(file_path):
    process_medical_text(file_path)

# 確保上傳目錄存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 輔助常數
NEWLINE = "\n"
NONE_SYMBOL = "-"

# 載入 MedCAT 模型與 UMLS 子集字典（在應用程式啟動時載入一次）
print(f"{Fore.GREEN}MedCAT Model and UMLS Dictionary Subset loading...{NEWLINE}{Style.RESET_ALL}", end="", flush=True)
model = "mc_modelpack_snomed_int_16_mar_2022_25be3857ba34bdd5.zip"
cat = CAT.load_model_pack(f'../models/{model}')
print(f"{Fore.GREEN}waiting for UMLS Dictionary Subset...{NEWLINE}{Style.RESET_ALL}", end="", flush=True)

umls_sub_dict = "filtered_data.csv"
umls_df = pd.read_csv(f"../data/dict/{umls_sub_dict}", sep='|', header=None)
umls_df.columns = [
    'CUI', 'LAT', 'TS', 'LUI', 'STT', 'SUI', 'ISPREF', 'AUI', 'SAUI',
    'SCUI', 'SDUI', 'SAB', 'TTY', 'CODE', 'STR', 'SRL', 'SUPPRESS', 'CVF'
]
print(umls_df.head())
model_loaded_time = time.time()
print(f"{Fore.GREEN} done. ({model_loaded_time - import_time:.2f} sec){Style.RESET_ALL}")

# 定義 Pydantic 模型結構（若需要，可以保留）
class SNOMED_CT(BaseModel):
    raw_text_as_clues: list[str]
    implies_concepts_FSN: list[str]
    id: str

class LOINC(BaseModel):
    raw_text_as_clues: list[str]
    implies_concepts_FSN: list[str]
    id: str

class RxNorm(BaseModel):
    raw_text_as_clues: list[str]
    implies_concepts_FSN: list[str]
    id: str

class JSONStructure(BaseModel):
    SNOMED_CT: list[SNOMED_CT]
    LOINC: list[LOINC]
    RxNorm: list[RxNorm]

# 初始化 OpenAI 客戶端（建議使用環境變數來存放 API 金鑰）
openai_api_key = os.getenv("OPENAI_API_KEY", "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")
if not openai_api_key:
    raise ValueError("請設定 OPENAI_API_KEY 環境變數")
client = OpenAI(api_key=openai_api_key)


# 封裝從第 1 步開始的邏輯為函式
def process_medical_records(file_path, sqe_list=None):
    """
    處理醫學紀錄的主要函式。

    參數：
    - file_path: 上傳的檔案路徑
    - sqe_list: 選填，指定要處理的行序號列表
    """
    start_time = time.time()
    # 取得檔案名稱和副檔名
    file_name = os.path.basename(file_path)
    file_base_name = file_name[:file_name.rfind(".")]
    file_ext = file_name[file_name.rfind(".")+1:]

    # 讀取 Excel 檔案
    df = pd.read_excel(file_path)
    print(df.head())

    # 逐行處理每個病患的紀錄
    for index, row in df.iterrows():
        if sqe_list and index not in sqe_list:
            continue  # 如果有提供 sqe_list，則只處理指定的行

        sqe_start_time = time.time()
        sqe = row['sqe']

        # 第 1 步：預處理
        # 將每個病患的紀錄儲存為一個文字檔
        raw_txt_path = f"../data/pipe_result/{file_base_name}_{sqe}.raw.txt"
        with open(raw_txt_path, "w") as file:
            print(row)
            file.write(
                f"**********急診去辨識病歷**********\n\n{row['急診去辨識病歷']}\n\n"
                f"**********住院去辨識病歷**********\n\n{row['住院去辨識病歷']}\n\n"
                f"**********檢驗紀錄**********\n\n{row['檢驗紀錄']}"
            )
        print("Step1 done")

        # 第 2 步：LLM 精煉
        # 讀取內容並拆分
        with open(raw_txt_path, "r") as file:
            content = file.read()

        split_content = content.split("\n\n")
        standardized_content = ""

        for i, segment in enumerate(split_content):
            # 顯示預覽
            lines = segment.splitlines()
            print(
                f"{Fore.YELLOW}{NEWLINE.join(lines[:5])}{f' [... {len(lines)} 行]' if len(lines) > 5 else ''}{Style.RESET_ALL}"
            )
            print(f"{Fore.WHITE}sqe {sqe}: {i+1}/{len(split_content)} 正在精煉...{Style.RESET_ALL}", end="", flush=True)
            seqment_start_time = time.time()

            # 呼叫 OpenAI API 進行處理
            standardization_completion = client.chat.completions.create(
                model="gpt-4o-2024-08-06",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "將使用者的內容翻譯成英文並執行標準化、精煉、以及縮寫展開（詞展開）。對於狀態詞後的實體，確保狀態詞適用於後續的每個實體。"
                        )
                    },
                    {"role": "user", "content": segment}
                ]
            )

            seqment_end_time = time.time()
            print(f"{Fore.WHITE} 完成。({round(seqment_end_time - seqment_start_time, 2)} sec)\n{Style.RESET_ALL}")
            # 合併所有段落
            standardized_content += standardization_completion.choices[0].message.content

        # 儲存標準化後的內容
        polishing_txt_path = f"../data/pipe_result/{file_base_name}_{sqe}.raw.polishing.txt"
        with open(polishing_txt_path, "w") as file:
            file.write(standardized_content)
        preprocess_time = time.time()
        print(f"{Fore.GREEN}sqe {sqe} 精煉時間: {round(preprocess_time - sqe_start_time, 2)} sec{Style.RESET_ALL}")

        # 第 3 步：語言學擷取（MedCAT）
        entities = cat.get_entities(standardized_content)
        print(1)
        # 儲存實體為 JSON 檔案
        medcat_json_path = f"../data/pipe_result/{file_base_name}_{sqe}.raw.polishing.MedCAT.json"
        print(2)
        with open(medcat_json_path, "w") as json_file:
            print(3)
            json.dump(entities, json_file, indent=2)
        print(4)
        linguistic_extraction_time = time.time()
        print(f"{Fore.GREEN}sqe {sqe} 語言學擷取時間: {round(linguistic_extraction_time - preprocess_time, 2)} sec{Style.RESET_ALL}")

        # 第 4 步：醫學規範化
        output_txt_path = f"../data/pipe_result/{file_base_name}_{sqe}.raw.polishing.output.txt"
        with open(output_txt_path, "w") as file:
            file.write("index|chunk|cui|source|code|string\n")
            entity_list = entities['entities']
            index_now = 0
            for key, entity in entity_list.items():
                cui_str = entity.get('cui', NONE_SYMBOL)
                sab_str = NONE_SYMBOL
                code_str = NONE_SYMBOL
                # 從 UMLS 資料集中取得詳細資訊
                cui_df = umls_df[umls_df['SCUI'] == cui_str]
                preferred_df = cui_df[cui_df['ISPREF'] == 'Y']
                if not preferred_df.empty:
                    target_df = preferred_df[preferred_df['TTY'] == 'PT']
                    if target_df.empty:
                        target_df = preferred_df[preferred_df['TTY'] == 'FN']
                else:
                    target_df = cui_df
                if not target_df.empty:
                    cui_str = target_df.iloc[0]['CUI']
                    sab_str = target_df.iloc[0]['SAB']
                    code_str = target_df.iloc[0]['CODE']
                else:
                    sab_str = "<LOST>"
                    code_str = "<LOST>"
                # 寫入檔案
                if entity.get('start') > index_now:
                    file.write(f"{index_now}|{standardized_content[index_now:entity.get('start')].replace(NEWLINE, '<NEW_LINE>')}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}{NEWLINE}")
                file.write(f"{entity.get('start')}|{standardized_content[entity.get('start'):entity.get('end')].replace(NEWLINE, '<NEW_LINE>')}|{cui_str}|{sab_str}|{code_str}|{entity.get('pretty_name', NONE_SYMBOL)}{NEWLINE}")
                index_now = entity.get('end')

        medical_normalization_time = time.time()
        print(f"{Fore.GREEN}sqe {sqe} 醫學規範化時間: {round(medical_normalization_time - linguistic_extraction_time, 2)} sec{Style.RESET_ALL}")
        sqe_end_time = time.time()
        print(f"{Fore.BLUE}sqe {sqe} 總時間: {round(sqe_end_time - sqe_start_time, 2)} sec{Style.RESET_ALL}")

        # 把整份output.txt檔案傳送到指定的API
        with open(output_txt_path, "r") as file:
            content = file.read()
            url = "http://35.229.136.14:8090/contentListener"
            headers = {
                'Content-Type': 'application/json'
            }
            response = requests.request("POST", url, headers=headers, data=content)

        # 如果只想處理一筆記錄，可以在此處加入 break
        # break

    end_time = time.time()
    print(f"總處理時間: {round(end_time - start_time, 2)} sec")


# 封裝從第 1 步開始的邏輯為函式
def process_medical_text(file_path):
    sqe = uuid.uuid4().hex
    sqe_start_time = time.time()

    # 第 1 步：預處理
    # 將每個病患的紀錄儲存為一個文字檔
    file_name = os.path.basename(file_path)
    file_base_name = ".".join(file_name.split(".")[:-2])
    file_ext = file_name[file_name.rfind(".")+1:]

    # 第 2 步：LLM 精煉
    # 讀取內容並拆分
    with open(file_path, "r") as file:
        content = file.read()

    split_content = content.split("\n\n")
    standardized_content = ""

    for i, segment in enumerate(split_content):
        # 顯示預覽
        lines = segment.splitlines()
        print(
            f"{Fore.YELLOW}{NEWLINE.join(lines[:5])}{f' [... {len(lines)} 行]' if len(lines) > 5 else ''}{Style.RESET_ALL}"
        )
        print(f"{Fore.WHITE}sqe {sqe}: {i+1}/{len(split_content)} 正在精煉...{Style.RESET_ALL}", end="", flush=True)
        seqment_start_time = time.time()

        # 呼叫 OpenAI API 進行處理
        standardization_completion = client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "將使用者的內容翻譯成英文並執行標準化、精煉、以及縮寫展開（詞展開）。對於狀態詞後的實體，確保狀態詞適用於後續的每個實體。"
                    )
                },
                {"role": "user", "content": segment}
            ]
        )

        seqment_end_time = time.time()
        print(f"{Fore.WHITE} 完成。({round(seqment_end_time - seqment_start_time, 2)} sec)\n{Style.RESET_ALL}")
        # 合併所有段落
        standardized_content += standardization_completion.choices[0].message.content

    # 儲存標準化後的內容
    polishing_txt_path = f"../data/pipe_result/{file_base_name}_{sqe}.raw.polishing.txt"
    with open(polishing_txt_path, "w") as file:
        file.write(standardized_content)
    preprocess_time = time.time()
    print(f"{Fore.GREEN}sqe {sqe} 精煉時間: {round(preprocess_time - sqe_start_time, 2)} sec{Style.RESET_ALL}")

    # 第 3 步：語言學擷取（MedCAT）
    entities = cat.get_entities(standardized_content)
    # 儲存實體為 JSON 檔案
    medcat_json_path = f"../data/pipe_result/{file_base_name}_{sqe}.raw.polishing.MedCAT.json"
    with open(medcat_json_path, "w") as json_file:
        json.dump(entities, json_file, indent=2)
    linguistic_extraction_time = time.time()
    print(f"{Fore.GREEN}sqe {sqe} 語言學擷取時間: {round(linguistic_extraction_time - preprocess_time, 2)} sec{Style.RESET_ALL}")

    # 第 4 步：醫學規範化
    output_txt_path = f"../data/pipe_result/{file_base_name}_{sqe}.raw.polishing.output.txt"
    with open(output_txt_path, "w") as file:
        file.write("index|chunk|cui|source|code|string\n")
        entity_list = entities['entities']
        index_now = 0
        for key, entity in entity_list.items():
            cui_str = entity.get('cui', NONE_SYMBOL)
            sab_str = NONE_SYMBOL
            code_str = NONE_SYMBOL
            # 從 UMLS 資料集中取得詳細資訊
            cui_df = umls_df[umls_df['SCUI'] == cui_str]
            preferred_df = cui_df[cui_df['ISPREF'] == 'Y']
            if not preferred_df.empty:
                target_df = preferred_df[preferred_df['TTY'] == 'PT']
                if target_df.empty:
                    target_df = preferred_df[preferred_df['TTY'] == 'FN']
            else:
                target_df = cui_df
            if not target_df.empty:
                cui_str = target_df.iloc[0]['CUI']
                sab_str = target_df.iloc[0]['SAB']
                code_str = target_df.iloc[0]['CODE']
            else:
                sab_str = "<LOST>"
                code_str = "<LOST>"
            # 寫入檔案
            if entity.get('start') > index_now:
                file.write(f"{index_now}|{standardized_content[index_now:entity.get('start')].replace(NEWLINE, '<NEW_LINE>')}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}{NEWLINE}")
            file.write(f"{entity.get('start')}|{standardized_content[entity.get('start'):entity.get('end')].replace(NEWLINE, '<NEW_LINE>')}|{cui_str}|{sab_str}|{code_str}|{entity.get('pretty_name', NONE_SYMBOL)}{NEWLINE}")
            index_now = entity.get('end')

    medical_normalization_time = time.time()
    print(f"{Fore.GREEN}sqe {sqe} 醫學規範化時間: {round(medical_normalization_time - linguistic_extraction_time, 2)} sec{Style.RESET_ALL}")
    sqe_end_time = time.time()
    print(f"{Fore.BLUE}sqe {sqe} 總時間: {round(sqe_end_time - sqe_start_time, 2)} sec{Style.RESET_ALL}")

    # 把整份output.txt檔案傳送到指定的API
    with open(output_txt_path, "r") as file:
        content = file.read()
        url = "http://35.229.136.14:8090/contentListener"
        headers = {
            'Content-Type': 'application/json'
        }
        response = requests.request("POST", url, headers=headers, data=content)


# 修改 Flask 應用程式的 xml_ner 路由，呼叫上述函式
@app.route('/xml_ner', methods=['POST'])
def xml_ner():
    if 'file' not in request.files:
        return jsonify({"error": "請求中沒有檔案部分"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "未選擇檔案"}), 400

    # 儲存檔案到指定目錄
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    random_string = uuid.uuid4().hex
    secure_filename = f"{timestamp}_{file.filename}_{random_string}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename)
    file.save(file_path)

    # 呼叫處理函式
    try:
        # 呼叫 Celery 任務
        task = process_medical_records_task.delay(file_path)
        # process_medical_records(file_path)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "檔案已接收，正在處理", "task_id": task.id}), 202
    # return jsonify({"message": "檔案處理成功", "filename": secure_filename}), 200


# 修改 Flask 應用程式的 txt_ner 路由，呼叫上述函式
@app.route('/txt_ner', methods=['POST'])
def txt_ner():
    # 從request中獲取原始數據
    medical_text = request.get_data(as_text=True)

    # 檢查medical_text是否存在或為空
    if not medical_text:
        return jsonify({"error": "請求中沒有醫學文字內容或內容為空"}), 400

    # 儲存檔案到指定目錄
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    random_string = uuid.uuid4().hex
    secure_filename = f"{timestamp}_medical_text_{random_string}.raw.txt"
    file_path = os.path.join(app.config['PIPE_FOLDER'], secure_filename)
    with open(file_path, "w") as file:
        file.write(medical_text)

    # 呼叫處理函式
    try:
        # 呼叫 Celery 任務
        task = process_medical_text_task.delay(file_path)
        # process_medical_text(file_path)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "文字內容已接收，正在處理", "task_id": task.id}), 202
    # return jsonify({"message": "檔案處理成功", "filename": secure_filename}), 200



if __name__ == '__main__':
    app.run(port=8081, debug=True, use_reloader=False)
