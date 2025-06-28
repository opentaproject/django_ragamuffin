#!/usr/bin/env python
import openai
import os
import time
import sys
from openai import OpenAI

model = 'gpt-4o-mini'
client = OpenAI()
#
# MAKE SURE YOU HAVE ENVIRONMENT SET
#
#export OPENAI_API_KEY=sk-proj...
#export OPENAI_PROJECT_ID=proj_...
#export OPENAI_ORG_ID=org-...



def nuke(delete=False):
    action = 'DELETE ' if delete else 'LIST'
    print(f"\n{action}VECTOR STORES")

    vector_stores = client.vector_stores.list()
    for vector_store in vector_stores:
        vector_store_id = vector_store.id
        vector_store_files = client.vector_stores.files.list(vector_store_id=vector_store_id)
        print(f"  {action} VS: {vector_store.name} {vector_store_id} {vector_store.metadata}")
        for vector_store_file in vector_store_files:
            file_id = vector_store_file.id
            print(f"    file: {file_id}")
            if delete:
                try:
                    client.vector_stores.files.delete(vector_store_id=vector_store_id, file_id=file_id)
                except Exception as e:
                    print(f"FILE ERROR {file_id}: {e}")
        if delete:
            try:
                client.vector_stores.delete(vector_store_id=vector_store_id)
            except Exception as e:
                print(f"VECTOR_STORE_ERROR {vector_store_id}: {e}")

    print(f"\n{action}ASSISTANTS")
    assistants = openai.beta.assistants.list()
    for assistant in assistants:
        assistant_id = assistant.id
        print(f"  {action} AS: {assistant.name} {assistant_id} {assistant.metadata}")
        vs = assistant.tool_resources.file_search.vector_store_ids
        print(f"      VS: {vs}")
        time.sleep(0.5)
        if delete:
            try:
                client.beta.assistants.delete(assistant_id)
            except Exception as e:
                print(f"ASSISTANT ERROR {assistant_id}: {e}")

    print(f"\n{action}FILES")
    files = client.files.list()
    for file in files:
        file_id = file.id
        print(f" {action} FILE: {file_id} {file.filename}")
        if delete:
            try:
                client.files.delete(file_id)
            except Exception as e:
                print(f"FILE ERROR {file_id}: {e}")

    print("\n✅ Done")

def main():
    delete = False
    if len(sys.argv) > 1 and sys.argv[1] == "delete=True":
        confirmation = input("Do you really want to delete everything? (yes/no): ").strip().lower()
        if confirmation == "yes":
            delete = True
        else:
            print("Deletion aborted.")

    if delete:
        print("CHECK THE CODE IF YOU REALLY WANT TO DELETE EVERYTHING")
    nuke(delete=delete)
    while True:
        nuke(delete=False)
        time.sleep(10)

if __name__ == "__main__":
    main()
