import os
import shutil
from pathlib import Path

def count_llm_extract_files(folder_path):
    # 確認資料夾是否存在
    if not os.path.exists(folder_path):
        print(f"資料夾 {folder_path} 不存在！")
        return 0

    # 檢查資料夾中的檔案
    files = os.listdir(folder_path)
    count = sum(1 for file in files if file.endswith('llmExtract.txt'))
    
    print(f"資料夾 {folder_path} 中有 {count} 個以 'llmExtract.txt' 結尾的檔案。")
    return count


def copy_full_segment_files(input_folder_path, output_folder_path):
    # 確保輸出資料夾存在
    os.makedirs(output_folder_path, exist_ok=True)

    # 初始化用於追蹤檔案類型的字典
    file_tracker = {}

    # 遍歷輸入資料夾中的檔案
    for root, _, files in os.walk(input_folder_path):
        for file in files:
            # 獲取檔案的完整路徑
            file_path = Path(root) / file
            # 解析檔名細節
            parts = file.split("_")
            if len(parts) >= 5:
                identifier = parts[4]  # 提取檔案的唯一 ID
                file_type = parts[5]  # 提取檔案類型 (如 ER, HR, LR)
                if identifier not in file_tracker:
                    file_tracker[identifier] = {
                        "ER": [],
                        "HR": [],
                        "LR": []
                    }
                file_tracker[identifier][file_type].append(file_path)

    # 找到符合條件的檔案 ID
    required_file_types = {"ER", "HR", "LR"}
    file_suffixes = {".raw.txt", ".raw.polishing.txt", ".raw.polishing.llmExtract.txt"}
    matching_ids = []
    incomplete_ids = []

    # sort
    file_tracker = dict(sorted(file_tracker.items(), key=lambda item: item[0]))

    for identifier, files in file_tracker.items():
        if files.keys() == required_file_types:
            print(identifier, files.keys(), "都存在")
            print(files)
        else:
            continue
        
        # 檢查file_suffixes是否在每個檔案類型底下都有
        all_suffixes_exist = True
        for file_type, file_list in files.items():
            for suffix in file_suffixes:
                suffix_found = False
                for file_path in file_list:
                    if file_path.name.endswith(suffix):
                        suffix_found = True
                        break
                if not suffix_found:
                    all_suffixes_exist = False
                    break
            if not all_suffixes_exist:
                break
        if all_suffixes_exist:
            matching_ids.append(identifier)
        else:
            incomplete_ids.append(identifier)

    # 將符合條件的檔案複製到輸出資料夾
    count = 0
    # for identifier in matching_ids:
    #     for file_type, file_list in file_tracker[identifier].items():
    #         for file_path in file_list:
    #             output_file_path = Path(output_folder_path) / file_path.name
    #             shutil.copy(file_path, output_file_path)
    #             print(f"已複製檔案 '{file_path}' 到 '{output_file_path}'")
    #             count += 1
    
    print("符合條件的檔案 ID:", matching_ids)
    print("不符合條件的檔案 ID:", incomplete_ids)
    print("總共複製了", count, "個檔案。")

# 使用者可以修改資料夾路徑
input_folder_path = "../data/pipe_result/1000"
output_folder_path = "../data/pipe_result/1001_drop"
count_llm_extract_files(input_folder_path)
matching_ids = copy_full_segment_files(input_folder_path, output_folder_path)