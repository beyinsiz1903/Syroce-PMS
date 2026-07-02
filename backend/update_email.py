from pymongo import MongoClient
import os

client = MongoClient("mongodb://localhost:27017")
db = client["syroce_pms"]
result = db.users.update_many({"email": "gm@syroce-demo.local"}, {"$set": {"email": "gm@syrocedemo.com"}})
print(f"Updated {result.modified_count} users to gm@syrocedemo.com")
