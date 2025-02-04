import json
import difflib

# The original text
original_text = """Family History: No contributory
Medication Allergy: No 病人自述 2017/2/25
Medication ADR:unknown
Allergy to Medical Device and Materials: No 病人自述 2017/2/25
Current Medication:
NTUH:PARAMOL 500 mg/tab 1 tab STAT PO 1 days
PARAMOL 500 mg/tab 1 tab Q6HPRN PO 2 days
Maxipime 500 mg/vial 2000 mg STAT IV 1 days
Maxipime 500 mg/vial 2000 mg Q12H IV 2 days
Hydrea 500 mg/cap 2 cap QID PO 2 days
Fasturtec 1.5 mg/vial 9 mg ONCE IF 1 days
Feburic 80 mg/tab 0.5 tab STAT PO 1 days
Feburic 80 mg/tab 0.5 tab QD PO 2 days
Feburic 80 mg/tab 1/2 tab QD PO 12 days
Gastro-Timelets SR 30 mg/cap 1 cap QD PO 12 days"""

# The LLM output as JSON
llm_output_json = """{
  "result": [
    {
      "non-entity": "Family History: No contributory\\n"
    },
    {
      "non-entity": "Medication Allergy: No 病人自述 2017/2/25\\n"
    },
    {
      "non-entity": "Medication ADR: unknown\\n"
    },
    {
      "non-entity": "Allergy to Medical Device and Materials: No 病人自述 2017/2/25\\n"
    },
    {
      "non-entity": "Current Medication:\\n"
    },
    {
      "clue": "PARAMOL 500 mg/tab",
      "concept": "Acetaminophen 500 MG Oral Tablet",
      "vocabulary": "RXNORM",
      "id": "198211",
      "keyword": [
        "PARAMOL",
        "500 mg",
        "tab"
      ]
    },
    {
      "non-entity": " 1 tab STAT PO 1 days\\n"
    },
    {
      "clue": "PARAMOL 500 mg/tab",
      "concept": "Acetaminophen 500 MG Oral Tablet",
      "vocabulary": "RXNORM",
      "id": "198211",
      "keyword": [
        "PARAMOL",
        "500 mg",
        "tab"
      ]
    },
    {
      "non-entity": " 1 tab Q6HPRN PO 2 days\\n"
    },
    {
      "clue": "Maxipime 500 mg/vial",
      "concept": "Cefepime 500 MG Injection",
      "vocabulary": "RXNORM",
      "id": "898176",
      "keyword": [
        "Maxipime",
        "500 mg",
        "vial"
      ]
    },
    {
      "non-entity": " 2000 mg STAT IV 1 days\\n"
    },
    {
      "clue": "Maxipime 500 mg/vial",
      "concept": "Cefepime 500 MG Injection",
      "vocabulary": "RXNORM",
      "id": "898176",
      "keyword": [
        "Maxipime",
        "500 mg",
        "vial"
      ]
    },
    {
      "non-entity": " 2000 mg Q12H IV 2 days\\n"
    },
    {
      "clue": "Hydrea 500 mg/cap",
      "concept": "Hydroxyurea 500 MG Oral Capsule",
      "vocabulary": "RXNORM",
      "id": "651334",
      "keyword": [
        "Hydrea",
        "500 mg",
        "cap"
      ]
    },
    {
      "non-entity": " 2 cap QID PO 2 days\\n"
    },
    {
      "clue": "Fasturtec 1.5 mg/vial",
      "concept": "Rasburicase 1.5 MG Injection",
      "vocabulary": "RXNORM",
      "id": "476163",
      "keyword": [
        "Fasturtec",
        "1.5 mg",
        "vial"
      ]
    },
    {
      "non-entity": " 9 mg ONCE IF 1 days\\n"
    },
    {
      "clue": "Feburic 80 mg/tab",
      "concept": "Febuxostat 80 MG Oral Tablet",
      "vocabulary": "RXNORM",
      "id": "313444",
      "keyword": [
        "Feburic",
        "80 mg",
        "tab"
      ]
    },
    {
      "non-entity": " 0.5 tab STAT PO 1 days\\n"
    },
    {
      "clue": "Feburic 80 mg/tab",
      "concept": "Febuxostat 80 MG Oral Tablet",
      "vocabulary": "RXNORM",
      "id": "313444",
      "keyword": [
        "Feburic",
        "80 mg",
        "tab"
      ]
    },
    {
      "non-entity": " 0.5 tab QD PO 2 days\\n"
    },
    {
      "clue": "Feburic 80 mg/tab",
      "concept": "Febuxostat 80 MG Oral Tablet",
      "vocabulary": "RXNORM",
      "id": "313444",
      "keyword": [
        "Feburic",
        "80 mg",
        "tab"
      ]
    },
    {
      "non-entity": " 1/2 tab QD PO 12 days\\n"
    },
    {
      "clue": "Gastro-Timelets SR 30 mg/cap",
      "concept": "Gastro-Timelets 30 MG Oral Capsule",
      "vocabulary": "RXNORM",
      "id": "123456",
      "keyword": [
        "Gastro-Timelets",
        "SR 30 mg",
        "cap"
      ]
    },
    {
      "non-entity": " 1 cap QD PO 12 days\\n"
    }
  ]
}"""

# Parse the JSON data
llm_output = json.loads(llm_output_json)["result"]

# Reconstruct the LLM's text and keep track of clue positions
reconstructed_text = ''
clue_positions = []

pos_in_reconstructed_text = 0

for item in llm_output:
    if 'non-entity' in item:
        text = item['non-entity']
        reconstructed_text += text
        pos_in_reconstructed_text += len(text)
    elif 'clue' in item:
        clue = item['clue']
        start_pos = pos_in_reconstructed_text
        reconstructed_text += clue
        end_pos = pos_in_reconstructed_text + len(clue)
        clue_positions.append({
            'clue': item['clue'],
            'start': start_pos,
            'end': end_pos,
            'item': item
        })
        pos_in_reconstructed_text += len(clue)
    else:
        pass  # ignore

# Use SequenceMatcher to align the reconstructed text with the original text
s = difflib.SequenceMatcher(None, reconstructed_text, original_text)
opcodes = s.get_opcodes()

# Function to map positions from reconstructed text to original text
def map_position(pos_in_reconstructed, opcodes):
    for tag, i1, i2, j1, j2 in opcodes:
        if i1 <= pos_in_reconstructed < i2:
            offset = pos_in_reconstructed - i1
            if tag in ('equal', 'replace'):
                pos_in_original = j1 + offset
                return pos_in_original
            elif tag == 'delete':
                # Character in reconstructed text is deleted in original text
                return None
            elif tag == 'insert':
                # Character in original text is inserted (doesn't exist in reconstructed text)
                return None
    return None

# Map the clue positions to the original text
for clue_info in clue_positions:
    start_pos = clue_info['start']
    end_pos = clue_info['end']

    mapped_start = map_position(start_pos, opcodes)
    mapped_end = map_position(end_pos - 1, opcodes)  # Adjust because end is exclusive

    if mapped_start is not None and mapped_end is not None:
        mapped_end += 1  # Adjust because end is exclusive
        matched_text = original_text[mapped_start:mapped_end]
        clue_info['mapped_start'] = mapped_start
        clue_info['mapped_end'] = mapped_end
        clue_info['matched_text'] = matched_text
    else:
        clue_info['mapped_start'] = None
        clue_info['mapped_end'] = None
        clue_info['matched_text'] = None

# 將修正後的index應用到llm_output_json的start和end
for item in llm_output:
    if 'clue' in item:
        clue_info = clue_positions.pop(0)
        item['start'] = clue_info['mapped_start']
        item['end'] = clue_info['mapped_end']

# Print the modified JSON
print(json.dumps(llm_output, indent=2))
