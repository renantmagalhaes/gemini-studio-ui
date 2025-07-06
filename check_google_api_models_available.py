import google.generativeai as genai
import os
from dotenv import load_dotenv

# Load your API key from the .env file
try:
    load_dotenv()
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
except (AttributeError, ValueError):
    print("Could not configure API. Make sure your .env file is set up correctly.")
    exit()

print("--- Discovering Available Models for Your API Key ---")
print("This list shows every model you have permission to use via the API.\n")

# List all models and find the ones that support the 'generateContent' method (chat/text models)
found_models = False
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        found_models = True
        print(f"Display Name: {m.display_name}")
        print(f"  API ID (Model Name): {m.name}\n")

if not found_models:
    print("No chat/text models found. Your API key might be invalid or have restricted permissions.")

print("-------------------------------------------------")
print("To use a model, copy its 'API ID (Model Name)' into the AVAILABLE_MODELS dictionary in app.py.")
