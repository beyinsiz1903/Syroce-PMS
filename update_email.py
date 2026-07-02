from pymongo import MongoClient
import os

client = MongoClient("mongodb://localhost:27017")
db = client["syroce_pms"]
db.users.update_one({"email": "gm@syroce-demo.local"}, {"$set": {"email": "gm@syrocedemo.com"}})
print("Updated email to gm@syrocedemo.com")
