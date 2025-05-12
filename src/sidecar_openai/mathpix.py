import httpx
import asyncio
import requests
import time
import string
import re
import unicodedata
import os
import logging
logger = logging.getLogger(__name__)

preamble = "\\documentclass{article} \n \
    \\usepackage{amsmath}  \n \
    \\usepackage[utf8]{inputenc}  \n  \
    \\usepackage[T1]{fontenc}   \n   \
    \\usepackage{lmodern}      \n   \
    \\usepackage{hyperref}  \n \
    \\title{ mathpix-generated}\n "



APP_ID = os.environ.get('APP_ID')
APP_KEY= os.environ.get('APP_KEY')

async def convert_pdf_file( pdf_path , format_out='mmd'):
    headers = {
        "app_id": APP_ID,
        "app_key": APP_KEY
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
            logger.info("✅ PDF submitted. Job ID:", job_id)
        else:
            logger.info("❌ Error:", response.status_code, response.text)
            return None

        status_url =  f'https://api.mathpix.com/v3/converter/{job_id}'
        logger.info(f" Waiting for processing... from {status_url} ")
        while True:
            poll = requests.get(status_url, headers=headers)
            logger.info(f"poll = {poll}")
            result = poll.json()
            status = result.get("status")
            if status == "completed":
                logger.info("✅ PDF processed.")
                break
            elif status == "error":
                logger.info("❌ Error:", result)
                exit()
            logger.info("...still processing...")
            time.sleep(2)

        result_url = f"https://api.mathpix.com/v3/pdf/{job_id}.{format_out}" 
        result = requests.get(result_url, headers=headers)
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
    try :
        s = asyncio.run(convert_pdf_file(pdf_path ,format_out ))
    except Exception as e :
        s = f"Conversion error: {str(e)}"
    #print(f"MATPIX S = {s}")
    return s
# Run it
#s = asyncio.run(convert_pdf_file('./latex.pdf','tex'))
#print(f"{s}")
