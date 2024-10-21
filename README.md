Download the models from [this link](https://uts.nlm.nih.gov/uts/login?service=https://medcat.rosalind.kcl.ac.uk/auth-callback)

#### Install
pip install requests medcat colorama flask flask_cors pandas celera redis pydantic openai

#### Environment Variables
export OPENAI_API_KEY='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'

#### Run API
python app.py

#### Run Worker
celery -A app.celery worker --loglevel=info --pool=solo