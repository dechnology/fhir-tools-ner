import sys
import datetime
import time
import random
start_time = time.time()
import json
from medcat.cat import CAT
import_time = time.time()
print(f"Libraries imported in {import_time - start_time:.2f} seconds.")

# Load the model pack
cat = CAT.load_model_pack('../models/mc_modelpack_snomed_int_16_mar_2022_25be3857ba34bdd5.zip')
model_loaded_time = time.time()
print(f"Model loaded in {model_loaded_time - import_time:.2f} seconds.")

# accept user new text and display the analysis result (infinitive loop)
while True:
    print("Please enter a new text (press Ctrl+D to finish):")
    new_text = sys.stdin.read()
    entities_extract_time = time.time()
    new_entities = cat.get_entities(new_text)
    # print json format
    result = json.dumps(new_entities, indent=2)
    print(result)


    # Save the new_entities to a JSON file
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f") + '_' + ''.join(random.choices('0123456789', k=10))
    with open(f"{timestamp}.json", "w") as json_file:
        json.dump(new_entities, json_file, indent=2)
    json_saved_time = time.time()
    print(f"Entities have been saved to {timestamp}.json in {json_saved_time - entities_extract_time:.2f} seconds.")
