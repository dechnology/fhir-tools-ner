"""
非結構化病歷工具處理流程:
1. Preprocess
2. LLM based medical Entity Extraction (GPT-4o: O, BioBERT: X)
3. LLM Polishing
    3-1. segmentation
    3-2. translation, normalization, polishing, and abbreviation expansion (word expansion)
    3-3. merge all responses to a single Medical record string and save to a file
4. Linguistic Extraction
5. Merge Tagging Results
6. (if a MedCAT entity is found in an LLM non-entity) LLM Re-evaluation
7. Concept Mapping
    7-0. Blacklist (移除無意義概念)
    7-1. Dictionary lookup
        7-1-1. MedCAT entity Part:
            -> Chunking (LLM or 長詞優先策略）之STR有值 -> 進入7.4，直接答案(提早結束)
            -> 長詞結合結果視為部分match -> 進入7.2
        7-1-2. LLM entity 優先序算法
            * 欄位(CODE、STR)交集有值 -> 進入7.4，直接答案(提早結束)
            * 欄位(CODE、STR)聯集有值 -> STR的部分進入7.3，但是CODE檢索結果必須併入7.4
            （或是）
                STR完全match -> 補CODE -> 進入7.3
                STR部分match -> LLM決定 -> 進入7.2
    7-2. 沒有完全符合STR的子字串，以LLM取得STR關鍵字排序，逐步縮小範圍，空集合的前一次搜尋結果即為RAG結果 -> LLM決定
    7-3. Cosine Similarity (or 加入 Levenshtein distance) Threshold
    7-4. Concept Resolution
8. Medical Normalization
"""

import os
import sys
import time
import shutil
import subprocess
import xml.etree.ElementTree as ET
import json
from collections import defaultdict
from pydantic import BaseModel
start_time = time.time()
from medcat.cat import CAT
from openai import OpenAI
import_time = time.time()
print(f"Libraries imported in {import_time - start_time:.2f} seconds.")


# ===== Step 0. Preparation =====
#  -> Load the model pack
# ===============================
# Load the model pack
cat = CAT.load_model_pack('../models/mc_modelpack_snomed_int_16_mar_2022_25be3857ba34bdd5.zip')
model_loaded_time = time.time()
print(f"Model loaded in {model_loaded_time - import_time:.2f} seconds.")


# ===== Step 1. Preprocess =====
#  -> 定義 Pydantic 模型結構
# ===============================
# 定義 Pydantic 模型結構
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

# 初始化OpenAI客户端
client = OpenAI(api_key="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")

# 建立benchmark，紀錄初始時間
import time
start_time = time.time()

# 開啟一個xlsx檔案，裡面每個row都是一個病人的病歷
import pandas as pd
file_name = "Testing EMR"
df = pd.read_excel(f"../data/raw/{file_name}.xlsx")
# 依序處理每個病人的病歷
# 每個row分別有四個欄位：seq, 急診去辨識病歷, 住院去辨識病歷, 檢驗紀錄
# 我們要把他重新拼裝為一個以seq為檔名的txt檔案，並以＝＝＝＝＝<欄位名稱>＝＝＝＝＝\n\n<欄位內容>的形式存起來
for index, row in df.iterrows():
    row_start_time = time.time()
    with open(f"../data/{file_name}_v3plus_{index+1}.raw.txt", "w") as file:
        file.write(f"==========sqe==========\n\n{row['sqe']}\n\n==========急診去辨識病歷==========\n\n{row['急診去辨識病歷']}\n\n==========住院去辨識病歷==========\n\n{row['住院去辨識病歷']}\n\n==========檢驗紀錄==========\n\n{row['檢驗紀錄']}")


    # 從f"../data/{file_name}_v3plus.{index+1}.raw.txt"讀取content
    content = ""
    with open(f"../data/{file_name}_v3plus_{index+1}.raw.txt", "r") as file:
        content = file.read()
        # print("split_content:")
        # print(content)

    # 调用API进行标准化转换
    standardization_completion = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "system", "content": "You are an expert in clinical text standardization. Convert the following unstructured medical text into standardized English format."},
            {"role": "user", "content": content}
        ]
    )

    # 获取标准化后的文本
    standardized_content = standardization_completion.choices[0].message.content

    # 儲存標準化後的文本到f"../data/{file_name}_v3plus_{index+1}.raw.standardized.txt"
    with open(f"../data/{file_name}_v3plus_{index+1}.raw.standardized.txt", "w") as file:
        file.write(standardized_content)
    row_standardized_time = time.time()
    print(f"Row {index+1} standardized time: {row_standardized_time - row_start_time} seconds")

    # 输出标准化后的文本（可选）
    # print("Standardized Content:")
    # print(standardized_content)

    # 清空目錄
    input_dir = "/Users/yangnoahlin/Downloads/apache-ctakes-4.0.0.1/data/input"
    output_dir = "/Users/yangnoahlin/Downloads/apache-ctakes-4.0.0.1/data/output"
    if os.path.exists(input_dir):
        shutil.rmtree(input_dir)
    os.makedirs(input_dir)

    # 移动指定文件到输入目录
    source_file = f"../data/{file_name}_v3plus_{index+1}.raw.standardized.txt"
    destination_file = os.path.join(input_dir, f"{file_name}_v3plus_{index+1}.raw.standardized.txt")
    shutil.copy2(source_file, destination_file)

    # 调用外部程序
    result = subprocess.run([
        "/Users/yangnoahlin/Downloads/apache-ctakes-4.0.0.1/bin/runClinicalPipeline.sh",
        "--key", "08b35fd3-57c5-4548-9463-b876602ed823",
        "--inputDir", input_dir,
        "--xmiOut", output_dir
        ], capture_output=True, text=True)
    
    cTAKES_output_file = f"{output_dir}/{file_name}_v3plus_{index+1}.raw.standardized.txt.xmi"
    if result.returncode == 0:
        print("cTAKES Pipeline executed successfully")
        print(result.stdout)
    else:
        print("cTAKES Pipeline failed with return code", result.returncode)
        print(result.stderr)
        print("create a empty file to ensure the program can continue")
        with open(cTAKES_output_file, "w") as file:
            file.write("")


    # 读取并解析 XMI 文件
    tree = ET.parse(cTAKES_output_file)
    root = tree.getroot()

    # 定义命名空间，如果 XMI 文件中有命名空间前缀，需要在此处定义
    namespaces = {
        'refsem': "http:///org/apache/ctakes/typesystem/type/refsem.ecore"
    }

    # 创建一个默认字典来存储重组的数据结构
    data = defaultdict(lambda: defaultdict(list))

    # 提取所有 refsem:UmlsConcept 标签
    umls_concepts = root.findall('.//refsem:UmlsConcept', namespaces)

    for concept in umls_concepts:
        coding_scheme = concept.get('codingScheme')
        preferred_text = concept.get('preferredText')
        code = concept.get('code')
        cui = concept.get('cui')
        tui = concept.get('tui')
        
        # 将数据加入到重组的结构中
        data[coding_scheme][preferred_text].append({
            "code": code,
            "cui": cui,
            "tui": tui
        })

    # 将默认字典转换为普通字典
    data_dict = {k: dict(v) for k, v in data.items()}

    # 转换为JSON格式的字符串
    ctakes_json_data = json.dumps(data_dict)

    
    # create a new file named f"../data/{file_name}_v3plus_{index+1}.raw.standardized.cTAKES.txt" and write the content of source_file and cTAKES_output_file into it
    standardized_with_cTAKES_file = f"../data/{file_name}_v3plus_{index+1}.raw.standardized.cTAKES.txt"
    with open(standardized_with_cTAKES_file, "w") as file:
        file.write(f"{content}\n\n==========cTAKES detection result==========\n\n")
        with open(cTAKES_output_file, "r") as cTAKES_output:
            file.write(ctakes_json_data)
    standardized_with_cTAKES_content = ""
    with open(standardized_with_cTAKES_file, "r") as file:
        standardized_with_cTAKES_content = file.read()

    
    row_run_cTAKES_time = time.time()
    print(f"Row {index+1} run cTAKES time: {row_run_cTAKES_time - row_standardized_time} seconds")

    # 调用API并传递模型
    # standardized_with_cTAKES_content handler
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "system", "content": """
             You are an expert in structured medical data extraction, specializing in SNOMED_CT, RxNorm, and LOINC.
             Your task is to analyze medical text in "急診去辨識病歷", "住院去辨識病歷" and "檢驗紀錄" and should identify and extract the relevant SNOMED_CT, RxNorm, and LOINC codes wherever applicable.
             Convert the information into the given structured format and NOT to deduplicate the information:
            
            - `SNOMED_CT`: A list of dictionaries, each containing the following keys:
                - `raw_text_as_clues`: The raw text list you found in the original content (copy the raw text chunk as clue to here).
                - `implies_concepts_FSN`: The fully specified name (FSN) list of the concept.
                - `id`: The unique SNOMED CT code from dictionary.

            - `LOINC`: A list of dictionaries, each containing the following keys:
                - `raw_text_as_clues`: The raw text list you found in the original content (copy the raw text chunk as clue to here).
                - `implies_concepts_FSN`: The fully specified name (FSN) list of the [test / measurement].
                - `id`: The unique LOINC code from dictionary.

            - `RxNorm`: A list of dictionaries, each containing the following keys:
                - `raw_text_as_clues`: The raw text list you found in the original content (copy the raw text chunk as clue to here).
                - `implies_concepts_FSN`: The fully specified name (FSN) list of the drug.
                - `id`: The unique RxNorm code from dictionary.
            """},
            {"role": "user", "content": standardized_with_cTAKES_content}
        ],
        response_format=JSONStructure,
    )

    # 获取解析后的结构化数据
    parsed_response = completion.choices[0].message.parsed

    # 输出结果
    # print("parsed_response:")
    # print(parsed_response.model_dump_json(indent=2))

    # 儲存萃取出的結構化資訊到f"../data/{file_name}_v3plus_{index+1}.raw.(standardized).cTAKES.LLM.txt"
    with open(f"../data/{file_name}_v3plus_{index+1}.raw.(standardized).cTAKES.LLM.txt", "w") as file:
        file.write(parsed_response.model_dump_json(indent=2))
    row_format_time = time.time()
    print(f"Row {index+1} format time: {row_format_time - row_standardized_time} seconds")
    row_end_time = time.time()
    print(f"Row {index+1} total time: {row_end_time - row_start_time} seconds")

end_time = time.time()
print(f"Total time: {end_time - start_time} seconds")


# Concept Names and Sources (File = MRCONSO.RRF)
# https://www.ncbi.nlm.nih.gov/books/NBK9685/table/ch03.T.concept_names_and_sources_file_mr/

# Abbreviations Used in Data Elements - 2024AA
# https://www.nlm.nih.gov/research/umls/knowledge_sources/metathesaurus/release/abbreviations.html

"""
C0484730|ENG|P|L13443801|PF|S16439235|Y|A27103485||10485-1||LNC|LN|10485-1|Glucagon Ag:PrThr:Pt:Tiss:Ord:Immune stain|0|N|256|
----------
CUI (Concept Unique Identifier)
LAT (Language of Terms)
    ENG
TS (Term Status)
    P	Preferred LUI of the CUI
    S	Non-Preferred LUI of the CUI
LUI (Unique Identifier for Term)
STT (Semantic Type Tree Number)
    PF	Preferred form of term
    VCW	Case and word-order variant of the preferred form
    VC	Case variant of the preferred form
    VO	Variant of the preferred form
    VW	Word-order variant of the preferred form
SUI (Unique Identifier for String)
ISPREF (Is Preferred Term)
    Atom status - preferred (Y) or not (N) for this string within this concept
AUI (Unique Identifier for Atom)
SAUI (Source AUI)
SCUI (Source Concept Identifier)
SDUI (Source Descriptor Identifier)
SAB (Source Abbreviation)
    ICD10
    LNC
    RXNORM
    SNOMEDCT_US
TTY (Term Type in Source)
    https://www.nlm.nih.gov/research/umls/knowledge_sources/metathesaurus/release/precedence_suppressibility.html
    https://www.nlm.nih.gov/research/umls/knowledge_sources/metathesaurus/release/abbreviations.html
    ICD10
        PT	Designated preferred name
        PX	Expanded preferred terms
        PS	Short forms that needed full specification
        HT	Hierarchical term
        HX	Expanded version of short hierarchical term
        HS	Short or alternate version of hierarchical term
    LNC
        LN	    LOINC official fully specified name
        MTH_LN	Metathesaurus official fully specified name with expanded abbreviations
        OSN	    Official short name
        DN	    Display Name
        CN	    LOINC official component name
        MTH_CN	Metathesaurus Component, with abbreviations expanded
        LPDN	LOINC parts display name
        LPN	    LOINC parts name
        HC	    Hierarchical class
        HS	    Short or alternate version of hierarchical term
        OLC	    Obsolete Long common name
        LC	    Long common name
        LS	    Expanded system/sample type
        LG	    LOINC group
        LA	    LOINC answer
        LO      Obsolete official fully specified name
        MTH_LO  Metathesaurus Expanded LOINC obsolete fully specified name
        OOSN    Obsolete official short name
        OLG     Obsolete LOINC group name
    RXNORM
        https://www.nlm.nih.gov/research/umls/rxnorm/docs/appendix5.html
        IN	    Ingredient	                                A compound or moiety that gives the drug its distinctive clinical properties. Ingredients generally use the United States Adopted Name (USAN).
        PIN	    Precise Ingredient	                        A specified form of the ingredient that may or may not be clinically active. Most precise ingredients are salt or isomer forms.
        MIN	    Multiple Ingredients	                    Two or more ingredients appearing together in a single drug preparation, created from SCDF. In rare cases when IN/PIN or PIN/PIN combinations of the same base ingredient exist, created from SCD.
        SCDC	Semantic Clinical Drug Component	        Ingredient + Strength
        SCDF	Semantic Clinical Drug Form                 Ingredient + Dose Form
        SCDFP	Semantic Clinical Drug Form                 Precise	Precise Ingredient + Dose Form
                                                            Exists only if the Basis of Strength (BoSS) is a precise ingredient for a related fully specified drug name.
        SCDG	Semantic Clinical Drug Group	            Ingredient + Dose Form Group
        SCDGP	Semantic Clinical Drug Form Group Precise	Precise Ingredient + Dose Form Group
                                                            Exists only if the Basis of Strength (BoSS) is a precise ingredient for a related fully specified drug name.	warfarin sodium Pill
        SCD	    Semantic Clinical Drug	                    Ingredient + Strength + Dose Form
        GPCK	Generic Pack	                            {# (Ingredient + Strength + Dose Form) / # (Ingredient + Strength + Dose Form)} Pack
        BN	    Brand Name	                                A proprietary name for a family of products containing a specific active ingredient.
        SBDC	Semantic Branded Drug Component	            Ingredient + Strength + Brand Name
        SBDF	Semantic Branded Drug Form	                Ingredient + Dose Form + Brand Name
        SBDFP	Semantic Branded Drug Form Precise	        Ingredient + Dose Form + Brand Name
                                                            Exists only if the Basis of Strength (BoSS) is a precise ingredient for a related fully specified drug name
        SBDG	Semantic Branded Drug Group	                Brand Name + Dose Form Group
        SBD	    Semantic Branded Drug	                    Ingredient + Strength + Dose Form + Brand Name
        BPCK	Brand Name Pack	                            {# (Ingredient Strength Dose Form) / # (Ingredient Strength Dose Form)} Pack [Brand Name]
        DF	    Dose Form	                                See Appendix 2 for a full list of Dose Forms.
        DFG	    Dose Form Group	                            See Appendix 3 for a full list of Dose Form Groups.

        PSN	    Prescribable Name	                        Synonym of another TTY, given for clarity and for display purposes in electronic prescribing applications. Only one PSN per concept.
        SY	    Synonym	                                    Synonym of another TTY, given for clarity. Zero or one-to-many SY per concept.
        TMSY	Tall Man Lettering Synonym	                Tall Man Lettering synonym of another TTY, given to distinguish between commonly confused drugs. Zero or one-to-many TMSY per concept.
    SNOMEDCT_US
        PT          Designated preferred name
        SY          Designated synonym
        FN          Full form of descriptor
        PTGB	    British Preferred Term
        SYGB	    British Synonym
        MTH_PT	    Metathesaurus Preferred Term
        MTH_FN	    Metathesaurus Full Form of Descriptor
        MTH_SY	    Metathesaurus Designated Synonym
        MTH_PTGB	Metathesaurus-supplied form of British Preferred Term
        MTH_SYGB	Metathesaurus-supplied form of British Synonym

CODE (Code in Source)
STR (String)
SRL (Source Restriction Level)
    0	No additional restrictions; general terms of the license agreement apply.
    1	General terms + additional restrictions in category 12.1
    2	General terms + additional restrictions in category 12.2
    3	General terms + additional restrictions in category 12.3
    4	General terms + additional restrictions in category 12.4
    9	General terms + SNOMED CT Affiliate License in Appendix 2
SUPPRESS (Suppressible Flag)
    SUPPRESS	SUPPRESS Description
    E	Suppressible due to editor decision
    N	Not suppressible
    O	Obsolete, SAB,TTY may be independently suppressible
    Y	Suppressible due to SAB,TTY
        Suppressibility not yet assigned by the UMLS
CVF (Content View Flag)
    CUI         Content View	                            CV_CODE	CV_DESCRIPTION
    C1700357	MetaMap NLP View	                        256	    This content view is built from mrconso.filtered.strict (a subset of RRF MRCONSO) and converted into an AUI list based on the previous release. This view is not algorithmically generated during Metathesaurus construction.
    C2711988	CORE Problem List Subset of SNOMED CT	    2048	This content view contains the subset of SNOMED CT concepts that are most frequently used in problem lists. The subset is derived from datasets from large health care institutions. The most commonly used problem list terms are mapped to SNOMED CT and other UMLS sources. The use of SNOMED CT contents in this subset is subject to the SNOMED CT license requirements. The use of SNOMED CT is free in IHTSDO member countries (including the U.S.) and low income countries.
                                                                    The creation of this content view is based on the list of SNOMED CT concept IDs in the latest release of the CORE Problem List Subset of SNOMED CT, excluding those that are retired from the Subset. It contains all atoms linked to that SNOMED CT concept with LAT=ENG and SUPPRESS=N.
    C3503753	RxNorm Current Prescribable Content Subset	4096	This content view contains the subset of RXNORM concepts that are marked as prescribable in the RXNCONSO.RRF file.
    C3812142	SNOMEDCT US Extension Subset	            8192	This content view allows users to easily identify atoms in the UMLS that come from the US Extension to SNOMED CT and carry the NLM Module ID of '731000124108'.
    C4048847	LOINC Universal Lab Orders Value Set	    16384	The Universal Lab Order Codes Value Set from LOINC is a collection of the most frequent lab orders. It was created for use by developers of provider order entry systems that would deliver them in HL7 messages to laboratories where they could be understood and fulfilled. The content view is defined as any atom belonging to sab = 'LNC' with the attribute of UNIVERSAL_LAB_ORDERS_VALUE_SET = TRUE.
    C4050460	LOINC Panels and Forms	                    32768	This content view contains any LOINC identifier used as a grouper containing a set of child LOINC data elements. Any UMLS AUI sab = 'LNC' and tty='LN' with the attribute of 'PANEL_TYPE' belongs to this content view.
"""

# ===== Step 3. Linguistic Extraction =====
#  -> Open the input file to read the text
#  -> Extract entities from the text
# =========================================
# Open the input file to read the text
with open("../data/Testing EMR_v3plus_1.raw.standardized.txt", "r") as file:
    text = file.read()
    entities = cat.get_entities(text)
entities_extracted_time = time.time()
print(f"Entities extracted in {entities_extracted_time - model_loaded_time:.2f} seconds.")

# Save the entities to a JSON file
with open("../data/Testing EMR_v4_1_MedCAT.json", "w") as json_file:
    json.dump(entities, json_file, indent=2)
json_saved_time = time.time()
print(f"Entities have been saved to '../data/Testing EMR_v4_1_MedCAT.json' in {json_saved_time - entities_extracted_time:.2f} seconds.")
