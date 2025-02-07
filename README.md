Download the models from [this link](https://uts.nlm.nih.gov/uts/login?service=https://medcat.rosalind.kcl.ac.uk/auth-callback)

## Installation & Usage

#### Install
pip install requests medcat colorama flask flask_cors pandas celera redis pydantic openai

#### Environment Variables
export OPENAI_API_KEY='sk-proj-*-*-*--*'

#### Run API
python app.py

#### Run Worker
celery -A app.celery worker --loglevel=info --pool=solo
