# labeling_transform.py

import sys
import os
import json
import time
from datetime import datetime
import uuid

# Step 1. 解析檔名，檔名範例：../data/pipe_result/200/20241216141342628727_medical_text_f7945fca-480c-41df-9f86-c8dc459d3082_11139_ER_3a23.raw.polishing.llmExtract.txt.json
# Goal: 把實際檔名部分(20241216141342628727_medical_text_f7945fca-480c-41df-9f86-c8dc459d3082_11139_ER_3a23.raw.polishing.llmExtract.txt.json)切為：<時間戳>_medical_text_<UUID>_<病歷號>_<段落類型>_<隨機碼>.raw.polishing.llmExtract.txt.json
# Step 2. 讀取 *.raw.polishing.llmExtract.txt.json 檔案，重新聚合成階層結構：files -> encounters -> paragraphs -> entities
# {
#     "entities": [
#         {
#             "source": "SNOMEDCT_US",
#             "code": "3006004",
#             "code_name": "Disturbance of consciousness (finding)",
#             "text": "Consciousness change since August 11,",
#             "icd10cm": {
#                 "code": "N/A",
#                 "name": "N/A"
#             },
#             "unique": 2,
#             "confidence": 0.6666666666666666,
#             "count": 3,
#             "correctness": true,
#             "insurance_related": false,
#             "remark": ""
#         }
#     ]
# }
# Step 3. 參考table schema，將階層結構轉換成可以塞進SQLite的四張table的SQL語句
# CREATE TABLE "files" (
# 	"file_id"	VARCHAR(36) NOT NULL,
# 	"total_count"	INTEGER NOT NULL DEFAULT 0,
# 	"completed_count"	INTEGER NOT NULL DEFAULT 0,
# 	"status"	VARCHAR(10) NOT NULL DEFAULT 'running',
# 	"created_at"	DATETIME,
# 	"updated_at"	DATETIME
# 	PRIMARY KEY("file_id")
# )
# CREATE TABLE "encounters" (
# 	"encounter_id"	VARCHAR(36) NOT NULL,
# 	"file_id"	VARCHAR(36) NOT NULL,
# 	"sqe"	VARCHAR(36) NOT NULL,
# 	"status"	VARCHAR(10) NOT NULL DEFAULT 'running',
# 	"created_at"	DATETIME,
# 	"updated_at"	DATETIME,
# 	PRIMARY KEY("encounter_id")
# )
# CREATE TABLE "paragraphs" (
# 	"paragraph_id"	VARCHAR(36) NOT NULL,
# 	"encounter_id"	VARCHAR(36) NOT NULL,
# 	"type"	VARCHAR(20) NOT NULL,
# 	"original_path"	VARCHAR(255) NOT NULL,
# 	"polished_path"	VARCHAR(255) NOT NULL,
# 	"status"	VARCHAR(10) NOT NULL DEFAULT 'running',
# 	"running_stage"	VARCHAR(20),
# 	"running_round"	INTEGER NOT NULL DEFAULT 0,
# 	"created_at"	DATETIME,
# 	"updated_at"	DATETIME,
# 	PRIMARY KEY("paragraph_id")
# )
# CREATE TABLE "entities" (
# 	"entity_id"	VARCHAR(36) NOT NULL,
# 	"paragraph_id"	VARCHAR(36) NOT NULL,
# 	"source"	VARCHAR(50) NOT NULL,
# 	"code"	VARCHAR(50) NOT NULL,
# 	"code_name"	VARCHAR(255) NOT NULL,
# 	"text"	VARCHAR(255) NOT NULL,
# 	"icd10_code"	VARCHAR(50),
# 	"icd10_name"	VARCHAR(255),
# 	"unique_count"	INTEGER NOT NULL DEFAULT 0,
# 	"total_count"	INTEGER NOT NULL DEFAULT 0,
# 	"confidence"	FLOAT NOT NULL DEFAULT 1.0,
# 	"correctness"	INTEGER NOT NULL DEFAULT 0,
# 	"is_edit"	INTEGER NOT NULL DEFAULT 0,
# 	"is_manual"	INTEGER DEFAULT 0,
# 	"remark"	INTEGER,
# 	"insurance_related"	INTEGER NOT NULL DEFAULT 0,
# 	"is_deleted"	INTEGER DEFAULT 0,
# 	"created_at"	DATETIME,
# 	"updated_at"	DATETIME,
# 	PRIMARY KEY("entity_id")
# )
# Gola：產出插入語句，類似下方：
# # 插入files表格的SQL語句
# time_stamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")
# file_id = uuid.uuid4()
# # INSERT INTO "files" ("file_id", "total_count", "completed_count", "status", "created_at", "updated_at")
# # VALUES ('value1', 'value2', 'value3', 'value4', 'value5', 'value6');
# files_insert_sql = f"""INSERT INTO "files" ("file_id", "total_count", "completed_count", "status", "created_at", "updated_at")
# VALUES ('{file_id}', '0', '0', 'running', '{time_stamp}', '{time_stamp}');"""
# # 插入encounters表格的SQL語句，數量等同於input_folder_path內的檔案數量/3，因為encounter由三個段落組成
# encounters_insert_sql = f"""INSERT INTO "encounters" ("encounter_id", "file_id", "sqe", "status", "created_at", "updated_at")
# VALUES ('{aggregated_encounter_id}', '{file_id}', '{sqe}', 'running', '{time_stamp}', '{time_stamp}');"""
# # 插入paragraphs表格的SQL語句，數量等同於input_folder_path內的檔案數量，因為每個檔案就是一個段落
# # EmergencyRecord
# # HospitalRecord
# # LaboratoryRecord
# paragraphs_insert_sql = f"""INSERT INTO "paragraphs" ("paragraph_id", "encounter_id", "type", "original_path", "polished_path", "status", "running_stage", "running_round", "created_at", "updated_at")
# VALUES ('{uuid.uuid4()}', '{encounter_id}', '{paragraph_type}', 'original_path', 'polished_path', 'running', 'running_stage', '0', '{time_stamp}', '{time_stamp}');"""
# # 插入entities表格的SQL語句，數量等同於input_folder_path內的檔案內容中所提及的所有entities
# entities_insert_sql = f"""INSERT INTO "entities" ("entity_id", "paragraph_id", "source", "code", "code_name", "text", "icd10_code", "icd10_name", "unique_count", "total_count", "confidence", "correctness", "insurance_related", "remark", "created_at", "updated_at")
# VALUES ('{uuid.uuid4()}', '{paragraph_id}', '{source}', '{code}', '{code_name}', '{text}', '{icd10cm_code}', '{icd10cm_name}', '{unique_count}', '{total_count}', '{confidence}', '{correctness}', '{insurance_related}', '{remark}', '{time_stamp}', '{time_stamp}');"""

input_folder_path = "../data/pipe_result/1001_full_with_icd10cm"
output_folder_path = "../data/pipe_result"
error_folder_path = "../data/pipe_result/error"

paragraph_type_mapping = {
    "ER": "EmergencyRecord",
    "HR": "HospitalRecord",
    "LR": "LaboratoryRecord"
}

time_start = time.time()
time_seg_start = time.time()
handle_count_now = 0
file_id = uuid.uuid4()
time_stamp = datetime.utcnow()
reconstructed_file_json = {
    "file_id": file_id,
    "total_count": 0,
    "completed_count": 0,
    "status": "in_review",
    "created_at": time_stamp,
    "updated_at": time_stamp,
    "encounters": {}
}

reconstrect_count = 0
max_reconstrect_count = sys.maxsize
for file_name in sorted(os.listdir(input_folder_path)):
    # 只處理 *.llmExtract.txt.json 檔案
    if not file_name.endswith(".llmExtract.txt.json"):
        continue
    # Step 1. 解析檔名
    file_name_parts = file_name.split("_")
    # print(file_name_parts)
    time_stamp = datetime.utcnow()
    ori_time_stamp = file_name_parts[0]
    task_uuid = file_name_parts[3]
    paragraph_uuid = uuid.uuid4()
    sqe = file_name_parts[4]
    paragraph_type = paragraph_type_mapping[file_name_parts[5]]
    ori_paragraph_type = file_name_parts[5]
    random_code = file_name_parts[6].split(".")[0]

    # 用sqe檢查encounter是否已經存在，若不存在則新增
    if sqe not in reconstructed_file_json["encounters"]:
        reconstructed_file_json["encounters"][sqe] = {
            "encounter_id": uuid.uuid4(),
            "file_id": file_id,
            "sqe": sqe,
            "status": "running",
            "created_at": time_stamp,
            "updated_at": time_stamp,
            "paragraphs": {}
        }
    
    # 用paragraph_type檢查paragraph是否已經存在，若重複存在則是異常，複製一份到error_folder_path(不是移動)
    if paragraph_type in reconstructed_file_json["encounters"][sqe]["paragraphs"]:
        error_file_path = f"{error_folder_path}/{file_name}"
        with open(f"{input_folder_path}/{file_name}", "r") as file:
            content = file.read()
        with open(error_file_path, "w") as file:
            file.write(content)
        continue
    else:
        reconstructed_file_json["encounters"][sqe]["paragraphs"][paragraph_type] = {
            "paragraph_id": paragraph_uuid,
            "encounter_id": reconstructed_file_json["encounters"][sqe]["encounter_id"],
            "type": paragraph_type,
            "original_path": f"data/1001_full_no_extract/{ori_time_stamp}_medical_text_{task_uuid}_{sqe}_{ori_paragraph_type}_{random_code}.raw.txt",
            "polished_path": f"data/1001_full_no_extract/{ori_time_stamp}_medical_text_{task_uuid}_{sqe}_{ori_paragraph_type}_{random_code}.raw.polishing.txt",
            "status": "in_review",
            "running_stage": "done",
            "running_round": 3,
            "created_at": time_stamp,
            "updated_at": time_stamp,
            "entities": []
        }

    # Step 2. 讀取 *.raw.polishing.llmExtract.txt.json 檔案
    with open(f"{input_folder_path}/{file_name}", "r") as file:
        llm_extract_json = json.load(file)
    
    for entity in llm_extract_json["entities"]:
        icd10cm_result = {
            "code": entity["icd10cm"]["code"],
            "name": entity["icd10cm"]["name"]
        }
        reconstructed_entity = {}
        reconstructed_entity["source"] = entity["source"]
        reconstructed_entity["code"] = entity["code"]
        reconstructed_entity["code_name"] = entity["code_name"]
        reconstructed_entity["text"] = entity["text"]
        reconstructed_entity["icd10cm"] = icd10cm_result
        reconstructed_entity["unique"] = entity["unique"]
        reconstructed_entity["confidence"] = entity["confidence"]
        reconstructed_entity["count"] = entity["count"]
        reconstructed_entity["correctness"] = True
        reconstructed_entity["insurance_related"] = False
        reconstructed_entity["remark"] = ""
        reconstructed_file_json["encounters"][sqe]["paragraphs"][paragraph_type]["entities"].append(reconstructed_entity)

    reconstrect_count += 1
    if reconstrect_count >= max_reconstrect_count:
        break
    if reconstrect_count % 100 == 0:
        print(f"Reconstructed {reconstrect_count} files, time spent: {time.time() - time_seg_start} seconds")
        time_seg_start = time.time()

# update total_count by encounters count
reconstructed_file_json["total_count"] = int(reconstrect_count / 3)

print(f"Reconstructed {reconstrect_count} files, total time spent: {time.time() - time_start} seconds")
time_start = time.time()

# Step 3. 參考table schema，將階層結構轉換成可以塞進SQLite的四張table的SQL語句
output_file_path = f"{output_folder_path}/insert_sql_1001.sql"
# files
files_insert_sql = f"""INSERT INTO "files" ("file_id", "total_count", "completed_count", "status", "created_at", "updated_at")
    VALUES ('{reconstructed_file_json["file_id"]}', {reconstructed_file_json["total_count"]}, {reconstructed_file_json["completed_count"]}, '{reconstructed_file_json["status"]}', '{reconstructed_file_json["created_at"]}', '{reconstructed_file_json["updated_at"]}');


"""
with open(output_file_path, "w") as file:
    # 正式sql語句前面增加一行註解
    file.write("-- Insert files\n\n")
    file.write(files_insert_sql)
    # encounters
    encounter_count = 0
    max_encounter_count = len(reconstructed_file_json["encounters"])
    # max_encounter_count = 2
    for sqe in reconstructed_file_json["encounters"]:
        encounter = reconstructed_file_json["encounters"][sqe]
        aggregated_encounter_id = encounter["encounter_id"]
        encounters_insert_sql = f"""INSERT INTO "encounters" ("encounter_id", "file_id", "sqe", "status", "created_at", "updated_at")
    VALUES ('{aggregated_encounter_id}', '{file_id}', '{sqe}', 'in_review', '{time_stamp}', '{time_stamp}');


"""

        # 正式sql語句前面增加一行註解
        file.write(f"-- Insert encounters for sqe: {sqe}\n\n")
        file.write(encounters_insert_sql)
        for paragraph_type in encounter["paragraphs"]:
            paragraph = encounter["paragraphs"][paragraph_type]
            paragraph_id = paragraph["paragraph_id"]
            paragraphs_insert_sql = f"""INSERT INTO "paragraphs" ("paragraph_id", "encounter_id", "type", "original_path", "polished_path", "status", "running_stage", "running_round", "created_at", "updated_at")
    VALUES ('{paragraph_id}', '{aggregated_encounter_id}', '{paragraph_type}', '{paragraph["original_path"]}', '{paragraph["polished_path"]}', '{paragraph["status"]}', '{paragraph["running_stage"]}', {paragraph["running_round"]}, '{paragraph["created_at"]}', '{paragraph["updated_at"]}');


"""         
            # 正式sql語句前面增加一行註解
            file.write(f"-- Insert paragraphs for sqe & paragraph_type: {sqe}-{paragraph_type}\n\n")
            file.write(paragraphs_insert_sql)
            entities_insert_sql = f"""INSERT INTO "entities" ("entity_id", "paragraph_id", "source", "code", "code_name", "text", "icd10_code", "icd10_name", "unique_count", "total_count", "confidence", "correctness", "is_edit", "is_manual", "remark", "insurance_related", "is_deleted", "created_at", "updated_at")
VALUES
"""
            if len(paragraph["entities"]) == 0:
                # 正式sql語句前面增加一行註解
                file.write(f"-- No entity in paragraph for sqe & paragraph_type: {sqe}-{paragraph_type}\n\n")
                continue
            for entity in paragraph["entities"]:
                source = entity["source"]
                code = entity["code"]
                code_name = entity["code_name"].replace("\'", "\'\'")
                text = entity["text"].replace("\'", "\'\'")
                icd10cm_code = entity["icd10cm"]["code"]
                icd10cm_name = entity["icd10cm"]["name"].replace("\'", "\'\'")
                unique_count = entity["unique"]
                total_count = entity["count"]
                confidence = entity["confidence"]
                correctness = 1 if entity["correctness"] else 0
                is_edit = 0
                is_manual = 0
                remark = entity["remark"]
                insurance_related = 1 if entity["insurance_related"] else 0
                is_deleted = 0
                time_stamp = datetime.utcnow()
                if icd10cm_code == "N/A":
                    entities_insert_sql += f""" ('{uuid.uuid4()}', '{paragraph_id}', '{source}', '{code}', '{code_name}', '{text}', NULL, NULL, {unique_count}, {total_count}, {confidence}, {correctness}, {is_edit}, {is_manual}, NULL, {insurance_related}, {is_deleted}, '{time_stamp}', '{time_stamp}'),
"""
                else:
                    # print(icd10cm_code)
                    entities_insert_sql += f""" ('{uuid.uuid4()}', '{paragraph_id}', '{source}', '{code}', '{code_name}', '{text}', '{icd10cm_code}', '{icd10cm_name}', {unique_count}, {total_count}, {confidence}, {correctness}, {is_edit}, {is_manual}, NULL, {insurance_related}, {is_deleted}, '{time_stamp}', '{time_stamp}'),
"""
            # 在最後一個換行符號前面加上一個分號
            entities_insert_sql = entities_insert_sql[:-2] + ";\n\n\n"
            # 正式sql語句前面增加一行註解
            file.write(f"-- Insert entities for paragraph_id: {paragraph_id}\n\n")
            file.write(entities_insert_sql)

        encounter_count += 1
        if encounter_count >= max_encounter_count:
            break
        if encounter_count % 100 == 0:
            print(f"Generate {encounter_count} encounters insert queries, time spent: {time.time() - time_seg_start} seconds")
            time_seg_start = time.time()

    print(f"Generate {encounter_count} encounters insert queries, total time spent: {time.time() - time_start} seconds")



