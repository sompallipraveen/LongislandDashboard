from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash

# Replace these values
MONGO_URI = "mongodb+srv://gamehunter421:q9udN9upzRdwjGva@perfumeecommerce.fw7ndeb.mongodb.net/?retryWrites=true&w=majority&appName=PerfumeEcommerce"
admin_email = "admin@longislandperfumes.com"  # change to your actual admin email
new_password = "admin123"  # change to your new password

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client['PerfumeEcommerce']

# Find the admin user
admin_user = db.users.find_one({'email': admin_email, 'role': 'admin'})

if admin_user:
    hashed_password = generate_password_hash(new_password)
    db.users.update_one(
        {'_id': ObjectId(admin_user['_id'])},
        {'$set': {'password': hashed_password}}
    )
    print(f"Password updated successfully for admin user: {admin_email}")
else:
    print("Admin user not found.")
