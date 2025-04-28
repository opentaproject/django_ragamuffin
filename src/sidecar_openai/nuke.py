import openai
import os
import pprint
import json
import chardet
import fitz
import shutil
import string
import random

from openai import OpenAI
import requests
import time
import tiktoken

model = 'gpt-4o-mini'

def nuke( delete=False) :
    if delete :
        print(f"NUKE ")
    else :
        print(f"LIST")
    client = OpenAI()
    vector_stores = client.vector_stores.list()
    action = 'DELETE ' if delete else ''
    print(f"\n{action}VECTOR STORES")
    for vector_store in  vector_stores :
        vector_store_id = vector_store.id
        vector_store_files = client.vector_stores.files.list( vector_store_id=vector_store.id)
        print(f"  {action} VS: {vector_store.name} {vector_store_id} {vector_store.metadata}")
        for vector_store_file in vector_store_files :
            file_id = vector_store_file.id
            print(f"    file: {file_id}  ")
            if delete :
                try :
                    client.vector_stores.files.delete( vector_store_id=vector_store_id, file_id=file_id)
                except :
                    print(f"FILE ERROR {file_id}")
        if delete :
            try :
                client.vector_stores.delete( vector_store_id=vector_store_id)
            except :
                print(f"VECTOR_STORE_ERROR {vector_store_id}")

    assistants = openai.beta.assistants.list()
    print(f"\n{action}ASSISTANTS")
    for assistant in assistants:
        assistant_id = assistant.id
        print(f"  {action} AS: {assistant.name} {assistant_id} {assistant.metadata} ")
        vs = assistant.tool_resources.file_search.vector_store_ids
        print(f"      VS: {vs}")
        time.sleep(0.5)
        if delete :
            try :
                client.beta.assistants.delete(assistant_id)
            except :
                print(f"ASSISTANT ERROR {assistant}")

    files = client.files.list()
    print(f"\n{action}FILES")
    for file in files :
        file_id = file.id
        print(f" {action} FILE: {file_id} {file.filename}")
        if delete :
            client.files.delete(file_id)

    print("\n✅ Done" )

def main(delete=False): 
    nuke(delete=False)
    while True :
        nuke(delete=False)
        time.sleep(10)
    print(f"Bye")
    

if __name__ == "__main__":
    main()
