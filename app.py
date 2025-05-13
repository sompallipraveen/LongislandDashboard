from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import uuid
from functools import wraps
import json
from datetime import datetime, timedelta
from io import BytesIO
import base64
from bson.binary import Binary
import mimetypes
import csv
import json
import io
from flask import Response
from datetime import datetime
import os
from dotenv import load_dotenv
from bson import ObjectId
from flask.json.provider import DefaultJSONProvider




load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default_secret_key')  # Use environment variable
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.config['SESSION_COOKIE_SECURE'] = True  # For HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['ADMIN_PREFIX'] = '/admin'  # Admin route prefix
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit file uploads to 16MB

# Connect to MongoDB
MONGO_URI = os.getenv('MONGO_URI')
client = MongoClient(MONGO_URI)
db = client['PerfumeEcommerce']

# Create an images collection
if 'images' not in db.list_collection_names():
    db.create_collection('images')

# Helper functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def generate_unique_id():
    return str(uuid.uuid4())

# Admin login required decorator
def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or 'is_admin' not in session:
            flash('Please login to access admin panel', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# New functions for image handling with MongoDB
def save_image_to_mongodb(file):
    """
    Save an image to MongoDB and return the image_id
    """
    if not file or not allowed_file(file.filename):
        return None
    
    try:
        # Generate a unique ID for the image
        image_id = generate_unique_id()
        
        # Get file extension and content type
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        content_type = mimetypes.guess_type(filename)[0] or f'image/{file_ext}'
        
        # Read file data
        file_data = file.read()
        
        # Create image document
        image_doc = {
            '_id': image_id,
            'filename': filename,
            'content_type': content_type,
            'data': Binary(file_data),  # Store binary data
            'size': len(file_data),
            'uploaded_at': datetime.now()
        }
        
        # Insert into MongoDB
        db.images.insert_one(image_doc)
        
        return image_id
    except Exception as e:
        print(f"Error saving image to MongoDB: {e}")
        return None

def get_image_from_mongodb(image_id):
    """
    Retrieve an image from MongoDB by its ID
    """
    if not image_id:
        return None
    
    try:
        image = db.images.find_one({'_id': image_id})
        if image:
            return image
        return None
    except Exception as e:
        print(f"Error retrieving image from MongoDB: {e}")
        return None

def delete_image_from_mongodb(image_id):
    """
    Delete an image from MongoDB by its ID
    """
    if not image_id:
        return False
    
    try:
        result = db.images.delete_one({'_id': image_id})
        return result.deleted_count > 0
    except Exception as e:
        print(f"Error deleting image from MongoDB: {e}")
        return False



# Add context processor to provide 'now' to all templates
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# Admin Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            user = db.users.find_one({'email': email})
            
            if user and user.get('role') == 'admin':
                # Try to check password with error handling for unsupported hash types
                try:
                    password_matches = check_password_hash(user['password'], password)
                except ValueError as e:
                    if "unsupported hash type" in str(e):
                        flash('Login error: Password verification not supported in this environment', 'danger')
                        return render_template('admin/login.html')
                    else:
                        raise e
                
                if password_matches:
                    session['user_id'] = str(user['_id'])  # ✅ safe
                    session['full_name'] = user['full_name']
                    session['email'] = user['email']
                    session['is_admin'] = True
                    session.permanent = True
                    
                    flash('Login successful!', 'success')
                    return redirect(url_for('dashboard'))
                else:
                    flash('Invalid email or password', 'danger')
            else:
                flash('Invalid email or password', 'danger')
        except Exception as e:
            flash(f'Login error: {str(e)}', 'danger')
            
    return render_template('admin/login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))

# Admin Dashboard
@app.route('/')
@admin_login_required
def dashboard():
    # Get dashboard statistics
    products_count = db.products.count_documents({})
    orders_count = db.orders.count_documents({})
    users_count = db.users.count_documents({})
    
    # Calculate revenue
    all_orders = list(db.orders.find({'status': {'$ne': 'cancelled'}}))
    total_revenue = sum(order.get('total', 0) for order in all_orders)
    
    # Get recent orders
    recent_orders = list(db.orders.find().sort('created_at', -1).limit(5))
    
    # Get sales by category for pie chart
    pipeline = [
        {'$unwind': '$items'},
        {'$lookup': {
            'from': 'products',
            'localField': 'items.product_id',
            'foreignField': '_id',
            'as': 'product'
        }},
        {'$unwind': '$product'},
        {'$lookup': {
            'from': 'categories',
            'localField': 'product.category_id',
            'foreignField': '_id',
            'as': 'category'
        }},
        {'$unwind': '$category'},
        {'$group': {
            '_id': '$category.name',
            'total': {'$sum': '$items.total'}
        }},
        {'$sort': {'total': -1}}
    ]
    
    try:
        category_sales = list(db.orders.aggregate(pipeline))
    except Exception as e:
        print(f"Error getting category sales: {e}")
        category_sales = []
    
    return render_template('admin/dashboard.html', 
                           products_count=products_count, 
                           orders_count=orders_count, 
                           users_count=users_count,
                           total_revenue=total_revenue,
                           recent_orders=recent_orders,
                           category_sales=category_sales)

# Product Management
@app.route('/products')
@admin_login_required
def products():
    # Get filter parameters
    category_id = request.args.get('category')
    brand_id = request.args.get('brand')
    stock_status = request.args.get('stock')
    featured = request.args.get('featured')
    search_query = request.args.get('q')
    sort_param = request.args.get('sort', 'name_asc')
    
    # Build query
    query = {}
    
    # Category filter
    if category_id:
        try:
            query['category_id'] = ObjectId(category_id)
        except:
            pass
    
    # Brand filter
    if brand_id:
        try:
            query['brand_id'] = ObjectId(brand_id)
        except:
            pass
    
    # Stock status filter
    if stock_status:
        if stock_status == 'in_stock':
            query['stock'] = {'$gt': 10}
        elif stock_status == 'low_stock':
            query['stock'] = {'$gt': 0, '$lte': 10}
        elif stock_status == 'out_of_stock':
            query['stock'] = {'$lte': 0}
    
    # Featured filter
    if featured:
        query['featured'] = featured == '1'
    
    # Search query
    if search_query:
        query['$or'] = [
            {'name': {'$regex': search_query, '$options': 'i'}},
            {'description': {'$regex': search_query, '$options': 'i'}}
        ]
    
    # Determine sort order
    sort_field = 'name'
    sort_direction = 1  # Default to ascending
    
    if sort_param == 'name_desc':
        sort_direction = -1
    elif sort_param == 'price_asc':
        sort_field = 'price'
        sort_direction = 1
    elif sort_param == 'price_desc':
        sort_field = 'price'
        sort_direction = -1
    elif sort_param == 'stock_asc':
        sort_field = 'stock'
        sort_direction = 1
    elif sort_param == 'stock_desc':
        sort_field = 'stock'
        sort_direction = -1
    
    # Get products with sorting
    products_list = list(db.products.find(query).sort(sort_field, sort_direction))
    
    # Calculate quantity sold for each product
    for product in products_list:
        # Aggregate sales quantity across all orders
        sales_pipeline = [
            {'$match': {
                'items.product_id': str(product['_id']),
                'status': {'$ne': 'cancelled'}
            }},
            {'$unwind': '$items'},
            {'$match': {'items.product_id': str(product['_id'])}},
            {'$group': {
                '_id': None,
                'total_quantity': {'$sum': '$items.quantity'}
            }}
        ]
        
        sales_result = list(db.orders.aggregate(sales_pipeline))
        
        # Add quantity sold to the product
        product['quantity_sold'] = sales_result[0]['total_quantity'] if sales_result else 0
        
        # Add category and brand names
        if 'category_id' in product:
            category = db.categories.find_one({'_id': product['category_id']})
            product['category_name'] = category.get('name') if category else 'Uncategorized'
        
        if 'brand_id' in product:
            brand = db.brands.find_one({'_id': product['brand_id']})
            product['brand_name'] = brand.get('name') if brand else 'Unknown'
    
    # Get categories and brands for filtering
    categories = list(db.categories.find())
    brands = list(db.brands.find())
    
    return render_template('admin/products.html', 
                          products=products_list, 
                          categories=categories,
                          brands=brands,
                          selected_category=category_id,
                          selected_brand=brand_id,
                          selected_stock=stock_status,
                          selected_featured=featured,
                          search_query=search_query,
                          sort=sort_param)


@app.route('/products/add', methods=['GET', 'POST'])
@admin_login_required
def add_product():
    if request.method == 'POST':
        # Handle image upload
        image_id = None
        if 'image' in request.files:
            image = request.files['image']
            if image and allowed_file(image.filename):
                image_id = save_image_to_mongodb(image)
        
        # Process size variants
        sizes = []
        size_displays = request.form.getlist('size_display[]')
        size_values = request.form.getlist('size[]')
        size_retail_prices = request.form.getlist('size_retail_price[]')  # Retail price field
        size_prices = request.form.getlist('size_price[]')
        size_stocks = request.form.getlist('size_stock[]')
        size_skus = request.form.getlist('size_sku[]')

        for i in range(len(size_displays)):
            if i < len(size_values) and i < len(size_prices) and i < len(size_stocks):
                try:
                    # Get retail price, with fallback to sale price
                    retail_price = float(size_retail_prices[i]) if i < len(size_retail_prices) else float(size_prices[i])
                    
                    size = {
                        'id': str(uuid.uuid4()),  # Generate unique ID for each size
                        'size_display': size_displays[i],
                        'size': int(size_values[i]),
                        'retail_price': retail_price,  # Add retail price
                        'price': float(size_prices[i]),
                        'stock': int(size_stocks[i]),
                        'sku': size_skus[i] if i < len(size_skus) else f"{request.form.get('name')}-{size_values[i]}ml"
                    }
                    sizes.append(size)
                except (ValueError, TypeError):
                    # Skip invalid entries
                    continue
        
        # Set default price from the first size if sizes exist
        default_price = float(request.form.get('price', 0))
        default_stock = int(request.form.get('stock', 0))
        
        if sizes:
            default_price = sizes[0]['price']
            default_stock = sizes[0]['stock']
        else:
            # If no sizes provided, create a default size
            default_retail_price = float(request.form.get('price', 0))
            sizes = [{
                'id': str(uuid.uuid4()),  # Unique ID
                'size_display': request.form.get('size_display', '3.3oz/100ml'),
                'size': int(request.form.get('size', 100)),
                'retail_price': default_retail_price,  # Add retail price
                'price': default_price,
                'stock': default_stock,
                'sku': request.form.get('sku', f"{request.form.get('name')}-{request.form.get('size', 100)}ml")
            }]
        
        # Convert category and brand IDs to ObjectId
        try:
            category_id = ObjectId(request.form.get('category_id'))
        except:
            flash('Invalid category selected', 'danger')
            categories = list(db.categories.find())
            brands = list(db.brands.find())
            return render_template('admin/add_product.html', categories=categories, brands=brands)
            
        try:
            brand_id = ObjectId(request.form.get('brand_id'))
        except:
            flash('Invalid brand selected', 'danger')
            categories = list(db.categories.find())
            brands = list(db.brands.find())
            return render_template('admin/add_product.html', categories=categories, brands=brands)
        
        # Create product with new fields
        new_product = {
            'name': request.form.get('name'),
            'category_id': category_id,
            'brand_id': brand_id,
            'description': request.form.get('description'),
            'price': default_price,  # Default price from first size
            'stock': default_stock,  # Default stock from first size
            'image_id': image_id,
            'sizes': sizes,
            'featured': 'featured' in request.form,
            'product_type': request.form.get('product_type'),
            'gender': request.form.get('gender'),
            'fragrance_notes': request.form.get('fragrance_notes', ''),
            'weight': float(request.form.get('weight', 0)) if request.form.get('weight') else None,
            'created_at': datetime.now()
        }
        
        db.products.insert_one(new_product)
        flash('Product added successfully', 'success')
        return redirect(url_for('products'))
    
    categories = list(db.categories.find())
    brands = list(db.brands.find())
    return render_template('admin/add_product.html', categories=categories, brands=brands)

@app.route('/products/edit/<product_id>', methods=['GET', 'POST'])
@admin_login_required
def edit_product(product_id):
    try:
        product = db.products.find_one({'_id': ObjectId(product_id)})
    except Exception as e:
        flash(f'Invalid product ID: {str(e)}', 'danger')
        return redirect(url_for('products'))
    
    if not product:
        flash('Product not found', 'danger')
        return redirect(url_for('products'))
    
    if request.method == 'POST':
        try:
            # Handle image upload
            image_id = product.get('image_id')  # Keep existing image if no new one
            if 'image' in request.files:
                image = request.files['image']
                if image and allowed_file(image.filename) and image.filename:
                    # Save new image
                    new_image_id = save_image_to_mongodb(image)
                    
                    if new_image_id:
                        # Delete old image if it exists
                        if image_id:
                            delete_image_from_mongodb(image_id)
                        
                        # Update image ID
                        image_id = new_image_id
            
            # Process size variants
            sizes = []
            size_displays = request.form.getlist('size_display[]')
            size_values = request.form.getlist('size[]')
            size_retail_prices = request.form.getlist('size_retail_price[]')  # Added retail price
            size_prices = request.form.getlist('size_price[]')
            size_stocks = request.form.getlist('size_stock[]')
            size_skus = request.form.getlist('size_sku[]')
            size_ids = request.form.getlist('size_id[]')
            
            # Get the list of existing size IDs to identify removed sizes
            existing_size_ids = [size.get('id') for size in product.get('sizes', []) if 'id' in size]
            submitted_size_ids = set(size_ids)
            
            # Size value mapping for display names
            size_mapping = {
                '1.0oz/30ml': 30,
                '1.7oz/50ml': 50,
                '2.5oz/75ml': 75,
                '3.3oz/100ml': 100,
                '6.7oz/200ml': 200
            }
            
            for i in range(len(size_displays)):
                try:
                    # Get size value from display or mapping
                    display = size_displays[i] if i < len(size_displays) else '3.3oz/100ml'
                    size_value = int(size_values[i]) if i < len(size_values) and size_values[i] else size_mapping.get(display, 100)
                    
                    # Get retail price, ensure it's a valid float
                    retail_price_str = size_retail_prices[i] if i < len(size_retail_prices) else '0'
                    try:
                        retail_price = float(retail_price_str)
                    except ValueError:
                        retail_price = 0.0
                    
                    # Get price, ensure it's a valid float
                    price_str = size_prices[i] if i < len(size_prices) else '0'
                    try:
                        price = float(price_str)
                    except ValueError:
                        price = 0.0
                    
                    # Get stock, ensure it's a valid integer
                    stock_str = size_stocks[i] if i < len(size_stocks) else '0'
                    try:
                        stock = int(stock_str)
                    except ValueError:
                        stock = 0
                    
                    # Get or generate SKU
                    if i < len(size_skus) and size_skus[i]:
                        sku = size_skus[i]
                    else:
                        product_name = request.form.get('name', '').replace(' ', '-').lower()
                        sku = f"{product_name}-{size_value}ml"
                    
                    # Create size object
                    size = {
                        'size_display': display,
                        'size': size_value,
                        'retail_price': retail_price,  # Added retail price
                        'price': price,
                        'stock': stock,
                        'sku': sku
                    }
                    
                    # Add size ID if it exists (for existing sizes)
                    if i < len(size_ids) and size_ids[i]:
                        size['id'] = size_ids[i]
                    else:
                        size['id'] = str(uuid.uuid4())
                    
                    sizes.append(size)
                except Exception as e:
                    print(f"ERROR - Processing size at index {i}: {str(e)}")
                    continue  # Skip this size and continue with others
            
            # Validate - ensure we have at least one size
            if not sizes:
                flash('At least one size variant is required', 'danger')
                categories = list(db.categories.find())
                brands = list(db.brands.find())
                return render_template('admin/edit_product.html', 
                                    product=product, 
                                    categories=categories,
                                    brands=brands)
            
            # Set default price from the first size
            default_price = sizes[0]['price'] if sizes else 0
            default_stock = sizes[0]['stock'] if sizes else 0
            
            # Convert IDs to ObjectIds
            try:
                category_id = ObjectId(request.form.get('category_id'))
            except:
                flash('Invalid category selected', 'danger')
                categories = list(db.categories.find())
                brands = list(db.brands.find())
                return render_template('admin/edit_product.html', 
                                    product=product, 
                                    categories=categories,
                                    brands=brands)
            
            try:
                brand_id = ObjectId(request.form.get('brand_id'))
            except:
                flash('Invalid brand selected', 'danger')
                categories = list(db.categories.find())
                brands = list(db.brands.find())
                return render_template('admin/edit_product.html', 
                                    product=product, 
                                    categories=categories,
                                    brands=brands)
            
            # Process weight field
            weight = None
            if request.form.get('weight'):
                try:
                    weight = float(request.form.get('weight'))
                except ValueError:
                    weight = None
            
            # Build update data dictionary
            update_data = {
                'name': request.form.get('name'),
                'category_id': category_id,
                'brand_id': brand_id,
                'description': request.form.get('description'),
                'price': default_price,
                'stock': default_stock,
                'sizes': sizes,
                'featured': 'featured' in request.form,
                'product_type': request.form.get('product_type'),
                'gender': request.form.get('gender'),
                'fragrance_notes': request.form.get('fragrance_notes', ''),
                'weight': weight,
                'updated_at': datetime.now()
            }
            
            # Add image_id only if it exists
            if image_id:
                update_data['image_id'] = image_id
            
            # Update the product in the database
            result = db.products.update_one(
                {'_id': ObjectId(product_id)},
                {'$set': update_data}
            )
            
            if result.matched_count == 0:
                flash('Product not found in database', 'danger')
            elif result.modified_count == 0:
                flash('No changes were made to the product or save was successful with no changes', 'info')
            else:
                flash('Product updated successfully', 'success')
            
            return redirect(url_for('products'))
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"ERROR - Updating product: {str(e)}")
            print(f"ERROR - Details: {error_details}")
            flash(f'Error updating product: {str(e)}', 'danger')
            categories = list(db.categories.find())
            brands = list(db.brands.find())
            return render_template('admin/edit_product.html', 
                                 product=product, 
                                 categories=categories,
                                 brands=brands)
    
    # GET request - show edit form
    categories = list(db.categories.find())
    brands = list(db.brands.find())
    
    # Ensure product has sizes array with IDs
    if 'sizes' not in product or not product['sizes']:
        product['sizes'] = [{
            'size_display': '3.3oz/100ml',
            'size': 100,
            'retail_price': product.get('price', 0),  # Add default retail price
            'price': product.get('price', 0),
            'stock': product.get('stock', 0),
            'sku': f"{product.get('name')}-100ml",
            'id': str(uuid.uuid4())
        }]
    else:
        # Make sure each size has an ID and retail_price
        for size in product['sizes']:
            if 'id' not in size:
                size['id'] = str(uuid.uuid4())
            # Add retail_price if not present
            if 'retail_price' not in size:
                size['retail_price'] = size.get('price', 0)
    
    return render_template('admin/edit_product.html', 
                          product=product, 
                          categories=categories,
                          brands=brands)

# Brand Management Routes
@app.route('/brands')
@admin_login_required
def brands():
    """
    Display all brands with product counts
    """
    brands_list = list(db.brands.find())
    
    # Add product count to each brand
    for brand in brands_list:
        brand['product_count'] = db.products.count_documents({'brand_id': brand['_id']})
    
    return render_template('admin/brands.html', brands=brands_list)

@app.route('/brands/add', methods=['GET', 'POST'])
@admin_login_required
def add_brand():
    """
    Add a new brand
    """
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description', '')
        
        if not name:
            flash('Brand name is required', 'danger')
            return redirect(url_for('add_brand'))
        
        # Check if brand with same name already exists
        existing_brand = db.brands.find_one({'name': name})
        if existing_brand:
            flash(f'Brand "{name}" already exists', 'warning')
            return redirect(url_for('brands'))
        
        # Create brand
        new_brand = {
            'name': name,
            'description': description,
            'created_at': datetime.now()
        }
        
        # Handle brand logo upload if provided
        if 'logo' in request.files:
            logo = request.files['logo']
            if logo and allowed_file(logo.filename):
                logo_id = save_image_to_mongodb(logo)
                if logo_id:
                    new_brand['logo_id'] = logo_id
        
        db.brands.insert_one(new_brand)
        flash('Brand added successfully', 'success')
        return redirect(url_for('brands'))
    
    return render_template('admin/add_brand.html')

@app.route('/brands/edit/<brand_id>', methods=['GET', 'POST'])
@admin_login_required
def edit_brand(brand_id):
    """
    Edit an existing brand
    """
    brand = db.brands.find_one({'_id': ObjectId(brand_id)})
    if not brand:
        flash('Brand not found', 'danger')
        return redirect(url_for('brands'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description', '')
        
        if not name:
            flash('Brand name is required', 'danger')
            return redirect(url_for('edit_brand', brand_id=brand_id))
        
        # Check if another brand with same name exists
        existing_brand = db.brands.find_one({'name': name, '_id': {'$ne': ObjectId(brand_id)}})
        if existing_brand:
            flash(f'Another brand with name "{name}" already exists', 'warning')
            return redirect(url_for('edit_brand', brand_id=brand_id))
        
        update_data = {
            'name': name,
            'description': description,
            'updated_at': datetime.now()
        }
        
        # Handle brand logo upload if provided
        if 'logo' in request.files:
            logo = request.files['logo']
            if logo and allowed_file(logo.filename):
                logo_id = save_image_to_mongodb(logo)
                if logo_id:
                    # Delete old logo if it exists
                    if brand.get('logo_id'):
                        delete_image_from_mongodb(brand['logo_id'])
                    
                    update_data['logo_id'] = logo_id
        
        db.brands.update_one(
            {'_id': ObjectId(brand_id)},
            {'$set': update_data}
        )
        
        flash('Brand updated successfully', 'success')
        return redirect(url_for('brands'))
    
    return render_template('admin/edit_brand.html', brand=brand)

@app.route('/brands/delete/<brand_id>')
@admin_login_required
def delete_brand(brand_id):
    """
    Delete a brand if it has no associated products
    """
    # Check if brand has products
    products_count = db.products.count_documents({'brand_id': ObjectId(brand_id)})
    if products_count > 0:
        flash(f'Cannot delete brand with {products_count} products', 'danger')
        return redirect(url_for('brands'))
    
    brand = db.brands.find_one({'_id': ObjectId(brand_id)})
    if brand:
        # Delete logo if it exists
        if brand.get('logo_id'):
            delete_image_from_mongodb(brand['logo_id'])
        
        # Delete the brand
        db.brands.delete_one({'_id': ObjectId(brand_id)})
        flash('Brand deleted successfully', 'success')
    else:
        flash('Brand not found', 'danger')
    
    return redirect(url_for('brands'))

@app.route('/products/delete/<product_id>')
@admin_login_required
def delete_product(product_id):
    product = db.products.find_one({'_id': ObjectId(product_id)})
    if not product:
        flash('Product not found', 'danger')
        return redirect(url_for('products'))
    
    # Delete associated image
    if product.get('image_id'):
        delete_image_from_mongodb(product['image_id'])
    
    # Delete product
    db.products.delete_one({'_id': ObjectId(product_id)})
    
    flash('Product deleted successfully', 'success')
    return redirect(url_for('products'))

# Category Management
@app.route('/categories')
@admin_login_required
def categories():
    categories = list(db.categories.find())
    
    # Add product count to each category
    for category in categories:
        category['product_count'] = db.products.count_documents({'category_id': category['_id']})
    
    return render_template('admin/categories.html', categories=categories)

@app.route('/categories/add', methods=['GET', 'POST'])
@admin_login_required
def add_category():
    if request.method == 'POST':
        new_category = {
            'name': request.form.get('name'),
            'description': request.form.get('description'),
            'created_at': datetime.now()
        }
        
        db.categories.insert_one(new_category)
        flash('Category added successfully', 'success')
        return redirect(url_for('categories'))
    
    return render_template('admin/add_category.html')

@app.route('/categories/edit/<category_id>', methods=['GET', 'POST'])
@admin_login_required
def edit_category(category_id):
    category = db.categories.find_one({'_id': ObjectId(category_id)})
    if not category:
        flash('Category not found', 'danger')
        return redirect(url_for('categories'))
    
    if request.method == 'POST':
        db.categories.update_one(
            {'_id': ObjectId(category_id)},
            {'$set': {
                'name': request.form.get('name'),
                'description': request.form.get('description'),
                'updated_at': datetime.now()
            }}
        )
        
        flash('Category updated successfully', 'success')
        return redirect(url_for('categories'))
    
    return render_template('admin/edit_category.html', category=category)

@app.route('/categories/delete/<category_id>')
@admin_login_required
def delete_category(category_id):
    # Check if category has products
    products_count = db.products.count_documents({'category_id': ObjectId(category_id)})
    if products_count > 0:
        flash(f'Cannot delete category with {products_count} products', 'danger')
        return redirect(url_for('categories'))
    
    db.categories.delete_one({'_id': ObjectId(category_id)})
    flash('Category deleted successfully', 'success')
    return redirect(url_for('categories'))

# Order Management Routes
@app.route('/orders')
@admin_login_required
def orders():
    """
    Display all orders with filtering and sorting capabilities
    """
    # Get filter parameters
    status_filter = request.args.get('status')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    search_query = request.args.get('q')
    sort_param = request.args.get('sort', 'date_desc')
    
    # Build query
    query = {}
    
    # Status filter
    if status_filter:
        query['status'] = status_filter
    
    # Date range filter
    date_query = {}
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            date_query['$gte'] = date_from_obj
        except ValueError:
            flash('Invalid date format for From date', 'warning')
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            date_to_obj = date_to_obj + timedelta(days=1)
            date_query['$lt'] = date_to_obj
        except ValueError:
            flash('Invalid date format for To date', 'warning')
    
    if date_query:
        query['created_at'] = date_query
    
    # Search query
    if search_query:
        query['$or'] = [
            {'shipping_address.full_name': {'$regex': search_query, '$options': 'i'}},
            {'shipping_address.email': {'$regex': search_query, '$options': 'i'}}
        ]
        
        # Try to convert the search query to an ObjectId to search by order ID
        try:
            query['$or'].append({'_id': ObjectId(search_query)})
        except:
            pass
    
    # Determine sort order
    sort_field = 'created_at'
    sort_direction = -1
    
    if sort_param == 'date_asc':
        sort_direction = 1
    elif sort_param == 'total_desc':
        sort_field = 'total'
        sort_direction = -1
    elif sort_param == 'total_asc':
        sort_field = 'total'
        sort_direction = 1
    
    # Execute the query
    try:
        # Get orders from database
        mongodb_orders = list(db.orders.find(query).sort(sort_field, sort_direction))
        
        # Process orders to avoid template issues
        orders = []
        for order in mongodb_orders:
            # Convert MongoDB document to a regular dictionary
            order_dict = {}
            for key, value in order.items():
                # Convert ObjectId to string for serialization
                if isinstance(value, ObjectId):
                    order_dict[key] = str(value)
                # Rename 'items' to 'order_items' to prevent method conflict
                elif key == 'items':
                    if isinstance(value, list):
                        # Process each item in the list
                        items_list = []
                        for item in value:
                            if isinstance(item, dict):
                                # Process each item in the order
                                item_dict = {}
                                for k, v in item.items():
                                    if isinstance(v, ObjectId):
                                        item_dict[k] = str(v)
                                    else:
                                        item_dict[k] = v
                                items_list.append(item_dict)
                            else:
                                items_list.append(item)
                        order_dict['order_items'] = items_list
                    else:
                        # If items is not a list, store it as is
                        order_dict['order_items'] = value
                else:
                    order_dict[key] = value
            
            orders.append(order_dict)
    except Exception as e:
        flash(f'Error retrieving orders: {str(e)}', 'danger')
        orders = []
    
    # Calculate total amount for displayed orders
    total_amount = sum(order.get('total', 0) for order in orders)
    
    # Get counts for each status for the dashboard
    status_counts = {
        'pending': db.orders.count_documents({'status': 'pending'}),
        'processing': db.orders.count_documents({'status': 'processing'}),
        'shipped': db.orders.count_documents({'status': 'shipped'}),
        'delivered': db.orders.count_documents({'status': 'delivered'}),
        'cancelled': db.orders.count_documents({'status': 'cancelled'})
    }
    
    return render_template('admin/orders.html', 
                          orders=orders, 
                          current_status=status_filter,
                          total_amount=total_amount,
                          pending_count=status_counts['pending'],
                          processing_count=status_counts['processing'],
                          shipped_count=status_counts['shipped'],
                          delivered_count=status_counts['delivered'],
                          cancelled_count=status_counts['cancelled'],
                          date_from=date_from,
                          date_to=date_to,
                          search_query=search_query)

@app.route('/admin/order/<order_id>')
@admin_login_required
def order_detail(order_id):
    try:
        order = db.orders.find_one({'_id': ObjectId(order_id)})
        if not order:
            flash('Order not found', 'danger')
            return redirect(url_for('orders'))
        
        # Convert the order document to ensure all ObjectIds are strings
        # and rename 'items' to 'order_items'
        order_dict = {}
        for key, value in order.items():
            if isinstance(value, ObjectId):
                order_dict[key] = str(value)
            elif key == 'items':
                # Rename 'items' to 'order_items' to avoid method conflict
                if isinstance(value, list):
                    # Process each item in the list
                    items_list = []
                    for item in value:
                        if isinstance(item, dict):
                            # Process each item in the order
                            item_dict = {}
                            for k, v in item.items():
                                if isinstance(v, ObjectId):
                                    item_dict[k] = str(v)
                                else:
                                    item_dict[k] = v
                            items_list.append(item_dict)
                        else:
                            items_list.append(item)
                    order_dict['order_items'] = items_list
                else:
                    order_dict['order_items'] = value
            elif isinstance(value, list):
                # Handle other lists
                new_list = []
                for item in value:
                    if isinstance(item, dict):
                        new_item = {}
                        for k, v in item.items():
                            if isinstance(v, ObjectId):
                                new_item[k] = str(v)
                            else:
                                new_item[k] = v
                        new_list.append(new_item)
                    else:
                        new_list.append(item)
                order_dict[key] = new_list
            else:
                order_dict[key] = value
        
        # Get customer details if available
        customer = None
        if 'user_id' in order_dict:
            try:
                customer = db.users.find_one({'_id': ObjectId(order_dict['user_id'])})
                if customer:
                    # Convert customer ObjectId to string
                    customer_dict = {}
                    for key, value in customer.items():
                        if isinstance(value, ObjectId):
                            customer_dict[key] = str(value)
                        else:
                            customer_dict[key] = value
                    customer = customer_dict
            except:
                pass
        
        return render_template('admin/order_detail.html', 
                              order=order_dict, 
                              customer=customer)
    
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('orders'))
@app.route('/orders/update-status/<order_id>', methods=['POST'])
@admin_login_required
def update_order_status(order_id):
    """
    Update the status of an order and record the change in history
    """
    try:
        order = db.orders.find_one({'_id': ObjectId(order_id)})
    except:
        flash('Invalid order ID format', 'danger')
        return redirect(url_for('orders'))
    
    if not order:
        flash('Order not found', 'danger')
        return redirect(url_for('orders'))
    
    new_status = request.form.get('status')
    comment = request.form.get('comment', '')
    notify_customer = 'notify_customer' in request.form
    
    if new_status not in ['pending', 'processing', 'shipped', 'delivered', 'cancelled']:
        flash('Invalid status value', 'danger')
        return redirect(url_for('order_detail', order_id=order_id))
    
    # Skip update if status hasn't changed
    if new_status == order.get('status'):
        flash('Order already has this status', 'info')
        return redirect(url_for('order_detail', order_id=order_id))
    
    # Create status history entry if it doesn't exist
    status_history = order.get('status_history', [])
    
    # Add new status to history
    status_history.append({
        'status': new_status,
        'previous_status': order.get('status'),
        'timestamp': datetime.now(),
        'comment': comment,
        'updated_by': session.get('full_name', 'Admin')
    })
    
    # Update order status
    update_data = {
        'status': new_status,
        'status_history': status_history,
        'updated_at': datetime.now()
    }
    
    # Special handling for shipped status
    tracking_info = None
    if new_status == 'shipped' and not order.get('shipping_date'):
        update_data['shipping_date'] = datetime.now()
        
        # Get tracking information if available
        if order.get('tracking_number') and order.get('shipping_carrier'):
            tracking_info = {
                'tracking_number': order.get('tracking_number'),
                'shipping_carrier': order.get('shipping_carrier')
            }
    
    # Special handling for delivered status
    if new_status == 'delivered' and not order.get('delivery_date'):
        update_data['delivery_date'] = datetime.now()
    
    try:
        db.orders.update_one(
            {'_id': ObjectId(order_id)},
            {'$set': update_data}
        )
        
        flash(f'Order status updated to {new_status}', 'success')
        
        # Send email notification if requested
        if notify_customer:
            try:
                send_order_status_update_to_customer(order_id, new_status, tracking_info)
                flash('Customer notification email sent', 'info')
            except Exception as e:
                flash(f'Error sending email notification: {str(e)}', 'warning')
                # Add notification to database as a fallback
                notification = {
                    'user_id': order.get('user_id'),
                    'email': order['shipping_address']['email'],
                    'type': 'order_status_update',
                    'message': f'Your order #{order_id} status has been updated to: {new_status}',
                    'sent': False,
                    'created_at': datetime.now()
                }
                db.notifications.insert_one(notification)
                flash('Customer notification queued for delivery (email failed)', 'info')
            
    except Exception as e:
        flash(f'Error updating order status: {str(e)}', 'danger')
    
    return redirect(url_for('order_detail', order_id=order_id))

@app.route('/orders/update-tracking/<order_id>', methods=['POST'])
@admin_login_required
def update_tracking(order_id):
    """
    Add or update tracking information for an order
    """
    try:
        order = db.orders.find_one({'_id': ObjectId(order_id)})
    except:
        flash('Invalid order ID format', 'danger')
        return redirect(url_for('orders'))
    
    if not order:
        flash('Order not found', 'danger')
        return redirect(url_for('orders'))
    
    tracking_number = request.form.get('tracking_number')
    shipping_carrier = request.form.get('shipping_carrier')
    update_status = 'update_status' in request.form
    notify_customer = 'notify_customer' in request.form
    
    if not tracking_number:
        flash('Tracking number is required', 'warning')
        return redirect(url_for('order_detail', order_id=order_id))
    
    update_data = {
        'tracking_number': tracking_number,
        'shipping_carrier': shipping_carrier,
        'tracking_updated_at': datetime.now()
    }
    
    # Prepare tracking info for email
    tracking_info = {
        'tracking_number': tracking_number,
        'shipping_carrier': shipping_carrier
    }
    
    # Update status to shipped if requested
    if update_status and order.get('status') != 'shipped':
        update_data['status'] = 'shipped'
        update_data['shipping_date'] = datetime.now()
        
        # Create status history entry if it doesn't exist
        status_history = order.get('status_history', [])
        
        # Add new status to history
        status_history.append({
            'status': 'shipped',
            'previous_status': order.get('status'),
            'timestamp': datetime.now(),
            'comment': f'Order shipped via {shipping_carrier} with tracking number {tracking_number}',
            'updated_by': session.get('full_name', 'Admin')
        })
        
        update_data['status_history'] = status_history
    
    try:
        # Update order
        db.orders.update_one(
            {'_id': ObjectId(order_id)},
            {'$set': update_data}
        )
        
        flash('Tracking information updated successfully', 'success')
        
        # Send notification if requested
        if notify_customer:
            try:
                send_order_status_update_to_customer(
                    order_id, 
                    'shipped' if update_status else order.get('status', 'processing'), 
                    tracking_info
                )
                flash('Tracking notification email sent to customer', 'info')
            except Exception as e:
                flash(f'Error sending email notification: {str(e)}', 'warning')
                # Fall back to database notification
                notification = {
                    'user_id': order.get('user_id'),
                    'email': order['shipping_address']['email'],
                    'type': 'tracking_update',
                    'message': f'Tracking information for your order #{order_id} has been updated. ' +
                              f'Your order is being shipped via {shipping_carrier} with tracking number {tracking_number}.',
                    'sent': False,
                    'created_at': datetime.now()
                }
                db.notifications.insert_one(notification)
                flash('Tracking notification queued for delivery (email failed)', 'info')
    except Exception as e:
        flash(f'Error updating tracking information: {str(e)}', 'danger')
    
    return redirect(url_for('order_detail', order_id=order_id))

@app.route('/orders/add-note/<order_id>', methods=['POST'])
@admin_login_required
def add_order_note(order_id):
    """
    Add an internal admin note to an order
    """
    try:
        order = db.orders.find_one({'_id': ObjectId(order_id)})
    except:
        flash('Invalid order ID format', 'danger')
        return redirect(url_for('orders'))
    
    if not order:
        flash('Order not found', 'danger')
        return redirect(url_for('orders'))
    
    note = request.form.get('note')
    if not note or not note.strip():
        flash('Note cannot be empty', 'warning')
        return redirect(url_for('order_detail', order_id=order_id))
    
    # Get existing notes or initialize empty array
    admin_notes = order.get('admin_notes', [])
    
    # Add new note
    admin_notes.append({
        'content': note.strip(),
        'timestamp': datetime.now(),
        'admin_name': session.get('full_name', 'Admin'),
        'admin_id': session.get('user_id')
    })
    
    try:
        # Update order
        db.orders.update_one(
            {'_id': ObjectId(order_id)},
            {'$set': {
                'admin_notes': admin_notes,
                'updated_at': datetime.now()
            }}
        )
        
        flash('Note added successfully', 'success')
    except Exception as e:
        flash(f'Error adding note: {str(e)}', 'danger')
    
    return redirect(url_for('order_detail', order_id=order_id))

@app.route('/orders/bulk-update', methods=['POST'])
@admin_login_required
def bulk_update_orders():
    """
    Update multiple orders at once
    """
    bulk_status = request.form.get('bulk_status')
    bulk_filter = request.form.get('bulk_filter', 'selected')
    bulk_notify = 'bulk_notify' in request.form
    
    if not bulk_status or bulk_status not in ['pending', 'processing', 'shipped', 'delivered', 'cancelled']:
        flash('Invalid status selected', 'danger')
        return redirect(url_for('orders'))
    
    # Determine which orders to update
    if bulk_filter == 'all':
        # Update all orders
        query = {}
    elif bulk_filter == 'filtered':
        # Update orders matching current filter
        status_filter = request.form.get('current_status')
        query = {'status': status_filter} if status_filter else {}
    else:  # 'selected'
        # Update only selected orders
        selected_orders = request.form.getlist('selected_orders[]')
        if not selected_orders:
            flash('No orders selected', 'warning')
            return redirect(url_for('orders'))
        
        # Convert string IDs to ObjectId
        order_ids = []
        for order_id in selected_orders:
            try:
                order_ids.append(ObjectId(order_id))
            except:
                pass
        
        query = {'_id': {'$in': order_ids}}
    
    try:
        # Find orders to update
        orders_to_update = list(db.orders.find(query))
        
        if not orders_to_update:
            flash('No orders found matching criteria', 'warning')
            return redirect(url_for('orders'))
        
        # Update each order
        update_count = 0
        for order in orders_to_update:
            # Skip if already has the status
            if order.get('status') == bulk_status:
                continue
            
            # Create status history entry
            status_history = order.get('status_history', [])
            status_history.append({
                'status': bulk_status,
                'previous_status': order.get('status'),
                'timestamp': datetime.now(),
                'comment': 'Bulk status update',
                'updated_by': session.get('full_name', 'Admin')
            })
            
            # Update the order
            db.orders.update_one(
                {'_id': str(order['_id'])},
                {'$set': {
                    'status': bulk_status,
                    'status_history': status_history,
                    'updated_at': datetime.now()
                }}
            )
            
            update_count += 1
            
            # Queue notification if requested
            if bulk_notify:
                notification = {
                    'user_id': order.get('user_id'),
                    'email': order['shipping_address']['email'],
                    'type': 'order_status_update',
                    'message': f'Your order #{order["_id"]} status has been updated to: {bulk_status}',
                    'sent': False,
                    'created_at': datetime.now()
                }
                db.notifications.insert_one(notification)
        
        flash(f'Updated status for {update_count} orders to {bulk_status}', 'success')
        if bulk_notify and update_count > 0:
            flash(f'Notifications queued for {update_count} customers', 'info')
            
    except Exception as e:
        flash(f'Error during bulk update: {str(e)}', 'danger')
    
    return redirect(url_for('orders'))

# Customer Management Routes
@app.route('/customers')
@admin_login_required
def customers():
    """
    Display all customers with basic search functionality
    """
    # Get search query
    search_query = request.args.get('q', '')
    
    # Build query
    query = {}
    if search_query:
        query['$or'] = [
            {'full_name': {'$regex': search_query, '$options': 'i'}},
            {'email': {'$regex': search_query, '$options': 'i'}}
        ]
    
    # Get customers
    try:
        customers = list(db.users.find(query).sort('created_at', -1))
    except Exception as e:
        flash(f'Error retrieving customers: {str(e)}', 'danger')
        customers = []
    
    # Add order stats to each customer
    for customer in customers:
        # Count orders
        customer['order_count'] = db.orders.count_documents({
            'user_id': customer['_id'],
            'status': {'$ne': 'cancelled'}
        })
        
        # Calculate total spent
        orders = db.orders.find({
            'user_id': customer['_id'],
            'status': {'$ne': 'cancelled'}
        })
        customer['total_spent'] = sum(order.get('total', 0) for order in orders)
    
    return render_template('admin/customers.html', 
                          customers=customers,
                          search_query=search_query)


# Reports and Analytics
@app.route('/reports')
@admin_login_required
def reports():
    """
    Display basic sales and analytics reports
    """
    # Get basic stats
    total_orders = db.orders.count_documents({'status': {'$ne': 'cancelled'}})
    total_customers = db.users.count_documents({})
    
    # Calculate total sales
    orders = list(db.orders.find({'status': {'$ne': 'cancelled'}}))
    total_sales = sum(order.get('total', 0) for order in orders)
    
    # Calculate average order value
    avg_order_value = total_sales / total_orders if total_orders > 0 else 0
    
    # Get data for sales chart (last 7 days)
    chart_labels = []
    chart_data = []
    
    # Get dates for the last 7 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=6)  # 7 days including today
    
    # Generate date range
    current_date = start_date
    while current_date <= end_date:
        # Format date for display
        formatted_date = current_date.strftime('%b %d')
        chart_labels.append(formatted_date)
        
        # Get sales for this day
        day_start = datetime(current_date.year, current_date.month, current_date.day, 0, 0, 0)
        day_end = datetime(current_date.year, current_date.month, current_date.day, 23, 59, 59)
        
        day_orders = list(db.orders.find({
            'created_at': {'$gte': day_start, '$lte': day_end},
            'status': {'$ne': 'cancelled'}
        }))
        
        day_sales = sum(order.get('total', 0) for order in day_orders)
        chart_data.append(day_sales)
        
        # Move to next day
        current_date += timedelta(days=1)
    
    # Get top 5 selling products
    pipeline = [
        {'$match': {'status': {'$ne': 'cancelled'}}},
        {'$unwind': '$items'},
        {'$group': {
            '_id': '$items.product_id',
            'name': {'$first': '$items.product_name'},
            'quantity': {'$sum': '$items.quantity'},
            'revenue': {'$sum': '$items.total'}
        }},
        {'$sort': {'quantity': -1}},
        {'$limit': 5}
    ]
    
    try:
        top_products = list(db.orders.aggregate(pipeline))
    except Exception as e:
        print(f"Error in top products aggregation: {e}")
        top_products = []
    
    # Convert chart data to JSON for JavaScript
    import json
    chart_labels_json = json.dumps(chart_labels)
    chart_data_json = json.dumps(chart_data)
    
    return render_template('admin/reports.html',
                          total_sales=total_sales,
                          total_orders=total_orders,
                          total_customers=total_customers,
                          avg_order_value=avg_order_value,
                          top_products=top_products,
                          chart_labels=chart_labels_json,
                          chart_data=chart_data_json)

# API for dashboard charts
@app.route('/api/sales-data')
@admin_login_required
def api_sales_data():
    # Get sales by month for the current year
    current_year = datetime.now().year
    
    pipeline = [
        {'$match': {
            'created_at': {
                '$gte': datetime(current_year, 1, 1),
                '$lt': datetime(current_year + 1, 1, 1)
            },
            'status': {'$ne': 'cancelled'}
        }},
        {'$group': {
            '_id': {'$month': '$created_at'},
            'total': {'$sum': '$total'},
            'count': {'$sum': 1}
        }},
        {'$sort': {'_id': 1}}
    ]
    
    monthly_data = list(db.orders.aggregate(pipeline))
    
    # Format data for chart
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    sales_data = [0] * 12
    order_counts = [0] * 12
    
    for item in monthly_data:
        month_index = item['_id'] - 1  # MongoDB months are 1-indexed
        sales_data[month_index] = item['total']
        order_counts[month_index] = item['count']
    
    return jsonify({
        'labels': months,
        'sales': sales_data,
        'orders': order_counts
    })

# Settings
@app.route('/settings', methods=['GET', 'POST'])
@admin_login_required
def settings():
    """
    Manage admin settings and store configuration
    """
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        
        # Handle password change
        if form_type == 'password':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            # Basic validation
            if not current_password or not new_password or not confirm_password:
                flash('All password fields are required', 'danger')
                return redirect(url_for('settings'))
            
            if new_password != confirm_password:
                flash('New passwords do not match', 'danger')
                return redirect(url_for('settings'))
            
            # Verify current password
            user = db.users.find_one({'_id': ObjectId(session['user_id'])})
            if not user or not check_password_hash(user['password'], current_password):
                flash('Current password is incorrect', 'danger')
                return redirect(url_for('settings'))
            
            # Update password
            hashed_password = generate_password_hash(new_password)
            db.users.update_one(
                {'_id': ObjectId(session['user_id'])},
                {'$set': {'password': hashed_password}}
            )
            
            flash('Password updated successfully', 'success')
            
        # Handle store settings
        elif form_type == 'store':
            store_name = request.form.get('store_name')
            contact_email = request.form.get('contact_email')
            contact_phone = request.form.get('contact_phone')
            
            # Basic validation
            if not store_name:
                flash('Store name is required', 'danger')
                return redirect(url_for('settings'))
            
            # Update or create store settings
            db.settings.update_one(
                {'type': 'store_settings'},
                {'$set': {
                    'store_name': store_name,
                    'contact_email': contact_email,
                    'contact_phone': contact_phone,
                    'updated_at': datetime.now(),
                    'updated_by': session.get('user_id')
                }},
                upsert=True
            )
            
            flash('Store settings updated successfully', 'success')
    
    # Get store settings
    store_settings = db.settings.find_one({'type': 'store_settings'}) or {}
    
    return render_template('admin/settings.html', store_settings=store_settings)

# Image serving route
@app.route('/image/<image_id>')
def serve_image(image_id):
    """
    Serve an image stored in MongoDB
    """
    image = get_image_from_mongodb(image_id)
    if not image:
        return "Image not found", 404
    
    # Create a response with the image data
    response = Response(image['data'], mimetype=image['content_type'])
    response.headers['Content-Type'] = image['content_type']
    return response

# Function to get image from MongoDB
def get_image_from_mongodb(image_id):
    """
    Retrieve an image from MongoDB by its ID
    """
    if not image_id:
        return None
    
    try:
        image = db.images.find_one({'_id': image_id})
        if image:
            return image
        return None
    except Exception as e:
        print(f"Error retrieving image from MongoDB: {e}")
        return None

# Function to delete image from MongoDB
def delete_image_from_mongodb(image_id):
    """
    Delete an image from MongoDB by its ID
    """
    if not image_id:
        return False
    
    try:
        result = db.images.delete_one({'_id': image_id})
        return result.deleted_count > 0
    except Exception as e:
        print(f"Error deleting image from MongoDB: {e}")
        return False

# Custom template filters
@app.template_filter('format_currency')
def format_currency(value):
    if value is None:
        return "$0.00"
    return f"${float(value):.2f}"

@app.template_filter('format_date')
def format_date(value):
    return value.strftime('%B %d, %Y')

@app.template_filter('format_datetime')
def format_datetime(value):
    return value.strftime('%B %d, %Y, %I:%M %p')



@app.route('/products/import', methods=['POST'])
@admin_login_required
def import_products():
    if 'import_file' not in request.files:
        flash('No file selected', 'danger')
        return redirect(url_for('products'))
    
    file = request.files['import_file']
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('products'))
    
    if not file.filename.endswith('.csv'):
        flash('Only CSV files are allowed', 'danger')
        return redirect(url_for('products'))
    
    # Read CSV file
    try:
        stream = io.StringIO(file.stream.read().decode('utf-8'), newline=None)
        csv_reader = csv.DictReader(stream)
        
        # Track import results
        products_added = 0
        products_updated = 0
        errors = []
        
        for row in csv_reader:
            try:
                # Check if product exists (by name)
                existing_product = db.products.find_one({'name': row['name']})
                
                # Process product data
                product_data = {
                    'name': row['name'],
                    'description': row.get('description', ''),
                    'featured': row.get('featured', '0') == '1',
                    'product_type': row.get('product_type', 'Eau De Parfum'),
                    'gender': row.get('gender', 'Unisex'),
                    'fragrance_notes': row.get('fragrance_notes', ''),
                    'updated_at': datetime.now()
                }
                
                # Process category and brand IDs
                try:
                    if 'category_id' in row and row['category_id']:
                        product_data['category_id'] = ObjectId(row['category_id'])
                except:
                    # If invalid, try to find by name
                    if 'category_name' in row and row['category_name']:
                        category = db.categories.find_one({'name': row['category_name']})
                        if category:
                            product_data['category_id'] = category['_id']
                
                try:
                    if 'brand_id' in row and row['brand_id']:
                        product_data['brand_id'] = ObjectId(row['brand_id'])
                except:
                    # If invalid, try to find by name
                    if 'brand_name' in row and row['brand_name']:
                        brand = db.brands.find_one({'name': row['brand_name']})
                        if brand:
                            product_data['brand_id'] = brand['_id']
                
                # Process price and stock
                try:
                    product_data['price'] = float(row.get('price', 0))
                except ValueError:
                    product_data['price'] = 0
                
                try:
                    product_data['stock'] = int(row.get('stock', 0))
                except ValueError:
                    product_data['stock'] = 0
                
                # Process sizes if provided
                if 'sizes_json' in row and row['sizes_json']:
                    try:
                        sizes = json.loads(row['sizes_json'])
                        product_data['sizes'] = sizes
                        # Update default price and stock from first size
                        if sizes:
                            product_data['price'] = sizes[0].get('price', product_data['price'])
                            product_data['stock'] = sizes[0].get('stock', product_data['stock'])
                    except json.JSONDecodeError:
                        # If JSON is invalid, create a default size
                        product_data['sizes'] = [{
                            'id': str(uuid.uuid4()),
                            'size_display': row.get('size_display', '3.3oz/100ml'),
                            'size': int(row.get('size', 100)),
                            'price': product_data['price'],
                            'stock': product_data['stock'],
                            'sku': row.get('sku', f"{row['name']}-{row.get('size', 100)}ml")
                        }]
                else:
                    # Create default size
                    product_data['sizes'] = [{
                        'id': str(uuid.uuid4()),
                        'size_display': row.get('size_display', '3.3oz/100ml'),
                        'size': int(row.get('size', 100)),
                        'price': product_data['price'],
                        'stock': product_data['stock'],
                        'sku': row.get('sku', f"{row['name']}-{row.get('size', 100)}ml")
                    }]
                
                # Update existing or insert new
                if existing_product:
                    db.products.update_one({'_id': existing_product['_id']}, {'$set': product_data})
                    products_updated += 1
                else:
                    product_data['created_at'] = datetime.now()
                    db.products.insert_one(product_data)
                    products_added += 1
                    
            except Exception as e:
                errors.append(f"Error processing {row.get('name', 'unknown')}: {str(e)}")
        
        # Show results
        if errors:
            for error in errors:
                flash(error, 'warning')
        
        flash(f'Import complete: {products_added} products added, {products_updated} products updated', 'success')
        return redirect(url_for('products'))
        
    except Exception as e:
        flash(f'Error processing CSV file: {str(e)}', 'danger')
        return redirect(url_for('products'))

@app.route('/products/export', methods=['GET'])
@admin_login_required
def export_products():
    # Determine which products to export
    export_scope = request.args.get('export_scope', 'all')
    export_fields = request.args.getlist('export_fields')
    
    # Build query based on scope
    query = {}
    if export_scope == 'filtered':
        # Get filter parameters from query string
        category_id = request.args.get('category')
        brand_id = request.args.get('brand')
        stock_status = request.args.get('stock')
        featured = request.args.get('featured')
        search_query = request.args.get('q')
        
        # Build query with filters
        if category_id:
            try:
                query['category_id'] = ObjectId(category_id)
            except:
                pass
        
        if brand_id:
            try:
                query['brand_id'] = ObjectId(brand_id)
            except:
                pass
        
        if stock_status:
            if stock_status == 'in_stock':
                query['stock'] = {'$gt': 10}
            elif stock_status == 'low_stock':
                query['stock'] = {'$gt': 0, '$lte': 10}
            elif stock_status == 'out_of_stock':
                query['stock'] = {'$lte': 0}
        
        if featured:
            query['featured'] = featured == '1'
        
        if search_query:
            query['$or'] = [
                {'name': {'$regex': search_query, '$options': 'i'}},
                {'description': {'$regex': search_query, '$options': 'i'}}
            ]
    
    # Get products
    products_list = list(db.products.find(query))
    
    # Create CSV file in memory
    output = io.StringIO()
    fieldnames = ['name', 'description', 'price', 'stock', 'featured', 'created_at']
    
    # Add additional fields based on export_fields
    if not export_fields or 'basic' in export_fields:
        fieldnames.extend(['category_id', 'category_name', 'brand_id', 'brand_name'])
    
    if not export_fields or 'inventory' in export_fields:
        fieldnames.extend(['sizes_json'])
    
    if not export_fields or 'meta' in export_fields:
        fieldnames.extend(['product_type', 'gender', 'fragrance_notes', 'weight'])
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    # Write product data
    for product in products_list:
        row = {
            'name': product.get('name', ''),
            'description': product.get('description', ''),
            'price': product.get('price', 0),
            'stock': product.get('stock', 0),
            'featured': '1' if product.get('featured') else '0',
            'created_at': product.get('created_at').strftime('%Y-%m-%d %H:%M:%S') if 'created_at' in product else '',
        }
        
        # Add category and brand info
        if not export_fields or 'basic' in export_fields:
            # Add category info
            row['category_id'] = str(product.get('category_id', ''))
            if 'category_id' in product:
                category = db.categories.find_one({'_id': product['category_id']})
                row['category_name'] = category.get('name', '') if category else ''
            else:
                row['category_name'] = ''
            
            # Add brand info
            row['brand_id'] = str(product.get('brand_id', ''))
            if 'brand_id' in product:
                brand = db.brands.find_one({'_id': product['brand_id']})
                row['brand_name'] = brand.get('name', '') if brand else ''
            else:
                row['brand_name'] = ''
        
        # Add size info
        if not export_fields or 'inventory' in export_fields:
            # Convert sizes to JSON
            if 'sizes' in product:
                # Convert ObjectId to string for JSON serialization
                sizes_json = []
                for size in product['sizes']:
                    size_copy = size.copy()
                    if 'id' in size_copy and not isinstance(size_copy['id'], str):
                        size_copy['id'] = str(size_copy['id'])
                    sizes_json.append(size_copy)
                row['sizes_json'] = json.dumps(sizes_json)
            else:
                row['sizes_json'] = ''
        
        # Add metadata
        if not export_fields or 'meta' in export_fields:
            row['product_type'] = product.get('product_type', '')
            row['gender'] = product.get('gender', '')
            row['fragrance_notes'] = product.get('fragrance_notes', '')
            row['weight'] = product.get('weight', '')
        
        writer.writerow(row)
    
    # Return CSV as download
    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=products_export_{timestamp}.csv"}
    )

@app.route('/products/bulk-update', methods=['POST'])
@admin_login_required
def bulk_update_products():
    # Get update parameters
    update_scope = request.form.get('update_scope', 'filtered')
    update_type = request.form.get('update_type', 'percent')
    try:
        update_value = float(request.form.get('update_value', 0))
    except ValueError:
        flash('Invalid update value', 'danger')
        return redirect(url_for('products'))
    
    # Build query based on scope
    query = {}
    if update_scope == 'filtered':
        # Get filter parameters from hidden fields or session
        category_id = request.form.get('category')
        brand_id = request.form.get('brand')
        stock_status = request.form.get('stock')
        featured = request.form.get('featured')
        search_query = request.form.get('q')
        
        # Build query with filters
        if category_id:
            try:
                query['category_id'] = ObjectId(category_id)
            except:
                pass
        
        if brand_id:
            try:
                query['brand_id'] = ObjectId(brand_id)
            except:
                pass
        
        if stock_status:
            if stock_status == 'in_stock':
                query['stock'] = {'$gt': 10}
            elif stock_status == 'low_stock':
                query['stock'] = {'$gt': 0, '$lte': 10}
            elif stock_status == 'out_of_stock':
                query['stock'] = {'$lte': 0}
        
        if featured:
            query['featured'] = featured == '1'
        
        if search_query:
            query['$or'] = [
                {'name': {'$regex': search_query, '$options': 'i'}},
                {'description': {'$regex': search_query, '$options': 'i'}}
            ]
    
    # Get products to update
    products_to_update = list(db.products.find(query))
    
    if not products_to_update:
        flash('No products found to update', 'warning')
        return redirect(url_for('products'))
    
    # Update products
    updated_count = 0
    for product in products_to_update:
        # Calculate new price for main product
        current_price = product.get('price', 0)
        new_price = current_price
        
        if update_type == 'percent':
            # Percentage change
            new_price = current_price + (current_price * update_value / 100)
        elif update_type == 'amount':
            # Fixed amount change
            new_price = current_price + update_value
        elif update_type == 'fixed':
            # Set to fixed price
            new_price = update_value
        
        # Ensure price is not negative
        new_price = max(0, new_price)
        
        # Update size prices if they exist
        updated_sizes = []
        if 'sizes' in product and product['sizes']:
            for size in product['sizes']:
                size_price = size.get('price', current_price)
                new_size_price = size_price
                
                if update_type == 'percent':
                    # Percentage change
                    new_size_price = size_price + (size_price * update_value / 100)
                elif update_type == 'amount':
                    # Fixed amount change
                    new_size_price = size_price + update_value
                elif update_type == 'fixed':
                    # Set to fixed price
                    new_size_price = update_value
                
                # Ensure price is not negative
                new_size_price = max(0, new_size_price)
                
                # Round to 2 decimal places
                new_size_price = round(new_size_price, 2)
                
                # Update size
                size_copy = size.copy()
                size_copy['price'] = new_size_price
                updated_sizes.append(size_copy)
            
            # If first size exists, use its price for main product price
            if updated_sizes:
                new_price = updated_sizes[0]['price']
            
            # Update product with new sizes
            db.products.update_one(
                {'_id': product['_id']},
                {
                    '$set': {
                        'price': new_price,
                        'sizes': updated_sizes,
                        'updated_at': datetime.now()
                    }
                }
            )
        else:
            # Round to 2 decimal places
            new_price = round(new_price, 2)
            
            # Update product price only
            db.products.update_one(
                {'_id': product['_id']},
                {
                    '$set': {
                        'price': new_price,
                        'updated_at': datetime.now()
                    }
                }
            )
        
        updated_count += 1
    
    flash(f'Successfully updated prices for {updated_count} products', 'success')
    return redirect(url_for('products'))

# Contact Message Management Routes
@app.route('/contact-messages')
@admin_login_required
def contact_messages():
    """
    Display all contact messages/inquiries with filtering options
    """
    # Get filter parameters
    status_filter = request.args.get('status')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    search_query = request.args.get('q')
    
    # Build query
    query = {}
    
    # Status filter
    if status_filter:
        query['status'] = status_filter
    
    # Date range filter
    date_query = {}
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            date_query['$gte'] = date_from_obj
        except ValueError:
            flash('Invalid date format for From date', 'warning')
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            # Add one day to include the end date fully
            date_to_obj = date_to_obj + timedelta(days=1)
            date_query['$lt'] = date_to_obj
        except ValueError:
            flash('Invalid date format for To date', 'warning')
    
    if date_query:
        query['created_at'] = date_query
    
    # Search query
    if search_query:
        # Look for the search term in various fields
        query['$or'] = [
            {'name': {'$regex': search_query, '$options': 'i'}},
            {'email': {'$regex': search_query, '$options': 'i'}},
            {'mobile': {'$regex': search_query, '$options': 'i'}},
            {'message': {'$regex': search_query, '$options': 'i'}}
        ]
    
    # Get messages with sorting (newest first)
    try:
        messages = list(db.contact_messages.find(query).sort('created_at', -1))
    except Exception as e:
        flash(f'Error retrieving messages: {str(e)}', 'danger')
        messages = []
    
    return render_template('admin/contact_messages.html', 
                          messages=messages,
                          current_status=status_filter,
                          search_query=search_query,
                          date_from=date_from,
                          date_to=date_to)

@app.route('/contact-messages/<message_id>')
@admin_login_required
def contact_message_detail(message_id):
    """
    Display detailed information for a specific contact message
    """
    try:
        message = db.contact_messages.find_one({'_id': ObjectId(message_id)})
    except:
        flash('Invalid message ID format', 'danger')
        return redirect(url_for('contact_messages'))
    
    if not message:
        flash('Message not found', 'danger')
        return redirect(url_for('contact_messages'))
    
    return render_template('admin/contact_message_detail.html', message=message)

@app.route('/contact-messages/update-status/<message_id>', methods=['POST'])
@admin_login_required
def update_message_status(message_id):
    """
    Update the status of a contact message
    """
    try:
        message = db.contact_messages.find_one({'_id': ObjectId(message_id)})
    except:
        flash('Invalid message ID format', 'danger')
        return redirect(url_for('contact_messages'))
    
    if not message:
        flash('Message not found', 'danger')
        return redirect(url_for('contact_messages'))
    
    # Get new status and admin notes
    new_status = request.form.get('status')
    admin_notes = request.form.get('admin_notes', '')
    
    if new_status not in ['unread', 'read', 'responded', 'spam']:
        flash('Invalid status value', 'danger')
        return redirect(url_for('contact_message_detail', message_id=message_id))
    
    # Create status history entry if it doesn't exist
    status_history = message.get('status_history', [])
    
    # Add new status to history
    status_history.append({
        'status': new_status,
        'previous_status': message.get('status'),
        'timestamp': datetime.now(),
        'comment': admin_notes,
        'updated_by': session.get('full_name', 'Admin')
    })
    
    # Update message
    db.contact_messages.update_one(
        {'_id': ObjectId(message_id)},
        {'$set': {
            'status': new_status,
            'status_history': status_history,
            'admin_notes': admin_notes,
            'updated_at': datetime.now()
        }}
    )
    
    flash(f'Message status updated to {new_status}', 'success')
    return redirect(url_for('contact_message_detail', message_id=message_id))

@app.route('/contact-messages/delete/<message_id>', methods=['POST'])
@admin_login_required
def delete_contact_message(message_id):
    """
    Delete a contact message
    """
    try:
        message = db.contact_messages.find_one({'_id': ObjectId(message_id)})
    except:
        flash('Invalid message ID format', 'danger')
        return redirect(url_for('contact_messages'))
    
    if not message:
        flash('Message not found', 'danger')
        return redirect(url_for('contact_messages'))
    
    # Delete the message
    db.contact_messages.delete_one({'_id': ObjectId(message_id)})
    
    flash('Message deleted successfully', 'success')
    return redirect(url_for('contact_messages'))

@app.route('/contact-messages/bulk-update', methods=['POST'])
@admin_login_required
def bulk_update_messages():
    """
    Update multiple contact messages at once
    """
    bulk_status = request.form.get('bulk_status')
    bulk_filter = request.form.get('bulk_filter', 'selected')
    
    if not bulk_status or bulk_status not in ['unread', 'read', 'responded', 'spam']:
        flash('Invalid status selected', 'danger')
        return redirect(url_for('contact_messages'))
    
    # Determine which messages to update
    if bulk_filter == 'all':
        # Update all messages
        query = {}
    elif bulk_filter == 'filtered':
        # Update messages matching current filter
        status_filter = request.form.get('current_status')
        query = {'status': status_filter} if status_filter else {}
    else:  # 'selected'
        # Update only selected messages
        selected_messages = request.form.getlist('selected_messages[]')
        if not selected_messages:
            flash('No messages selected', 'warning')
            return redirect(url_for('contact_messages'))
        
        # Convert string IDs to ObjectId
        message_ids = []
        for message_id in selected_messages:
            try:
                message_ids.append(ObjectId(message_id))
            except:
                pass
        
        query = {'_id': {'$in': message_ids}}
    
    try:
        # Update the messages
        result = db.contact_messages.update_many(
            query,
            {'$set': {
                'status': bulk_status,
                'updated_at': datetime.now()
            }}
        )
        
        flash(f'Updated status for {result.modified_count} messages to {bulk_status}', 'success')
    except Exception as e:
        flash(f'Error during bulk update: {str(e)}', 'danger')
    
    return redirect(url_for('contact_messages'))
# Add to the existing inject_now context processor or create a new one
@app.context_processor
def inject_admin_data():
    """
    Inject common admin data into all templates, including unread message counts
    """
    data = {
        'now': datetime.now()
    }
    
    # Only add message data if user is logged in as admin
    if 'user_id' in session and 'is_admin' in session:
        try:
            # Count unread messages
            unread_count = db.contact_messages.count_documents({'status': 'unread'})
            data['unread_messages_count'] = unread_count
            
            # Get recent unread messages for dropdown
            if unread_count > 0:
                recent_unread = list(db.contact_messages.find(
                    {'status': 'unread'}
                ).sort('created_at', -1).limit(5))
                data['recent_unread_messages'] = recent_unread
        except Exception as e:
            print(f"Error getting unread messages: {e}")
    
    return data

# Alternative: update before_request to set these values in the session
@app.before_request
def update_message_counts():
    """
    Update unread message counts before each request
    """
    # Only process for admin routes
    if request.path.startswith('/admin') and 'user_id' in session and 'is_admin' in session:
        try:
            # Count unread messages
            unread_count = db.contact_messages.count_documents({'status': 'unread'})
            session['unread_messages_count'] = unread_count
            
            # Get recent unread messages for dropdown (just IDs and basic info)
            if unread_count > 0:
                recent_unread = list(db.contact_messages.find(
                    {'status': 'unread'},
                    {'_id': 1, 'name': 1, 'message': 1, 'created_at': 1}
                ).sort('created_at', -1).limit(5))
                
                # Convert ObjectId to string
                for msg in recent_unread:
                    msg['_id'] = str(msg['_id'])
                
                session['recent_unread_messages'] = recent_unread
        except Exception as e:
            print(f"Error updating message counts: {e}")

@app.route('/customers/<customer_id>')
@admin_login_required
def customer_detail(customer_id):
    """
    Display detailed information for a specific customer
    """
    try:
        customer = db.users.find_one({'_id': ObjectId(customer_id)})
    except:
        flash('Invalid customer ID format', 'danger')
        return redirect(url_for('customers'))
    
    if not customer:
        flash('Customer not found', 'danger')
        return redirect(url_for('customers'))
    
    # Calculate total orders
    orders_count = db.orders.count_documents({
        'user_id': ObjectId(customer_id),
        'status': {'$ne': 'cancelled'}
    })
    
    # Get customer orders with sorting and filtering
    try:
        orders = list(db.orders.find({
            'user_id': ObjectId(customer_id)
        }).sort('created_at', -1).limit(5))  # Limit to 5 most recent orders
    except Exception as e:
        flash(f'Error retrieving orders: {str(e)}', 'warning')
        orders = []
    
    # Calculate total spent
    total_spent = 0
    for order in orders:
        if order.get('status') != 'cancelled':
            total_spent += order.get('total', 0)
    
    # Fetch customer addresses (if not already in the user document)
    if 'addresses' not in customer:
        customer['addresses'] = []
    
    return render_template('admin/customer_detail.html', 
                          customer=customer,
                          orders=orders,
                          orders_count=orders_count,
                          total_spent=total_spent)

@app.route('/admin/customers/update-contact/<customer_id>', methods=['POST'])
@admin_login_required
def admin_update_customer_contact(customer_id):
    """
    Update customer contact information from admin panel
    """
    try:
        # Validate and clean input
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        mobile = request.form.get('mobile', '').strip()
        status = request.form.get('status', 'active')
        
        # Validate inputs
        if not full_name or not email:
            flash('Full name and email are required', 'danger')
            return redirect(url_for('customer_detail', customer_id=customer_id))
        
        # Validate email format
        import re
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            flash('Invalid email format', 'danger')
            return redirect(url_for('customer_detail', customer_id=customer_id))
        
        # Clean and validate mobile number if provided
        formatted_mobile = None
        if mobile:
            # Remove non-digit characters
            mobile_digits = re.sub(r'\D', '', mobile)
            
            # Validate mobile number
            if re.match(r'^1?\d{10}$', mobile_digits):
                # Trim leading 1 if present
                if len(mobile_digits) == 11 and mobile_digits.startswith('1'):
                    mobile_digits = mobile_digits[1:]
                
                # Format mobile number
                formatted_mobile = f"({mobile_digits[:3]}) {mobile_digits[3:6]}-{mobile_digits[6:]}"
            else:
                flash('Invalid mobile number format', 'warning')
        
        # Check if email is already in use by another user
        existing_email = db.users.find_one({
            'email': email, 
            '_id': {'$ne': ObjectId(customer_id)}
        })
        
        if existing_email:
            flash('Email already in use by another account', 'danger')
            return redirect(url_for('customer_detail', customer_id=customer_id))
        
        # Prepare update data
        update_data = {
            'full_name': full_name,
            'email': email,
            'status': status
        }
        
        # Add mobile number if formatted
        if formatted_mobile:
            update_data['mobile'] = formatted_mobile
        
        # Update user in database
        db.users.update_one(
            {'_id': ObjectId(customer_id)},
            {'$set': update_data}
        )
        
        flash('Customer contact information updated successfully', 'success')
    
    except Exception as e:
        flash(f'Error updating customer: {str(e)}', 'danger')
    
    return redirect(url_for('customer_detail', customer_id=customer_id))

# Payment Dashboard Routes
@app.route('/payments-dashboard')
@admin_login_required
def payments_dashboard():
    """
    Display payment statistics and analytics
    """
    # Get date range for filtering (default to current month)
    today = datetime.now()
    first_day_of_month = datetime(today.year, today.month, 1)
    
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    from_date = first_day_of_month
    to_date = today
    
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d')
        except ValueError:
            flash('Invalid date format for From date', 'warning')
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d')
            # Add one day to include the end date fully
            to_date = to_date + timedelta(days=1)
        except ValueError:
            flash('Invalid date format for To date', 'warning')
    
    # Query for completed payments in the date range
    payment_query = {
        'payment_method': 'credit_card',
        'payment_status': 'completed',
        'created_at': {'$gte': from_date, '$lt': to_date}
    }
    
    # Get all payments in the date range
    payments = list(db.orders.find(payment_query))
    
    # Calculate key metrics
    total_revenue = sum(payment.get('total', 0) for payment in payments)
    payment_count = len(payments)
    avg_order_value = total_revenue / payment_count if payment_count > 0 else 0
    
    # Get payment status counts
    status_counts = {
        'completed': db.orders.count_documents({
            'payment_method': 'credit_card',
            'payment_status': 'completed'
        }),
        'pending': db.orders.count_documents({
            'payment_method': 'credit_card',
            'payment_status': 'pending'
        }),
        'failed': db.orders.count_documents({
            'payment_method': 'credit_card',
            'payment_status': 'failed'
        })
    }
    
    # Calculate daily revenue for chart
    daily_revenue = []
    current_date = from_date
    
    while current_date < to_date:
        next_date = current_date + timedelta(days=1)
        
        day_payments = db.orders.find({
            'payment_method': 'credit_card',
            'payment_status': 'completed',
            'created_at': {'$gte': current_date, '$lt': next_date}
        })
        
        day_total = sum(payment.get('total', 0) for payment in day_payments)
        
        daily_revenue.append({
            'date': current_date.strftime('%Y-%m-%d'),
            'display_date': current_date.strftime('%b %d'),
            'amount': day_total
        })
        
        current_date = next_date
    
    # Get top customers by payment amount
    top_customers_pipeline = [
        {'$match': {
            'payment_method': 'credit_card',
            'payment_status': 'completed',
            'created_at': {'$gte': from_date, '$lt': to_date}
        }},
        {'$group': {
            '_id': '$user_id',
            'email': {'$first': '$shipping_address.email'},
            'name': {'$first': '$shipping_address.full_name'},
            'total_spent': {'$sum': '$total'},
            'orders_count': {'$sum': 1}
        }},
        {'$sort': {'total_spent': -1}},
        {'$limit': 5}
    ]
    
    top_customers = list(db.orders.aggregate(top_customers_pipeline))
    
    # Get recent transactions
    recent_transactions = list(db.orders.find({
        'payment_method': 'credit_card'
    }).sort('created_at', -1).limit(10))
    
    return render_template('admin/payments_dashboard.html',
                          total_revenue=total_revenue,
                          payment_count=payment_count,
                          avg_order_value=avg_order_value,
                          status_counts=status_counts,
                          daily_revenue=daily_revenue,
                          top_customers=top_customers,
                          recent_transactions=recent_transactions,
                          date_from=from_date.strftime('%Y-%m-%d'),
                          date_to=(to_date - timedelta(days=1)).strftime('%Y-%m-%d'))

# Payment Management Routes - Add this to your app.py
@app.route('/payment-transactions')
@admin_login_required
def payment_transactions():
    """
    Display all payment transactions with filtering
    """
    # Get filter parameters
    status_filter = request.args.get('status')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    search_query = request.args.get('q')
    min_amount = request.args.get('min_amount')
    max_amount = request.args.get('max_amount')
    
    # Build query
    query = {'payment_method': 'credit_card'}
    
    # Status filter
    if status_filter:
        query['payment_status'] = status_filter
    
    # Date range filter
    date_query = {}
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            date_query['$gte'] = date_from_obj
        except ValueError:
            flash('Invalid date format for From date', 'warning')
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            # Add one day to include the end date fully
            date_to_obj = date_to_obj + timedelta(days=1)
            date_query['$lt'] = date_to_obj
        except ValueError:
            flash('Invalid date format for To date', 'warning')
    
    if date_query:
        query['created_at'] = date_query
    
    # Amount range filter
    amount_query = {}
    if min_amount:
        try:
            amount_query['$gte'] = float(min_amount)
        except ValueError:
            flash('Invalid minimum amount', 'warning')
    
    if max_amount:
        try:
            amount_query['$lte'] = float(max_amount)
        except ValueError:
            flash('Invalid maximum amount', 'warning')
    
    if amount_query:
        query['total'] = amount_query
    
    # Search query
    if search_query:
        query['$or'] = [
            {'shipping_address.full_name': {'$regex': search_query, '$options': 'i'}},
            {'shipping_address.email': {'$regex': search_query, '$options': 'i'}},
            {'payment_intent_id': {'$regex': search_query, '$options': 'i'}}
        ]
        # Try to add ObjectId search
        try:
            query['$or'].append({'_id': ObjectId(search_query)})
        except:
            pass
    
    # Execute the query
    try:
        transactions = list(db.orders.find(query).sort('created_at', -1))
    except Exception as e:
        flash(f'Error retrieving transactions: {str(e)}', 'danger')
        transactions = []
    
    # Calculate totals
    total_amount = sum(tx.get('total', 0) for tx in transactions)
    
    return render_template('admin/payment_transactions.html',
                          transactions=transactions,
                          total_amount=total_amount,
                          count=len(transactions),
                          current_status=status_filter,
                          date_from=date_from,
                          date_to=date_to,
                          min_amount=min_amount,
                          max_amount=max_amount,
                          search_query=search_query)

# Coupon Management Routes
@app.route('/coupons')
@admin_login_required
def coupons():
    """
    Display all coupons with filtering and sorting
    """
    # Get filter parameters
    status_filter = request.args.get('status')
    search_query = request.args.get('q')
    
    # Build query
    query = {}
    
    # Status filter (active/expired)
    if status_filter:
        now = datetime.now()
        if status_filter == 'active':
            # Active coupons: start_date ≤ now ≤ end_date or no end_date
            query['$and'] = [
                {'start_date': {'$lte': now}},
                {'$or': [
                    {'end_date': {'$gte': now}},
                    {'end_date': {'$exists': False}}
                ]}
            ]
        elif status_filter == 'upcoming':
            # Upcoming coupons: start_date > now
            query['start_date'] = {'$gt': now}
        elif status_filter == 'expired':
            # Expired coupons: end_date < now
            query['end_date'] = {'$lt': now}
        elif status_filter == 'disabled':
            # Disabled coupons
            query['active'] = False
    
    # Search query
    if search_query:
        query['$or'] = [
            {'code': {'$regex': search_query, '$options': 'i'}},
            {'description': {'$regex': search_query, '$options': 'i'}}
        ]
    
    try:
        # Get coupons with sorting
        coupons_list = list(db.coupons.find(query).sort('created_at', -1))
        
        # Add status labels for UI display
        now = datetime.now()
        for coupon in coupons_list:
            if not coupon.get('active', True):
                coupon['status'] = 'disabled'
            elif 'start_date' in coupon and coupon['start_date'] > now:
                coupon['status'] = 'upcoming'
            elif 'end_date' in coupon and coupon['end_date'] < now:
                coupon['status'] = 'expired'
            else:
                coupon['status'] = 'active'
                
            # Add usage count
            coupon['usage_count'] = db.orders.count_documents({
                'coupon_code': coupon.get('code'),
                'status': {'$ne': 'cancelled'}
            })
            
    except Exception as e:
        flash(f'Error retrieving coupons: {str(e)}', 'danger')
        coupons_list = []
    
    return render_template('admin/coupons.html', 
                          coupons=coupons_list,
                          current_status=status_filter,
                          search_query=search_query)

@app.route('/coupons/add', methods=['GET', 'POST'])
@admin_login_required
def add_coupon():
    """
    Add a new coupon
    """
    if request.method == 'POST':
        try:
            # Get form data
            code = request.form.get('code', '').strip().upper()
            discount_type = request.form.get('discount_type')
            
            # Validate coupon code
            if not code:
                flash('Coupon code is required', 'danger')
                return redirect(url_for('add_coupon'))
                
            # Check if coupon code already exists
            existing_coupon = db.coupons.find_one({'code': code})
            if existing_coupon:
                flash(f'Coupon code "{code}" already exists', 'danger')
                return redirect(url_for('add_coupon'))
            
            # Process discount value
            try:
                discount_value = float(request.form.get('discount_value', 0))
                if discount_value <= 0:
                    flash('Discount value must be greater than zero', 'danger')
                    return redirect(url_for('add_coupon'))
                    
                # For percentage discounts, ensure the value is <= 100
                if discount_type == 'percentage' and discount_value > 100:
                    flash('Percentage discount cannot exceed 100%', 'danger')
                    return redirect(url_for('add_coupon'))
            except ValueError:
                flash('Invalid discount value', 'danger')
                return redirect(url_for('add_coupon'))
            
            # Process min_purchase_amount
            min_purchase_amount = 0
            if request.form.get('min_purchase_amount'):
                try:
                    min_purchase_amount = float(request.form.get('min_purchase_amount'))
                    if min_purchase_amount < 0:
                        flash('Minimum purchase amount cannot be negative', 'danger')
                        return redirect(url_for('add_coupon'))
                except ValueError:
                    flash('Invalid minimum purchase amount', 'danger')
                    return redirect(url_for('add_coupon'))
            
            # Process usage_limit
            usage_limit = None
            if request.form.get('usage_limit'):
                try:
                    usage_limit = int(request.form.get('usage_limit'))
                    if usage_limit <= 0:
                        flash('Usage limit must be greater than zero', 'danger')
                        return redirect(url_for('add_coupon'))
                except ValueError:
                    flash('Invalid usage limit', 'danger')
                    return redirect(url_for('add_coupon'))
            
            # Process dates
            start_date = None
            end_date = None
            
            if request.form.get('start_date'):
                try:
                    start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
                except ValueError:
                    flash('Invalid start date format', 'danger')
                    return redirect(url_for('add_coupon'))
            
            if request.form.get('end_date'):
                try:
                    end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
                    # Set time to end of day
                    end_date = datetime.combine(end_date.date(), datetime.max.time())
                except ValueError:
                    flash('Invalid end date format', 'danger')
                    return redirect(url_for('add_coupon'))
            
            # Validate date range
            if start_date and end_date and start_date > end_date:
                flash('End date must be after start date', 'danger')
                return redirect(url_for('add_coupon'))
            
            # Create coupon document
            new_coupon = {
                'code': code,
                'description': request.form.get('description', ''),
                'discount_type': discount_type,
                'discount_value': discount_value,
                'min_purchase_amount': min_purchase_amount,
                'usage_limit': usage_limit,
                'start_date': start_date,
                'end_date': end_date,
                'active': 'active' in request.form,
                'single_use_per_customer': 'single_use_per_customer' in request.form,
                'exclude_sale_items': 'exclude_sale_items' in request.form,
                'created_at': datetime.now(),
                'created_by': session.get('user_id')
            }
            
            # Add applicable product categories if specified
            applicable_categories = request.form.getlist('applicable_categories')
            if applicable_categories:
                category_ids = []
                for cat_id in applicable_categories:
                    try:
                        category_ids.append(ObjectId(cat_id))
                    except:
                        pass
                if category_ids:
                    new_coupon['applicable_categories'] = category_ids
            
            # Add applicable brands if specified
            applicable_brands = request.form.getlist('applicable_brands')
            if applicable_brands:
                brand_ids = []
                for brand_id in applicable_brands:
                    try:
                        brand_ids.append(ObjectId(brand_id))
                    except:
                        pass
                if brand_ids:
                    new_coupon['applicable_brands'] = brand_ids
            
            # Insert coupon into database
            result = db.coupons.insert_one(new_coupon)
            
            flash('Coupon created successfully', 'success')
            return redirect(url_for('coupons'))
            
        except Exception as e:
            flash(f'Error creating coupon: {str(e)}', 'danger')
            return redirect(url_for('add_coupon'))
    
    # GET request - show form
    # Get categories and brands for the form
    categories = list(db.categories.find())
    brands = list(db.brands.find())
    
    return render_template('admin/add_coupon.html', 
                          categories=categories,
                          brands=brands)

@app.route('/coupons/edit/<coupon_id>', methods=['GET', 'POST'])
@admin_login_required
def edit_coupon(coupon_id):
    """
    Edit an existing coupon
    """
    try:
        coupon = db.coupons.find_one({'_id': ObjectId(coupon_id)})
    except:
        flash('Invalid coupon ID', 'danger')
        return redirect(url_for('coupons'))
    
    if not coupon:
        flash('Coupon not found', 'danger')
        return redirect(url_for('coupons'))
    
    if request.method == 'POST':
        try:
            # Get form data
            code = request.form.get('code', '').strip().upper()
            discount_type = request.form.get('discount_type')
            
            # Validate coupon code
            if not code:
                flash('Coupon code is required', 'danger')
                return redirect(url_for('edit_coupon', coupon_id=coupon_id))
                
            # Check if coupon code already exists (for another coupon)
            existing_coupon = db.coupons.find_one({
                'code': code,
                '_id': {'$ne': ObjectId(coupon_id)}
            })
            if existing_coupon:
                flash(f'Another coupon with code "{code}" already exists', 'danger')
                return redirect(url_for('edit_coupon', coupon_id=coupon_id))
            
            # Process discount value
            try:
                discount_value = float(request.form.get('discount_value', 0))
                if discount_value <= 0:
                    flash('Discount value must be greater than zero', 'danger')
                    return redirect(url_for('edit_coupon', coupon_id=coupon_id))
                    
                # For percentage discounts, ensure the value is <= 100
                if discount_type == 'percentage' and discount_value > 100:
                    flash('Percentage discount cannot exceed 100%', 'danger')
                    return redirect(url_for('edit_coupon', coupon_id=coupon_id))
            except ValueError:
                flash('Invalid discount value', 'danger')
                return redirect(url_for('edit_coupon', coupon_id=coupon_id))
            
            # Process min_purchase_amount
            min_purchase_amount = 0
            if request.form.get('min_purchase_amount'):
                try:
                    min_purchase_amount = float(request.form.get('min_purchase_amount'))
                    if min_purchase_amount < 0:
                        flash('Minimum purchase amount cannot be negative', 'danger')
                        return redirect(url_for('edit_coupon', coupon_id=coupon_id))
                except ValueError:
                    flash('Invalid minimum purchase amount', 'danger')
                    return redirect(url_for('edit_coupon', coupon_id=coupon_id))
            
            # Process usage_limit
            usage_limit = None
            if request.form.get('usage_limit'):
                try:
                    usage_limit = int(request.form.get('usage_limit'))
                    if usage_limit <= 0:
                        flash('Usage limit must be greater than zero', 'danger')
                        return redirect(url_for('edit_coupon', coupon_id=coupon_id))
                except ValueError:
                    flash('Invalid usage limit', 'danger')
                    return redirect(url_for('edit_coupon', coupon_id=coupon_id))
            
            # Process dates
            start_date = None
            end_date = None
            
            if request.form.get('start_date'):
                try:
                    start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
                except ValueError:
                    flash('Invalid start date format', 'danger')
                    return redirect(url_for('edit_coupon', coupon_id=coupon_id))
            
            if request.form.get('end_date'):
                try:
                    end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
                    # Set time to end of day
                    end_date = datetime.combine(end_date.date(), datetime.max.time())
                except ValueError:
                    flash('Invalid end date format', 'danger')
                    return redirect(url_for('edit_coupon', coupon_id=coupon_id))
            
            # Validate date range
            if start_date and end_date and start_date > end_date:
                flash('End date must be after start date', 'danger')
                return redirect(url_for('edit_coupon', coupon_id=coupon_id))
            
            # Update coupon document
            update_data = {
                'code': code,
                'description': request.form.get('description', ''),
                'discount_type': discount_type,
                'discount_value': discount_value,
                'min_purchase_amount': min_purchase_amount,
                'usage_limit': usage_limit,
                'start_date': start_date,
                'end_date': end_date,
                'active': 'active' in request.form,
                'single_use_per_customer': 'single_use_per_customer' in request.form,
                'exclude_sale_items': 'exclude_sale_items' in request.form,
                'updated_at': datetime.now(),
                'updated_by': session.get('user_id')
            }
            
            # Handle applicable categories
            applicable_categories = request.form.getlist('applicable_categories')
            if applicable_categories:
                category_ids = []
                for cat_id in applicable_categories:
                    try:
                        category_ids.append(ObjectId(cat_id))
                    except:
                        pass
                
                if category_ids:
                    update_data['applicable_categories'] = category_ids
                else:
                    # Remove the field if no categories selected
                    db.coupons.update_one(
                        {'_id': ObjectId(coupon_id)},
                        {'$unset': {'applicable_categories': ''}}
                    )
            else:
                # Remove the field if no categories selected
                db.coupons.update_one(
                    {'_id': ObjectId(coupon_id)},
                    {'$unset': {'applicable_categories': ''}}
                )
            
            # Handle applicable brands
            applicable_brands = request.form.getlist('applicable_brands')
            if applicable_brands:
                brand_ids = []
                for brand_id in applicable_brands:
                    try:
                        brand_ids.append(ObjectId(brand_id))
                    except:
                        pass
                
                if brand_ids:
                    update_data['applicable_brands'] = brand_ids
                else:
                    # Remove the field if no brands selected
                    db.coupons.update_one(
                        {'_id': ObjectId(coupon_id)},
                        {'$unset': {'applicable_brands': ''}}
                    )
            else:
                # Remove the field if no brands selected
                db.coupons.update_one(
                    {'_id': ObjectId(coupon_id)},
                    {'$unset': {'applicable_brands': ''}}
                )
            
            # Update the database
            db.coupons.update_one(
                {'_id': ObjectId(coupon_id)},
                {'$set': update_data}
            )
            
            flash('Coupon updated successfully', 'success')
            return redirect(url_for('coupons'))
            
        except Exception as e:
            flash(f'Error updating coupon: {str(e)}', 'danger')
            return redirect(url_for('edit_coupon', coupon_id=coupon_id))
    
    # GET request - show form
    # Get categories and brands for the form
    categories = list(db.categories.find())
    brands = list(db.brands.find())
    
    # Format dates for display in form
    if 'start_date' in coupon and coupon['start_date']:
        coupon['start_date_formatted'] = coupon['start_date'].strftime('%Y-%m-%d')
    
    if 'end_date' in coupon and coupon['end_date']:
        coupon['end_date_formatted'] = coupon['end_date'].strftime('%Y-%m-%d')
    
    # Get currently selected categories and brands
    selected_categories = []
    if 'applicable_categories' in coupon:
        selected_categories = [str(cat_id) for cat_id in coupon['applicable_categories']]
    
    selected_brands = []
    if 'applicable_brands' in coupon:
        selected_brands = [str(brand_id) for brand_id in coupon['applicable_brands']]
    
    return render_template('admin/edit_coupon.html', 
                          coupon=coupon,
                          categories=categories,
                          brands=brands,
                          selected_categories=selected_categories,
                          selected_brands=selected_brands)

@app.route('/coupons/delete/<coupon_id>', methods=['POST'])
@admin_login_required
def delete_coupon(coupon_id):
    """
    Delete a coupon
    """
    try:
        result = db.coupons.delete_one({'_id': ObjectId(coupon_id)})
        if result.deleted_count > 0:
            flash('Coupon deleted successfully', 'success')
        else:
            flash('Coupon not found', 'danger')
    except Exception as e:
        flash(f'Error deleting coupon: {str(e)}', 'danger')
    
    return redirect(url_for('coupons'))

@app.route('/coupons/toggle-status/<coupon_id>', methods=['POST'])
@admin_login_required
def toggle_coupon_status(coupon_id):
    """
    Toggle the active status of a coupon
    """
    try:
        coupon = db.coupons.find_one({'_id': ObjectId(coupon_id)})
        if not coupon:
            flash('Coupon not found', 'danger')
            return redirect(url_for('coupons'))
        
        # Toggle the active status
        new_status = not coupon.get('active', True)
        
        db.coupons.update_one(
            {'_id': ObjectId(coupon_id)},
            {'$set': {
                'active': new_status,
                'updated_at': datetime.now(),
                'updated_by': session.get('user_id')
            }}
        )
        
        status_text = 'activated' if new_status else 'deactivated'
        flash(f'Coupon {status_text} successfully', 'success')
    except Exception as e:
        flash(f'Error toggling coupon status: {str(e)}', 'danger')
    
    return redirect(url_for('coupons'))

def convert_objectid(doc):
    return {k: str(v) if isinstance(v, ObjectId) else v for k, v in doc.items()}
def sanitize_doc(doc):
    return {k: str(v) if isinstance(v, ObjectId) else v for k, v in doc.items()}

@app.route('/advanced-orders')
@admin_login_required
def advanced_orders():
    """
    Display advanced orders view with more detailed information
    """
    # Get filter parameters (similar to regular orders)
    status_filter = request.args.get('status')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    search_query = request.args.get('q')
    sort_param = request.args.get('sort', 'date_desc')
    
    # Build query (similar to regular orders)
    query = {}
    
    # Status filter
    if status_filter:
        query['status'] = status_filter
    
    # Date range filter
    date_query = {}
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            date_query['$gte'] = date_from_obj
        except ValueError:
            flash('Invalid date format for From date', 'warning')
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            date_to_obj = date_to_obj + timedelta(days=1)
            date_query['$lt'] = date_to_obj
        except ValueError:
            flash('Invalid date format for To date', 'warning')
    
    if date_query:
        query['created_at'] = date_query
    
    # Search query
    if search_query:
        query['$or'] = [
            {'shipping_address.full_name': {'$regex': search_query, '$options': 'i'}},
            {'shipping_address.email': {'$regex': search_query, '$options': 'i'}}
        ]
        
        try:
            query['$or'].append({'_id': ObjectId(search_query)})
        except:
            query['$or'].append({'_id': {'$regex': search_query, '$options': 'i'}})
    
    # Determine sort order
    sort_field = 'created_at'
    sort_direction = -1
    
    if sort_param == 'date_asc':
        sort_direction = 1
    elif sort_param == 'total_desc':
        sort_field = 'total'
        sort_direction = -1
    elif sort_param == 'total_asc':
        sort_field = 'total'
        sort_direction = 1
    
    # Execute the query
    try:
        orders = list(db.orders.find(query).sort(sort_field, sort_direction))
    except Exception as e:
        flash(f'Error retrieving orders: {str(e)}', 'danger')
        orders = []
    
    # Calculate total amount for displayed orders
    total_amount = sum(order.get('total', 0) for order in orders)
    
    # Get counts for each status
    status_counts = {
        'pending': db.orders.count_documents({'status': 'pending'}),
        'processing': db.orders.count_documents({'status': 'processing'}),
        'shipped': db.orders.count_documents({'status': 'shipped'}),
        'delivered': db.orders.count_documents({'status': 'delivered'}),
        'cancelled': db.orders.count_documents({'status': 'cancelled'})
    }
    
    return render_template('admin/advanced_orders.html', 
                          orders=orders, 
                          current_status=status_filter,
                          total_amount=total_amount,
                          status_counts=status_counts)

class MongoJSONProvider(DefaultJSONProvider):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)

# Set the custom JSON provider on the Flask app
app.json_provider_class = MongoJSONProvider
app.json = MongoJSONProvider(app)

def sanitize_mongo_doc(doc):
    """Convert MongoDB document to a safe dictionary for templates"""
    if isinstance(doc, dict):
        # Create a new dict without the items() method conflict
        result = {}
        for k, v in doc.items():
            # Rename 'items' key to 'order_items' to avoid method conflict
            if k == 'items':
                result['order_items'] = sanitize_mongo_doc(v)
            elif isinstance(v, (dict, list)):
                result[k] = sanitize_mongo_doc(v)
            elif isinstance(v, ObjectId):
                result[k] = str(v)
            else:
                result[k] = v
        return result
    elif isinstance(doc, list):
        return [sanitize_mongo_doc(item) for item in doc]
    else:
        return doc

if __name__ == '__main__':
    app.run(debug=True, port=5001, use_reloader=False)