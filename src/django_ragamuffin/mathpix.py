import httpx
import asyncio
import requests
import time
import string
import re
import unicodedata
import os
import logging
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
logger = logging.getLogger(__name__)

preamble = "\\documentclass{article} \n \
    \\usepackage{amsmath}  \n \
    \\usepackage[utf8]{inputenc}  \n  \
    \\usepackage[T1]{fontenc}   \n   \
    \\usepackage{lmodern}      \n   \
    \\usepackage{hyperref}  \n \
    \\title{ mathpix-generated}\n "



def get_mathpix_credentials():
    app_id = getattr(settings, 'APP_ID', None) or os.environ.get('APP_ID')
    app_key = getattr(settings, 'APP_KEY', None) or os.environ.get('APP_KEY')
    if not app_id or not app_key:
        raise ImproperlyConfigured("Mathpix APP_ID and APP_KEY must be configured for PDF conversion.")
    return app_id, app_key

async def convert_pdf_file( pdf_path , format_out='mmd'):
    app_id, app_key = get_mathpix_credentials()
    headers = {
        "app_id": app_id,
        "app_key": app_key
    }

    # Multipart form with file
    filename = pdf_path.split('/')[-1]
    files = {
        'file': (filename, open(pdf_path, 'rb'), 'application/pdf'),
        'options_json': (
            None,
            '{"ocr": ["math", "text"], "formats": ["latex_styled","latex_simplified","mmd"], "include_image_data" : "true" }',
            'application/json'
        )
    }

    async with httpx.AsyncClient() as client:
        response = await client.post("https://api.mathpix.com/v3/pdf", headers=headers, files=files)

        if response.status_code == 200:
            job_id = response.json()["pdf_id"]
            logger.info("PDF submitted. Job ID: %s", job_id)
        else:
            raise RuntimeError(f"Mathpix PDF submission failed: {response.status_code} {response.text}")

        status_url =  f'https://api.mathpix.com/v3/converter/{job_id}'
        logger.info(f" Waiting for processing... from {status_url} ")
        while True:
            poll = requests.get(status_url, headers=headers)
            logger.info(f"poll = {poll}")
            result = poll.json()
            status = result.get("status")
            if status == "completed":
                logger.info("PDF processed.")
                break
            elif status == "error":
                raise RuntimeError(f"Mathpix PDF processing failed: {result}")
            logger.info("...still processing...")
            time.sleep(2)

        result_url = f"https://api.mathpix.com/v3/pdf/{job_id}.{format_out}" 
        result = requests.get(result_url, headers=headers)
        if result.status_code != 200:
            raise RuntimeError(f"Mathpix result download failed: {result.status_code} {result.text}")
        s  = ( result.content ).decode('utf-8',errors='replace')
        s = re.sub(r'\\\(','$',s)
        s = re.sub(r'\\\)','$',s)
        if format_out == 'tex' :
            _,m,r = s.partition(r'\begin{document')
            s = m + r
            b,m,_ = s.partition(r'\end{document}')
            s = b + m
            s = re.sub(r'^\s*\n', '', s , flags=re.MULTILINE)
            s = f"{preamble} { s }"
        return s
        
def mathpix( pdf_path, format_out='mmd' ):
    return asyncio.run(convert_pdf_file(pdf_path ,format_out ))
# Run it
#s = asyncio.run(convert_pdf_file('./latex.pdf','tex'))
#print(f"{s}")
