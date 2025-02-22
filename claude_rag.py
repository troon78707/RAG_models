# -*- coding: utf-8 -*-
"""claude_RAG

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1HHYpNKlGjjJGhgk-0xipESG3JghO9p4r
"""

pip install pymongo datasets pandas anthropic openai

import os
import requests
from io import BytesIO
import pandas as pd
from google.colab import userdata

def download_and_combine_parquet_files(parquet_file_urls, hf_token):
    """
    Downloads Parquet files from the provided URLs using the given Hugging Face token,
    and returns a combined DataFrame.

    Parameters:
    - parquet_file_urls: List of strings, URLs to the Parquet files.
    - hf_token: String, Hugging Face authorization token.

    Returns:
    - combined_df: A pandas DataFrame containing the combined data from all Parquet files.
    """
    headers = {"Authorization": f"Bearer {hf_token}"}
    all_dataframes = []

    for parquet_file_url in parquet_file_urls:
        response = requests.get(parquet_file_url, headers=headers)
        if response.status_code == 200:
            parquet_bytes = BytesIO(response.content)
            df = pd.read_parquet(parquet_bytes)
            all_dataframes.append(df)
        else:
            print(f"Failed to download Parquet file from {parquet_file_url}: {response.status_code}")

    if all_dataframes:
        combined_df = pd.concat(all_dataframes, ignore_index=True)
        return combined_df
    else:
        print("No dataframes to concatenate.")
        return None

# Commented out other parquet files below to reduce the amount of data ingested.
# One praquet file has an estimated 50,000 datapoint
parquet_files = [
    "https://huggingface.co/api/datasets/AIatMongoDB/tech-news-embeddings/parquet/default/train/0000.parquet",
    # "https://huggingface.co/api/datasets/AIatMongoDB/tech-news-embeddings/parquet/default/train/0001.parquet",
    # "https://huggingface.co/api/datasets/AIatMongoDB/tech-news-embeddings/parquet/default/train/0002.parquet",
    # "https://huggingface.co/api/datasets/AIatMongoDB/tech-news-embeddings/parquet/default/train/0003.parquet",
    # "https://huggingface.co/api/datasets/AIatMongoDB/tech-news-embeddings/parquet/default/train/0004.parquet",
    # "https://huggingface.co/api/datasets/AIatMongoDB/tech-news-embeddings/parquet/default/train/0005.parquet",
]

hf_token = userdata.get("HF_TOKEN")
combined_df = download_and_combine_parquet_files(parquet_files, hf_token)

# Remove the _id coloum from the intital dataset
combined_df = combined_df.drop(columns=['_id'])

# Convert each numpy array in the 'embedding' column to a normal Python list
combined_df['embedding'] = combined_df['embedding'].apply(lambda x: x.tolist())

combined_df.head()

import pymongo
from google.colab import userdata

def get_mongo_client(mongo_uri):
  """Establish connection to the MongoDB."""
  try:
    client = pymongo.MongoClient(mongo_uri)
    print("Connection to MongoDB successful")
    return client
  except pymongo.errors.ConnectionFailure as e:
    print(f"Connection failed: {e}")
    return None

mongo_uri = userdata.get('MONGO_URI_3')
if not mongo_uri:
  print("MONGO_URI not set in environment variables")

mongo_client = get_mongo_client(mongo_uri)

DB_NAME="tech_news"
COLLECTION_NAME="hacker_noon_tech_news"

db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]

# To ensure we are working with a fresh collection
# delete any existing records in the collection
collection.delete_many({})

# Data Ingestion
combined_df_json = combined_df.to_dict(orient='records')
collection.insert_many(combined_df_json)

def vector_search(user_query, collection):
    """
    Perform a vector search in the MongoDB collection based on the user query.

    Args:
    user_query (str): The user's query string.
    collection (MongoCollection): The MongoDB collection to search.

    Returns:
    list: A list of matching documents.
    """

    # Generate embedding for the user query
    query_embedding = get_embedding(user_query)

    if query_embedding is None:
        return "Invalid query or embedding generation failed."

    # Define the vector search pipeline
    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "queryVector": query_embedding,
                "path": "embedding",
                "numCandidates": 150,  # Number of candidate matches to consider
                "limit": 5  # Return top 5 matches
            }
        },
        {
            "$project": {
                "_id": 0,  # Exclude the _id field
                "embedding": 0,  # Exclude the embedding field
                "score": {
                    "$meta": "vectorSearchScore"  # Include the search score
                }
            }
        }
    ]

    # Execute the search
    results = collection.aggregate(pipeline)
    return list(results)

import openai
from google.colab import userdata

openai.api_key = userdata.get("OPENAI_API_KEY")

EMBEDDING_MODEL = "text-embedding-3-small"

def get_embedding(text):
    """Generate an embedding for the given text using OpenAI's API."""

    # Check for valid input
    if not text or not isinstance(text, str):
        return None

    try:
        # Call OpenAI API to get the embedding
        embedding = openai.embeddings.create(input=text, model=EMBEDDING_MODEL, dimensions=256).data[0].embedding
        return embedding
    except Exception as e:
        print(f"Error in get_embedding: {e}")
        return None

import anthropic
client = anthropic.Client(api_key=userdata.get("ANTHROPIC_API_KEY"))

def handle_user_query(query, collection):

  get_knowledge = vector_search(query, collection)

  search_result = ''
  for result in get_knowledge:
    search_result += (
        f"Title: {result.get('title', 'N/A')}, "
        f"Company Name: {result.get('companyName', 'N/A')}, "
        f"Company URL: {result.get('companyUrl', 'N/A')}, "
        f"Date Published: {result.get('published_at', 'N/A')}, "
        f"Article URL: {result.get('url', 'N/A')}, "
        f"Description: {result.get('description', 'N/A')}, \n"
    )

  response = client.messages.create(
    model="claude-3-opus-20240229",
    max_tokens=1024,
    system="You are a news aggregator providing up to date information to retail investors based on what investments they have. Once told what companies a user has investments in, you provide them with any important information related to their investments",
    messages=[
        {"role": "user", "content": "Answer this user query: " + query + " with the following context: " + search_result}
    ]
  )

  return (response.content[0].text), search_result

# Conduct query with retrieval of sources
query = "I am invested in Alphabet, Apple and Microsoft"
response, source_information = handle_user_query(query, collection)

print(f"Response: {response}")
print(f"Source Information: \\n{source_information}")