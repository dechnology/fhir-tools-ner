"""
非結構化病歷工具處理流程:
1. Preprocess (所有匯出格式轉換為txt, 目前只有xlsx)
2. LLM Polishing
    2-1. segmentation
    2-2. translation, normalization, polishing, and abbreviation expansion (word expansion)
    2-3. merge all responses to a single Medical record string and save to a file
3. Linguistic Extraction (MedCAT)，一次一句
    3-1. 執行MedCAT之後，連結到UMLS的條目
    3-2. LLM based medical Entity Extraction (Concept Mapping)
        4-0. Blacklist (移除無意義概念，暫時不用)
        4-1. Dictionary lookup (N=100)
            -> 左右entity各自找出條目後聯集，使找到的UMLS條目數量在30條以內，若大於N條，則逐一加入夾在中間的token，直到找到的UMLS條目數量在N條以內
        4-2. Concept Resolution
            ->直接計算~Entiry_A~Entity_B~的字串嵌入值，比對出最相近的條目
            or
            ->用~Entiry_A~Entity_B~的字串請AI幫忙找出最相近的條目（~中沒有Entity）
4. Medical Normalization (ICD10 to SNOMED_CT, the final output is SNOMED_CT, RxNORM, and LOINC)
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
import pandas as pd
from openai import OpenAI
from colorama import Fore, Style
start_time = time.time()
print(f"{Fore.GREEN}MedCAT package importing...{Style.RESET_ALL}", end="", flush=True)
from medcat.cat import CAT
import_time = time.time()
print(f"{Fore.GREEN} done. ({import_time - start_time:.2f} sec){Style.RESET_ALL}")


# ===== Parameters =====
#  -> system parameters
#  -> target setting
# ===============================
# system parameters
tool_name = "fhir_tool_1"
version = "v1"
preview_count = 5
# target setting
model = "mc_modelpack_snomed_int_16_mar_2022_25be3857ba34bdd5.zip"
file = "TestingMedicalRecord.xlsx"
umls_sub_dict = "filtered_data.csv"
# helper
NEWLINE = "\n"
NONE_SYMBOL = "-"


# ===== Step 0. Preparation =====
#  -> Load the model pack
#  -> Define the Pydantic model structure
# ===============================
# Load the model pack
print(f"{Fore.GREEN}MedCAT Model and UMLS Dictionary Subset loading...{NEWLINE}{Style.RESET_ALL}", end="", flush=True)
cat = CAT.load_model_pack(f'../models/{model}')
print(f"{Fore.GREEN}waiting for UMLS Dictionary Subset...{NEWLINE}{Style.RESET_ALL}", end="", flush=True)
umls_df = pd.read_csv(f"../data/dict/{umls_sub_dict}", sep='|', header=None)
umls_df.columns = [
    'CUI', 'LAT', 'TS', 'LUI', 'STT', 'SUI', 'ISPREF', 'AUI', 'SAUI', 
    'SCUI', 'SDUI', 'SAB', 'TTY', 'CODE', 'STR', 'SRL', 'SUPPRESS', 'CVF'
]
print(umls_df.head())
model_loaded_time = time.time()
print(f"{Fore.GREEN} done. ({model_loaded_time - import_time:.2f} sec){Style.RESET_ALL}")

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
preprocess_time = time.time()


# ===== Step 1. Preprocess =====
#  -> 判斷格式是否支援
#  -> 轉換所有支援格式為txt (目前只處理一個xlsx檔案)
#  -> 將每個病人的病歷分別存成一個txt檔案
# ===============================
# 開啟一個xlsx檔案，裡面每個row都是一個病人的病歷
# get file name and extension
# 藉由最後一個.的位置得到檔案名稱和副檔名
file_name = file[:file.rfind(".")]
file_ext = file[file.rfind(".")+1:]
df = pd.read_excel(f"../data/input/{file}")
# 依序處理每個病人的病歷
# 每個row分別有四個欄位：sqe, 急診去辨識病歷, 住院去辨識病歷, 檢驗紀錄
# 我們要把他重新拼裝為一個以sqe為檔名的txt檔案，並以**********<欄位名稱>**********\n\n<欄位內容>的形式存起來
for index, row in df.iterrows():
    if index != 1:
        continue
    sqe_start_time = time.time()
    with open(f"../data/pipe_result/{file_name}_{tool_name}_{version}_{row['sqe']}.raw.txt", "w") as file:
        file.write(f"**********急診去辨識病歷**********\n\n{row['急診去辨識病歷']}\n\n**********住院去辨識病歷**********\n\n{row['住院去辨識病歷']}\n\n**********檢驗紀錄**********\n\n{row['檢驗紀錄']}")


    # ===== Step 2. LLM Polishing =====
    #  -> load file content
    #  -> segmentation
    #  -> translation, normalization, polishing, and abbreviation expansion (word expansion)
    #  -> merge all responses to a single Medical record string and save to a file
    # ===============================
    # 從f"../data/pipe_result/{file_name}_{tool_name}_v1.{row['sqe']}.raw.txt"讀取content
    content = ""
    with open(f"../data/pipe_result/{file_name}_{tool_name}_{version}_{row['sqe']}.raw.txt", "r") as file:
        content = file.read()
        # print("split_content:")
        # print(content)

    # 將content拆分成多個段落
    split_content = content.split("\n\n")
    # 精準切割：
    # 1. 在不破壞文意的情況下，將每個段落切割成多個子段落
    # 2. 如果每個子段落的長度大於500，則將其拆分成多個孫段落
    # TODO: 待實作

    # 使用OpenAI的API對每個段落進行翻譯、標準化、精煉和縮寫展開（詞展開）
    standardized_content = ""
    for i in range(len(split_content)):
        # 取得段落 split_content[i] 的前N行
        lines = split_content[i].splitlines()
        print(f"{Fore.YELLOW}{NEWLINE.join(lines[:preview_count])}{f' [... {len(lines)} lines]' if len(lines) > preview_count else ''}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}sqe {row['sqe']}: {i+1}/{len(split_content)} polishing...{Style.RESET_ALL}", end="", flush=True)
        seqment_start_time = time.time()
        standardization_completion = client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": """translation the user context to english and execute normalization, polishing, and abbreviation expansion (word expansion)."""},
                {"role": "user", "content": split_content[i]}
            ]
        )
        rewtire_completion = client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": """Rewrite the medical record using the  UMLS concept (SNOMED CT, RxNORM, and LOINC) preferred names without id."""},
                {"role": "user", "content": standardization_completion.choices[0].message.content}
            ]
        )
        chunk_completion = client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": """split the user text (chunking) and make each chunk a separate entity. For entities that follow qualifier words, ensure the qualifier word applies to each of the following entities. Finally, reconstruct the original sentence using the expanded and modified entities."""},
                {"role": "user", "content": rewtire_completion.choices[0].message.content}
            ]
        )
        seqment_end_time = time.time()
        print(f"{Fore.WHITE} done. ({round(seqment_end_time - seqment_start_time, 2)} sec.)\n{Style.RESET_ALL}")
        # 合併所有回應到一個單一的醫療記錄字串
        standardized_content += chunk_completion.choices[0].message.content

    # 儲存標準化後的醫療記錄字串，保存到文件f"../data/pipe_result/{file_name}_{tool_name}_{version}_{row['sqe']}.raw.polishing.txt"
    with open(f"../data/pipe_result/{file_name}_{tool_name}_{version}_{row['sqe']}.raw.polishing.txt", "w") as file:
        file.write(standardized_content)
    preprocess_time = time.time()
    print(f"{Fore.GREEN}sqe {row['sqe']} polishing time: {round(preprocess_time - sqe_start_time, 2)} sec{Style.RESET_ALL}")
    # print("Standardized Content:")
    # print(standardized_content)

    
    # ===== Step 3. Linguistic Extraction (MedCAT)，一次一句 =====
    #  -> get entities from the standardized content
    #  -> link all entities to UMLS entries
    # 3-1. 意思完備
    #     -> 如果句中出現qualifier values，則改寫整句話（將qualifier values應用到後續的entities）重跑一次Linguistic Extraction
    # 3-2. LLM based medical Entity Extraction (Concept Mapping)
    #     4-0. Blacklist (移除無意義概念，暫時不用)
    #     4-1. Dictionary lookup (N=100)
    #         -> 左右entity各自找出條目後聯集，使找到的UMLS條目數量在30條以內，若大於N條，則逐一加入夾在中間的token，直到找到的UMLS條目數量在N條以內
    #     4-2. Concept Resolution
    #         ->直接計算~Entiry_A~Entity_B~的字串嵌入值，比對出最相近的條目
    #         or
    #         ->用~Entiry_A~Entity_B~的字串請AI幫忙找出最相近的條目（~中沒有Entity）
    # ===============================
    # 使用MedCAT從文本中提取實體
    # TODO: 一次一句
    entities = cat.get_entities(standardized_content)
    # Save the entities to a JSON file
    with open(f"../data/pipe_result/{file_name}_{tool_name}_{version}_{row['sqe']}.raw.polishing.MedCAT.json", "w") as json_file:
        json.dump(entities, json_file, indent=2)
    linguistic_extraction_time = time.time()
    print(f"{Fore.GREEN}sqe {row['sqe']} linguistic extraction time: {round(linguistic_extraction_time - preprocess_time, 2)} sec{Style.RESET_ALL}")
    
    
    # ===== Step 4. Medical Normalization (ICD10 to SNOMED_CT, the final output is SNOMED_CT, RxNORM, and LOINC) =====
    #  -> 按照 token|cui|source|code|string 的格式輸出到檔案，不屬於concept的token，以"-"呈現
    # ===============================
    # MedCAT提取出的資訊，可以依照此對照擷取資訊
    #  -> token: source_value
    #  -> cui: cui
    #  -> source: 
    #  -> code: 
    #  -> string: pretty_name
    with open(f"../data/pipe_result/{file_name}_{tool_name}_{version}_{row['sqe']}.raw.polishing.output.txt", "w") as file:
        # print("index|chunk|cui|source|code|string")
        file.write("index|chunk|cui|source|code|string\n")
        entity_list = entities['entities']
        index_now = 0
        for key, entity in entity_list.items():
            # print(entity.get('cui', NONE_SYMBOL), entity.get('pretty_name', NONE_SYMBOL)) 
            # print(f"{entity.source_value}|{entity.cui}|{NONE_SYMBOL}|{NONE_SYMBOL}|{entity.pretty_name}")
            cui_df = umls_df[umls_df['SCUI'] == entity.get('cui')]
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
                # TODO: 有部分MedCAT輸出的cui會落在MRCONSO.RRF，但是不會落在filtered_data.csv，也就是說並非snomedct_us
            if entity.get('start') > index_now:
                file.write(f"{index_now}|{standardized_content[index_now:entity.get('start')].replace(NEWLINE, '<NEW_LINE>')}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}{NEWLINE}")
                file.write(f"{entity.get('start')}|{standardized_content[entity.get('start'):entity.get('end')].replace(NEWLINE, '<NEW_LINE>')}|{cui_str}|{sab_str}|{code_str}|{entity.get('pretty_name', NONE_SYMBOL)}{NEWLINE}")
                index_now = entity.get('end')
            elif entity.get('start') == index_now:
                file.write(f"{entity.get('source_value', NONE_SYMBOL)}|{cui_str}|{sab_str}|{code_str}|{entity.get('pretty_name', NONE_SYMBOL)}{NEWLINE}")
    
    medical_normalization_time = time.time()
    print(f"{Fore.GREEN}sqe {row['sqe']} Medical Normalization time: {round(medical_normalization_time - linguistic_extraction_time, 2)} sec{Style.RESET_ALL}")
    sqe_end_time = time.time()
    print(f"{Fore.BLUE}sqe {row['sqe']} total time: {round(sqe_end_time - sqe_start_time, 2)} sec{Style.RESET_ALL}")
    print("提前結束（快速測試）")
    break

end_time = time.time()
print(f"Total time: {round(end_time - start_time, 2)} sec")


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
