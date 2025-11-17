import os
from dotenv import load_dotenv

# This loads the variables from your .env file into the script's environment
load_dotenv() 

# Now you can access your keys SAFELY
api_key = os.environ.get("APCA_API_KEY_ID")
secret_key = os.environ.get("APCA_API_SECRET_KEY")
