from pathlib import Path
import logging
import string, random
import tiktoken
import time
import tiktoken
from django.conf import settings
import hashlib
import openai
from openai._exceptions import NotFoundError
import re
import os
logger = logging.getLogger(__name__)
client = openai.OpenAI(api_key=settings.AI_KEY)


from openai import OpenAIError, RateLimitError, APIError, Timeout

timeout = settings.MAXWAIT

def create_run_with_retry(thread_id, assistant_id, timeout, truncation_strategy, tools, max_retries=5):
    delay = 2  # initial delay in seconds
    print(f"CREATE RUN WITH ASSISTANT_ID = {assistant_id}")
    for attempt in range(1, max_retries + 1):
        try:
            run = openai.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id,
                timeout=timeout,
                truncation_strategy=truncation_strategy,
                tools=tools,
            )
            return run  # success
        except RateLimitError as e:
            logger.error(f"Rate limit hit. Attempt {attempt}/{max_retries}. Retrying in {delay} seconds...")
        except APIError  as e:
            logger.error(f"Transient API error on attempt {attempt}/{max_retries}: {e}. Retrying in {delay} seconds...")
        except Timeout as e:
            logger.error(f"Transient API error on attempt {attempt}/{max_retries}: {e}. Retrying in {delay} seconds...")
        except Exception as e:
            logger.error(f"Non-retryable error: {e}")
            raise  # re-raise non-rate-limit exceptions
        time.sleep(delay)
        delay *= 2  # exponential backoff
        return run

    raise Exception("Max retries exceeded due to rate limiting or API errors.")


def run_remote_query( context ):

    print(f"CONTEXT = {context}")
    now = time.time();
    openai = context['openai']; 
    thread_id = context['thread_id'];
    assistant_id = context['assistant_id'];
    query = context['query'];
    last_messages=context['last_messages'];
    max_num_results = context['max_num_results']

    try :
        openai.beta.threads.messages.create( thread_id=thread_id,  role="user", content=query )
    except Exception as err :
        return 'Error in thread'

    truncation_strategy = { "type": "last_messages", "last_messages": last_messages }
    tools=[ { "type": "file_search", "file_search": { "max_num_results": max_num_results , "ranking_options": { "score_threshold": 0.0 } } } ]
    print(f"TOOLS = {tools} TRUNCATION_STRATEGY = {truncation_strategy}")
    if last_messages is None:
        run = create_run_with_retry(thread_id, assistant_id, timeout, truncation_strategy, tools)
    else:
        run = create_run_with_retry(thread_id, assistant_id, timeout, truncation_strategy, tools)
    interval = 5;
    imax = settings.MAXWAIT / interval
    i = 0;
    print(f"RUN QUERY {query}")
    while i < imax :
        run_status = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if run_status.status == "completed":
            break
        elif run_status.status == "failed":
            raise Exception(f"Run failed. {run_status}")
        else:
            time.sleep(interval)
        i = i + 1;
        print(f"I = {i}")
    usage = run_status.usage
    model = run.model
    assistant_id_ = run_status.assistant_id
    used_instructions =  client.beta.assistants.retrieve(assistant_id=assistant_id_).instructions
    #assert i < imax , f"Request timed out after {settings.MAXWAIT} seconds; try again ; try to change the question."
    messages = openai.beta.threads.messages.list(thread_id=thread_id)
    i = 0;
    for msg in messages.data[::-1]:  # newest last
        i = i + 1 
        if msg.role == "assistant":
            res = msg
    if i == imax :
        txt =  f"Request timed out after {settings.MAXWAIT} seconds; try again ; try to change the question."
    else :
        txt =   str( msg.content[0].text.value )
        print(f"TXT = {txt}")
        txt = re.sub(r"【\d+:\d+†[^】]+】", "", txt)
    encoding = tiktoken.encoding_for_model(settings.AI_MODELS['staff'])
    ntokens = len( encoding.encode(txt ) )
    if hasattr( usage, 'total_tokens') :
        ntokens = usage.total_tokens
    tokens = encoding.encode(txt)
    time_spent = int( time.time() - now  + 0.5 )
    characters = string.ascii_letters + string.digits  # a-zA-Z0-9
    h = ''.join(random.choices(characters, k=8))
    msg =  {'user' : query, 'assistant' : txt,
            'ntokens' : ntokens ,
            'model' : model,
            'time_spent' : time_spent ,
            'last_messages' : last_messages,
            'max_num_results' : max_num_results,
            'hash' : h }
    return msg

