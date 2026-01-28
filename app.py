# ==============================
# Imports & Environment Setup
# ==============================
import os
import re
import io         # ADDED: Needed for image stream handling
import base64     # ADDED: Needed for base64 decoding
import tempfile   # ADDED: Needed for temporary file handling
import zipfile    # ADDED: Needed for ZIP file creation (For Celphone Download)
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file # ADDED: send_file
from dotenv import load_dotenv
from supabase import create_client, Client
from werkzeug.utils import secure_filename # ADDED: FIX FOR UPLOAD ERROR

# ==============================
# Load Environment Variables
# ==============================
load_dotenv()
SUPAB_URL = os.getenv("SUPAB_URL")
SUPAB_SERVICE_KEY = os.getenv("SUPAB_SERVICE_KEY")

if not SUPAB_URL or not SUPAB_SERVICE_KEY:
    raise ValueError("SUPAB_URL and SUPAB_SERVICE_KEY must be set in .env file")

# ==============================
# Flask App Initialization
# ==============================
app = Flask(__name__)
# Optional: Secret key for session management if needed later
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey") 

# ==============================
# 🆕 STANDALONE SIGNATURE PAD SETUP
# ==============================
SIGN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'signatures')
os.makedirs(SIGN_DIR, exist_ok=True)

def last_signature_path():
    files = [f for f in os.listdir(SIGN_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    if not files:
        return None
    files.sort(key=lambda x: os.path.getmtime(os.path.join(SIGN_DIR, x)), reverse=True)
    return os.path.join(SIGN_DIR, files[0])

# ==============================
# Supabase Client
# ==============================
supabase: Client = create_client(SUPAB_URL, SUPAB_SERVICE_KEY)

def get_db():
    return supabase

# ================================
# UTILITY: VB6 STYLE REPLACE (Sanitization)
# ================================
def vb6_replace(text):
    """
    Simple sanitization to remove SQL injection chars or HTML symbols.
    NOTE: This is basic. Ideally, use parameterized queries or ORM sanitization.
    """
    if not text:
        return ""
    return (
        text.strip()
            .replace("'", "")
            .replace('"', "")
            .replace(";", "")
            .replace("--", "")
            .replace("<", "") # Added basic HTML tag prevention
            .replace(">", "")
    )

# ==============================
# 🆕 CAPTION CHANGER UTILITY
# ==============================
def get_system_settings():
    try:
        db = get_db()
        response = db.from_('system_settings').select('*').eq('id',1).execute()
        if response.data:
            return response.data[0]
        else:
            # Default fallback kung walang laman
            return {
                'main_title': 'UGBROMOVE App',
                'sub_title': 'Placeholder',
                'company_name': 'No Company',
                'logo_url': ''
            }
    except Exception as e:
        print(f"Error getting settings: {e}")
        return {}

# 🆕 CONTEXT PROCESSOR: Makes 'settings' available in ALL HTML templates
@app.context_processor
def inject_settings():
    return dict(settings=get_system_settings())

# ==============================
# 🆕 AUTO CLEANUP SCANNER (13H INTERVAL + STORAGE CLEANUP)
# ==============================
@app.before_request
def cleanup_old_cards_scanner():
    """
    Automatic Scanner.
    1. Check if 13 hours passed since last cleanup.
    2. If Yes: Delete cards older than 24 hours.
    3. Also: Delete associated files from Supabase Storage.
    4. Update last cleanup time.
    """
    # Huwag scan sa static files (css, js) para mabilis
    if request.path.startswith('/static'): return

    try:
        db = get_db()

        # 1. KUNIN ANG LAST CLEANUP TIME SA 'idgenerate' TABLE
        # FIXED: Sort by id desc to ensure we hit controller row
        response = db.from_('idgenerate').select('last_card_cleanup').order('id', desc=True).limit(1).execute()
        
        last_cleanup = None
        if response.data and response.data[0]:
            raw_time = response.data[0].get('last_card_cleanup')
            if raw_time:
                last_cleanup = datetime.fromisoformat(raw_time)

        # 2. CALCULATE INTERVAL
        now = datetime.now()
        time_since_last_cleanup = timedelta(0)

        if last_cleanup:
            time_since_last_cleanup = now - last_cleanup

        # 3. CONDITION: LANG MAG-SCAN KUNG 13 HOURS NA ANG NAKAKARAAN
        if time_since_last_cleanup < timedelta(hours=13):
            return # Fresh pa ang scan, huwag gumulo sa system.

        print(f">>> SCANNING OLD CARDS... Last scan was {time_since_last_cleanup} ago.")

        # 4. DELETE LOGIC: DELETE ANG > 24 HOURS + STORAGE CLEANUP
        # Yung '2 hours pa lang' ay hindi dito mapupunta.
        expiry_time = now - timedelta(hours=24)

        # === NEW: SELECT MUNA PARA MAKUHA NG FILENAME (RULE #6) ===
        to_delete_response = db.from_('members').select('id', 'generated_card_image') \
            .lt('generated_at', expiry_time.isoformat()).execute()
        
        if to_delete_response.data:
            ids_to_clear = []
            files_to_remove = []
            
            for record in to_delete_response.data:
                url = record.get('generated_card_image')
                db_id = record.get('id')
                
                if db_id: ids_to_clear.append(db_id)
                
                # EXTRACT FILENAME FROM URL
                # URL Example: https://xyz.supabase.co/storage/v1/object/public/public_id_cards/guardian_ids/123_2023.png
                if url:
                    try:
                        if '/public_id_cards/' in url:
                            filename = url.split(f'/public_id_cards/')[-1]
                            if filename: files_to_remove.append(filename)
                    except:
                        pass

            # === ACTION 1: DELETE FROM SUPABASE STORAGE ===
            if files_to_remove:
                try:
                    # Automatic deletion mula sa Storage
                    supabase.storage.from_('public_id_cards').remove(files_to_remove)
                    print(f">>> DELETED {len(files_to_remove)} FILES FROM STORAGE.")
                except Exception as e:
                    print(f">>> Error deleting from storage: {e}")

            # === ACTION 2: UPDATE DATABASE (NULLIFY) ===
            if ids_to_clear:
                db.from_('members').update({
                    'generated_card_image': None,
                    'generated_at': None
                }).in_('id', ids_to_clear).execute()
                
                print(f">>> CLEANED UP {len(ids_to_clear)} EXPIRED CARDS (Database + Storage).")

        # 5. UPDATE LAST CLEANUP TIME (Reset Clock ng Scanner)
        db.from_('idgenerate').update({'last_card_cleanup': now.isoformat()}).execute()

    except Exception as e:
        print(f"Auto-cleanup error: {e}")

# ==============================
# Routes - Home & Navigation
# ==============================
@app.route('/')
def home():
    return render_template('placeholder_members.html')

@app.route('/members')
def members_redirect():
    return redirect(url_for('home'))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return "<h1>Contact Page Placeholder</h1>"

# ==============================
# Route: Original Login (Clean / Not Done Yet)
# ==============================
@app.route('/login')
def login():
    # Requirement: "yung login naman ay clean mo lang pag click sabihin lang na hindi pa tapos"
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login</title>
        <style>
            body { font-family: sans-serif; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; background-color: #f3f4f6; color: #333; margin: 0; }
            h1 { color: #ef4444; }
            p { font-size: 1.2rem; }
            a { text-decoration: none; color: #2563eb; font-weight: bold; margin-top: 20px; border: 2px solid #2563eb; padding: 10px 20px; border-radius: 5px; }
            a:hover { background-color: #2563eb; color: white; }
        </style>
    </head>
    <body>
        <h1>UNDER CONSTRUCTION</h1>
        <p>Ang feature na ito ay hindi pa tapos.</p>
        <a href="/"> &larr; Bumalik sa Home</a>
    </body>
    </html>
    """ 

# ==============================
# ADMIN ROUTE (Password Protected)
# ==============================
@app.route('/admin', methods=['GET', 'POST'])
def admin_login_route():
    """
    Admin Route: Checks for 'admin123' password before showing admin.html
    Ito ang tatawagin kapag cinlick ang Admin Menu.
    """
    error = None
    if request.method == 'POST':
        password = request.form.get('password')
        # TEMPORARY PASSWORD: admin123
        if password == 'admin123':
            # Tama ang password, tatawagin ang admin.html
            return render_template('admin.html')
        else:
            # FIXED: Tagalog error message (Exam Style - no answer given)
            error = "Mali ang password. Subukan mo ulit."

    # Simple Login Form (Server-side rendered)
    login_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Login</title>
        <style>
            body { font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background: #1f2937; color: white; margin: 0; }
            .box { background: white; color: #333; padding: 40px; border-radius: 10px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.5); min-width: 300px; }
            input { padding: 12px; width: 100%; margin: 15px 0; box-sizing: border-box; border: 1px solid #ccc; border-radius: 5px; font-size: 16px; }
            button { padding: 12px 20px; background: #2563eb; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; width: 100%; font-weight: bold; }
            button:hover { background: #1d4ed8; }
            .error { color: red; font-size: 0.9rem; margin-top: 10px; }
            .back-link { display: block; margin-top: 20px; font-size: 0.9rem; color: #888; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="box">
            <h2>Admin Access</h2>
            <p>Restricted Area</p>
            <form method="POST">
                <input type="password" name="password" placeholder="Ilagay ang Password" required autofocus>
                <button type="submit">LOGIN</button>
            </form>
            <p class="error">""" + (str(error) if error else "") + """</p>
            <a href="/" class="back-link">Back to Home</a>
        </div>
    </body>
    </html>
    """
    return login_html

# ==============================
# ROUTE: SIGNATURE PAGE RENDER (FIXED)
# ==============================
# NAGBAGO: Binago ko ang route sa '/signature.html' para tumugma sa tawag ng window.open sa admin.html
@app.route('/signature.html')
def officer_signature():
    """Tawagin ito kapag napili ang 'Officer Signature' sa Admin Forms."""
    return render_template('signature.html')

# ==============================
# NEW: ROUTE FOR MODE OF PAYMENT
# ==============================
@app.route('/mode_payment.html')
def mode_payment():
    """Tawagin ito kapag napili ang 'Mode of Payment' sa Admin Forms."""
    return render_template('mode_payment.html')

# ==============================
# NEW: ROUTE FOR CAPTION CHANGER
# ==============================
@app.route('/caption_changer.html')
def caption_changer():
    """Tawagin ito kapag napili ang 'Caption Changer' sa Admin Forms."""
    return render_template('caption_changer.html')

# ==============================
# SEARCH ROUTES
# ==============================
@app.route("/search")
def search_form():
    return render_template("search_form.html")

@app.route("/search-members", methods=["POST"])
def search_members():
    """
    Handles form submission (Server-side rendering).
    Highlights search terms.
    """
    try:
        db = get_db()
        raw_search = request.form.get("search_term")
        search_type = request.form.get("search_type") or "all"
        search_term = vb6_replace(raw_search).lower()

        # Default Logic: Show all if empty
        if not search_term:
            response = db.from_('members').select('*').order('name', desc=False).execute()
            members = response.data if response.data else []
            return render_template("search_results.html", members=members, total_results=len(members))

        # Construct Supabase OR Logic
        or_logic = ""
        
        if search_type == "all":
            or_logic = ",".join([
                f"name.ilike.%{search_term}%",
                f"chapter.ilike.%{search_term}%",
                f"designation.ilike.%{search_term}%",
                f"contact_no.ilike.%{search_term}%",
                f"blood_type.ilike.%{search_term}%",
                f"home_address.ilike.%{search_term}%",
                f"pseudo_name.ilike.%{search_term}%"
            ])
        elif search_type == "name":
            or_logic = f"name.ilike.%{search_term}%,pseudo_name.ilike.%{search_term}%"
        elif search_type == "chapter":
            or_logic = f"chapter.ilike.%{search_term}%"
        elif search_type == "designation":
            or_logic = f"designation.ilike.%{search_term}%"
        elif search_type == "contact":
            or_logic = f"contact_no.ilike.%{search_term}%"
        else:
            or_logic = f"name.ilike.%{search_term}%"

        response = db.from_('members').select('*').or_(or_logic).order('name', desc=False).execute()
        members = response.data if response.data else []

        # Highlight Function (Regex)
        def highlight(text):
            if not text: return ""
            regex = re.compile(re.escape(search_term), re.IGNORECASE)
            return regex.sub(lambda m: f'<span class="highlight">{m.group(0)}</span>', text)

        # Apply highlights
        for m in members:
            m['name'] = highlight(m.get('name', ''))
            m['chapter'] = highlight(m.get('chapter', ''))
            m['designation'] = highlight(m.get('designation', ''))
            m['contact_no'] = highlight(m.get('contact_no', ''))
            m['blood_type'] = highlight(m.get('blood_type', ''))
            m['home_address'] = highlight(m.get('home_address', ''))
            m['pseudo_name'] = highlight(m.get('pseudo_name', ''))

        return render_template(
            "search_results.html",
            members=members,
            search_term=search_term,
            search_type=search_type,
            total_results=len(members)
        )

    except Exception as e:
        print(f"Search Error: {e}")
        return f"Error loading members: {str(e)}", 500

# ==============================
# MEMBER API ROUTES
# ==============================
@app.route('/api/members/json', methods=["GET"])
def api_members_json():
    """Returns raw list of members for DataTables or JS Grid."""
    try:
        db = get_db()
        response = db.from_('members').select('*').order('name', desc=False).execute()
        return jsonify(response.data)
    except Exception as e:
        print(f"API Error: {e}")
        return jsonify([]), 500

# ============================================================
# 🆕 ULTIMATE FIX ROUTE: SIGNATURETABLE API (COMBO BOX)
# ============================================================
@app.route('/api/signaturetable/json', methods=["GET"])
def api_signaturetable_json():
    """
    Fetches list from SIGNATURETABLE for the Combo Box.
    Robust: Uses '*' select to handle any case of 'name' column.
    """
    try:
        db = get_db()
        
        # SELECT '*' para makuha kahit anong case ang column (name, Name, NAME)
        response = db.from_('signaturetable').select('*').execute()
        
        data = []
        if response.data:
            for item in response.data:
                # Kunin yung value kahit 'name', 'Name', o 'NAME' ang key
                val = item.get("name") or item.get("Name") or item.get("NAME")
                
                if val:
                    # Standardize key to 'name' (lowercase) for the frontend
                    data.append({"name": val})
                    
        return jsonify(data)
    except Exception as e:
        # I-print sa Python Terminal para makita natin yung tunay na error
        print(f"ERROR fetching signature table: {e}")
        # Ibalik ang error message sa response para alam natin
        return jsonify({"error": str(e)}), 500

@app.route('/api/members/search', methods=["GET"])
def api_members_search():
    """Live search endpoint (Name OR Pseudo Name OR Chapter)."""
    try:
        db = get_db()
        q = request.args.get('q', '').strip()
        if not q: return jsonify([])
        or_logic = f"name.ilike.%{q}%,pseudo_name.ilike.%{q}%,chapter.ilike.%{q}%"
        response = db.from_('members').select('*').or_(or_logic).limit(20).execute()
        return jsonify(response.data)
    except Exception as e:
        print(f"Autocomplete Error: {e}")
        return jsonify([]), 500

@app.route('/api/members/by-date', methods=["GET"])
def api_members_by_date():
    """Filter members by date_of_membership."""
    try:
        db = get_db()
        selected_date = request.args.get('date')
        if not selected_date: return jsonify([]), 400
        response = db.from_('members').select('*').eq('date_of_membership', selected_date).order('name', desc=False).execute()
        return jsonify(response.data)
    except Exception as e:
        print(f"Filter Date Error: {e}")
        return jsonify([]), 500

# ==============================
# MEMBER CRUD LOGIC
# ==============================
@app.route('/add_member', methods=['GET', 'POST'])
def add_member():
    """Handles creating new members AND updating existing ones."""
    if request.method == 'POST':
        try:
            db = get_db()
            form_action = request.form.get('form_action') 
            record_id = request.form.get('member_id')
            
            form_data = {
                'idnumb': request.form.get('id_no'),
                'name': request.form.get('name'),
                'gender': request.form.get('gender'),
                'birthdate': request.form.get('birthdate'),
                'civil_status': request.form.get('civil_status'),
                'country': request.form.get('country'),
                'blood_type': request.form.get('blood_type'),
                'designation': request.form.get('designation', ''),
                'chapter': request.form.get('chapter', ''),
                'date_of_membership': request.form.get('date_of_membership'),
                'membership_type': request.form.get('membership_type'),
                'contact_no': request.form.get('contact_no', ''),
                'email': request.form.get('email'),
                'home_address': request.form.get('home_address', ''),
                'height': request.form.get('height'),
                'weight': request.form.get('weight'),
                'occupation': request.form.get('occupation'),
                'govt_id_presented': request.form.get('govt_id_presented'),
                'govt_id_no': request.form.get('govt_id_no'),
                'emergency_person_name': request.form.get('emergency_person_name'),
                'emergency_contact_no': request.form.get('emergency_contact_no'),
                'emergency_address': request.form.get('emergency_address'), 
                'photo_data': request.form.get('photo_data'), 
                'qr_code': request.form.get('qr_code'),
                'signature': request.form.get('signature'),
                'pseudo_name': request.form.get('pseudo_name'),
                'issued_date': datetime.now().strftime('%Y-%m-%d'),
                'valid_until': (datetime.now() + timedelta(days=365*3)).strftime('%Y-%m-%d')
            }

            if form_action == 'update' and record_id:
                new_photo = request.form.get('photo_data')
                if not new_photo or new_photo == "data,": 
                    form_data.pop('photo_data', None)
                db.from_('members').update(form_data).eq('id', record_id).execute()
                print(f"Updated Member ID: {record_id}")
            else:
                db.from_('members').insert(form_data).execute()
                print("Added New Member")
            
            return redirect(url_for('home'))

        except Exception as e:
            print(f"Add/Update Error: {e}")
            return f"Error processing member: {str(e)}", 500

    return render_template('add_member_form.html')

@app.route('/delete_member/<int:member_id>', methods=["DELETE"])
def delete_member(member_id):
    """Deletes a member via AJAX/Fetch."""
    try:
        db = get_db()
        db.from_('members').delete().eq('id', member_id).execute()
        return jsonify({'success': True, 'message': 'Member deleted successfully'})
    except Exception as e:
        print(f"Delete Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==============================
# LAYOUT EDITOR LOGIC (UPDATED)
# ==============================
@app.route('/save_layout', methods=['POST'])
def save_layout():
    """
    Updated: Saves layout SPECIFICALLY per client_slug (Carbon Copy).
    If client_slug exists -> Update. If not -> Insert.
    """
    try:
        payload = request.json
        db = get_db()
        
        # 1. GET CLIENT SLUG FROM PAYLOAD
        client_slug = payload.get('client_slug')

        if not client_slug:
            # Fallback: Save generic if no client selected (Old behavior)
            # FIXED: Sort by created_at desc to ensure we update the latest layout
            response = db.from_('layouts').select("*").order('created_at', desc=True).limit(1).execute()
            existing_data = response.data
            
            if existing_data and len(existing_data) > 0:
                record_id = existing_data[0]['id']
                db.from_('layouts').update({"config_json": payload}).eq('id', record_id).execute()
            else:
                db.from_('layouts').insert({"config_json": payload}).execute()
        else:
            # 2. CARBON COPY LOGIC: Check existing layout for this specific company
            response = db.from_('layouts').select("*").eq('client_slug', client_slug).execute()
            existing_data = response.data
            
            if existing_data and len(existing_data) > 0:
                # UPDATE: May existing na sa company na 'to
                record_id = existing_data[0]['id']
                db.from_('layouts').update({"config_json": payload}).eq('id', record_id).execute()
                print(f">>> UPDATED LAYOUT FOR: {client_slug}")
            else:
                # INSERT: Bagong company entry
                db.from_('layouts').insert({"config_json": payload, "client_slug": client_slug}).execute()
                print(f">>> INSERTED NEW LAYOUT FOR: {client_slug}")

        return jsonify({"status": "success", "message": "Layout saved successfully!"}), 200

    except Exception as e:
        print(f"Error saving layout: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/load_layout', methods=['GET'])
def load_layout():
    """
    Updated: Loads layout SPECIFICALLY per client_slug.
    If no client_slug provided -> Load latest (Fallback).
    """
    try:
        db = get_db()
        
        # 1. GET CLIENT SLUG FROM URL PARAMS
        client_slug = request.args.get('client_slug')
        
        if client_slug:
            # Load specific company
            response = db.from_('layouts').select("*").eq('client_slug', client_slug).execute()
            print(f">>> LOADING LAYOUT FOR: {client_slug}")
        else:
            # Fallback: Load latest layout
            response = db.from_('layouts').select("*").order('created_at', desc=True).limit(1).execute()
        
        data = response.data
        if not data:
            return jsonify({"status": "error", "message": "No saved layout found."}), 404
        return jsonify({"status": "success", "data": data[0]['config_json']}), 200

    except Exception as e:
        print(f"Error loading layout: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==============================
# 🆕 NEW: FETCH CLIENT SLUGS (FOR ADMIN COMBO BOX)
# ==============================
@app.route('/api/layouts', methods=['GET'])
def get_client_slugs():
    """
    Fetches unique client_slug from layouts table.
    Ito ang tatawagin ng admin.html combo box.
    """
    try:
        db = get_db()
        
        # 1. Kunin lahat ng client_slug
        response = db.from_('layouts').select('client_slug').execute()
        
        if response.data:
            # 2. Kunin lang yung UNIQUE values (Wang duplicate)
            seen = set()
            unique_slugs = []
            
            for item in response.data:
                slug = item.get('client_slug')
                if slug and slug.strip() != "":
                    if slug not in seen:
                        seen.add(slug)
                        unique_slugs.append({ 'client_slug': slug })
            
            return jsonify(unique_slugs), 200
        else:
            return jsonify([]), 200
            
    except Exception as e:
        print(f">>> ERROR fetching client slugs: {e}")
        return jsonify([]), 500

# ==============================
# 🆕 NEW ROUTE: SAVE ID NUMBER PER CLIENT (THE ID GENERATOR)
# ==============================
@app.route('/save_id_for_client', methods=['POST'])
def save_id_for_client():
    """
    Saves or Updates ID Number for a specific Company/Client.
    CARBON COPY: Kung existing na -> Update. Kung wala -> Insert.
    """
    try:
        db = get_db()
        data = request.json
        
        client_slug = data.get('client_slug')
        idnumber = data.get('idnumber')

        if not client_slug or not idnumber:
            return jsonify({'success': False, 'message': 'Missing Client or ID Number'}), 400

        # CHECK KUNG MAY EXISTING NA BA
        response = db.from_('idgenerate').select('*').eq('client_slug', client_slug).execute()
        
        if response.data:
            # UPDATE (CARBON COPY: I-update lang yung existing na record)
            db.from_('idgenerate').update({'idnumber': idnumber}).eq('client_slug', client_slug).execute()
            print(f">>> UPDATED ID for {client_slug}: {idnumber}")
        else:
            # INSERT (New Company Entry)
            db.from_('idgenerate').insert({'idnumber': idnumber, 'client_slug': client_slug}).execute()
            print(f">>> INSERTED NEW ID for {client_slug}: {idnumber}")

        return jsonify({'success': True, 'message': 'ID Number saved successfully!'}), 200

    except Exception as e:
        print(f"Error saving ID for client: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==============================
# 🆕 CAPTION CHANGER ROUTES (API)
# ==============================
@app.route('/api/get_settings', methods=['GET'])
def api_get_settings():
    return jsonify(get_system_settings())

@app.route('/api/save_settings', methods=['POST'])
def api_save_settings():
    try:
        db = get_db()
        data = request.json
        
        main_title = data.get('main_title')
        sub_title = data.get('sub_title')
        company_name = data.get('company_name')
        logo_base64 = data.get('logo_data') # Kung may upload na bago

        # Logic para sa Logo Upload
        logo_url_to_save = None
        
        if logo_base64 and logo_base64 != "":
            # Upload to Supabase Storage
            bucket_name = "public_id_cards"
            filename = "client_logos/current_logo.png" # Static filename, overwrites always
            
            try:
                # Decode Base64
                if "," in logo_base64:
                    base64_string = logo_base64.split(",")[1]
                else:
                    base64_string = logo_base64
                
                image_bytes = base64.b64decode(base64_string)
                
                # Create Temp File
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                    tmp_file.write(image_bytes)
                    temp_path = tmp_file.name
                
                # Upload
                options = {"content-type": "image/png", "upsert": "true"}
                supabase.storage.from_(bucket_name).upload(path=filename, file=temp_path, file_options=options)
                
                # Cleanup
                os.remove(temp_path)
                
                # Get URL
                logo_url_to_save = supabase.storage.from_(bucket_name).get_public_url(filename)
                print(f">>> Logo Uploaded: {logo_url_to_save}")
                
            except Exception as upload_err:
                print(f">>> Logo Upload Error: {upload_err}")
                # Pag nagerror sa upload, huwag na lang palitan yung logo sa DB
                pass

        # I-construct ang payload para sa Database
        update_payload = {
            'main_title': main_title,
            'sub_title': sub_title,
            'company_name': company_name
        }
        
        # Lang i-update yung logo_url kung successful yung upload
        if logo_url_to_save:
            update_payload['logo_url'] = logo_url_to_save

        db.from_('system_settings').update(update_payload).eq('id', 1).execute()

        return jsonify({'success': True, 'message': 'Settings saved successfully!'})
        
    except Exception as e:
        print(f">>> Save Settings Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==============================
# ADMIN FORMS ROUTES (ACTIVE - Connected to Supabase)
# ==============================

@app.route('/get_admin_forms', methods=['GET'])
def get_admin_forms():
    """Fetches all forms from admin_forms table."""
    try:
        db = get_db()
        response = db.from_('admin_forms').select("*").order('created_at', desc=True).execute()
        
        if response.data:
            return jsonify(response.data), 200
        return jsonify([]), 200
    except Exception as e:
        print(f">>> ERROR CONNECTING TO SUPABASE (get_admin_forms): {e}")
        return jsonify([]), 500

@app.route('/add_admin_form', methods=['POST'])
def add_admin_form():
    """Saves new form name to admin_forms table."""
    try:
        db = get_db()
        data = request.json
        forms_name = data.get('forms_name')

        if not forms_name:
            return jsonify({'success': False, 'message': 'Form name is required'}), 400

        response = db.from_('admin_forms').insert({"forms_name": forms_name}).execute()

        return jsonify({
            'success': True, 
            'message': f'Form "{forms_name}" saved successfully!',
            'data': response.data
        }), 200
    except Exception as e:
        print(f"Error saving admin form: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/delete_admin_form/<int:id>', methods=['DELETE'])
def delete_admin_form(id):
    """Deletes a form from admin_forms table by ID."""
    try:
        db = get_db()
        db.from_('admin_forms').delete().eq('id', id).execute()
        
        return jsonify({'success': True, 'message': 'Form deleted successfully'}), 200
    except Exception as e:
        print(f"Error deleting admin form: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==============================
# OFFICER SIGNATURE LOGIC (Complete CRUD)
# ==============================

# 1. GET LIST (Para sa Table/Listbox sa HTML)
@app.route('/get_officers_list', methods=['GET'])
def get_officers_list():
    """Returns all officers from officer_list table."""
    try:
        db = get_db()
        response = db.from_('officer_list').select("*").order('created_at', desc=True).execute()
        return jsonify(response.data), 200
    except Exception as e:
        print(f"Error fetching officers: {e}")
        return jsonify([]), 500

# 2. SAVE NEW (POST) - Para sa "Add New" button
@app.route('/save_officer_signature', methods=['POST'])
def save_officer_signature():
    """Saves officer name and signature (Base64) to Supabase."""
    try:
        db = get_db()
        data = request.json

        name_officer = data.get('name_officer')
        designation = data.get('designation')  
        man_signature = data.get('man_signature') 
        text_signature = data.get('text_signature', '') 

        if not name_officer or not man_signature:
            return jsonify({'success': False, 'message': 'Name and Signature are required'}), 400

        payload = {
            'name_officer': name_officer,
            'designation': designation,
            'man_signature': man_signature,
            'text_signature': text_signature
        }

        response = db.from_('officer_list').insert(payload).execute()

        return jsonify({
            'success': True, 
            'message': f'Signature for {name_officer} saved successfully!',
            'data': response.data
        }), 200

    except Exception as e:
        print(f"Save Signature Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# 3. GET SINGLE (For Edit) - Para i-load sa canvas
@app.route('/get_officer/<int:officer_id>', methods=['GET'])
def get_officer(officer_id):
    """Fetches a single officer's details for editing."""
    try:
        db = get_db()
        response = db.from_('officer_list').select("*").eq('id', officer_id).execute()
        
        if response.data:
            return jsonify({'success': True, 'data': response.data[0]}), 200
        else:
            return jsonify({'success': False, 'message': 'Officer not found'}), 404
            
    except Exception as e:
        print(f"Error fetching officer: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# 4. UPDATE (PUT) - Para sa Save pag naka-Edit mode
@app.route('/update_officer_signature/<int:officer_id>', methods=['PUT'])
def update_officer_signature(officer_id):
    """Updates an existing officer's signature."""
    try:
        db = get_db()
        data = request.json

        name_officer = data.get('name_officer')
        designation = data.get('designation')
        man_signature = data.get('man_signature')
        text_signature = data.get('text_signature', '')

        if not name_officer or not man_signature:
            return jsonify({'success': False, 'message': 'Name and Signature are required'}), 400

        payload = {
            'name_officer': name_officer,
            'designation': designation,
            'man_signature': man_signature,
            'text_signature': text_signature
        }

        response = db.from_('officer_list').update(payload).eq('id', officer_id).execute()

        return jsonify({
            'success': True, 
            'message': f'Officer {name_officer} updated successfully!',
            'data': response.data
        }), 200

    except Exception as e:
        print(f"Update Signature Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# 5. DELETE (DELETE) - Para sa Delete button
@app.route('/delete_officer/<int:officer_id>', methods=['DELETE'])
def delete_officer(officer_id):
    """Deletes an officer by ID."""
    try:
        db = get_db()
        db.from_('officer_list').delete().eq('id', officer_id).execute()
        return jsonify({'success': True, 'message': 'Officer deleted successfully'}), 200
    except Exception as e:
        print(f"Error deleting officer: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==============================
# HEALTH CHECK & SETTINGS
# ==============================
@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

@app.route('/get_current_id')
def get_current_id():
    """
    Updated: Fetches ID format based on selected client_slug.
    If client_slug is provided, gets specific ID. Else, gets latest ID.
    """
    try:
        db = get_db()
        client_slug = request.args.get('client_slug')

        if client_slug:
            # NEW LOGIC: Hanapin specific na ID para sa company na to
            response = db.from_('idgenerate').select('*').eq('client_slug', client_slug).limit(1).execute()
            
            if response.data:
                return jsonify({'idnumber': response.data[0].get('idnumber')})
            else:
                # Walang nahanap na ID format para sa company na to
                return jsonify({'idnumber': ''})
        else:
            # OLD LOGIC: Kunin yung last created kahit walang slug (Fallback)
            response = db.from_('idgenerate').select('*').order('id', desc=True).limit(1).execute()
            if response.data:
                return jsonify({'idnumber': response.data[0].get('idnumber')})
            return jsonify({'idnumber': ''})

    except Exception as e:
        print(f"Error getting ID: {e}")
        return jsonify({'idnumber': ''})

@app.route('/save_id_to_db', methods=['POST'])
def save_id_to_db():
    """Saves or Updates ID format in settings."""
    try:
        db = get_db()
        data = request.json
        id_value = data.get('id_value')
        if not id_value:
            return jsonify({'success': False, 'message': 'No ID value provided'}), 400

        check_response = db.from_('idgenerate').select('id').order('id', desc=True).limit(1).execute()
        if check_response.data:
            record_id = check_response.data[0].get('id')
            db.from_('idgenerate').update({"idnumber": id_value}).eq('id', record_id).execute()
        else:
            db.from_('idgenerate').insert({"idnumber": id_value}).execute()

        return jsonify({'success': True, 'message': 'ID saved successfully!', 'id': id_value})
    except Exception as e:
        print(f"Error saving ID: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==============================
# TEST PAGE ROUTE
# ==============================
@app.route('/test')
def test_page():
    return render_template('test.html')

# ==============================
# REDIRECTS
# ==============================
@app.route('/display_id/<int:member_id>')
def display_id(member_id):
    return redirect(url_for('id_pdf_generator'))

@app.route('/id_pdf_generator')
def id_pdf_generator():
    return render_template('id_pdf_generator.html')

@app.route('/phone_viewer')
def phone_viewer():
    """Displays all member ID cards in phone view"""
    return render_template('phone_viewer.html')

# ==============================
# NEW: VIEW PHONE (CELPHONE ONLY / USER FRIENDLY)
# ==============================
@app.route('/view_phone')
def view_phone():
    """
    Celphone Only ID Viewer (User Friendly).
    Direct access for members to select name and download ID without Admin tools.
    """
    return render_template('view_phone.html', supabase_url=SUPAB_URL)

# ==============================
# FIXED: SAVE CARD IMAGE (Temp File Method + STATIC FILENAME)
# ==============================
@app.route('/save_card_image', methods=['POST'])
def save_card_image():
    # Helper logging
    def log(message):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open("error_log.txt", "a") as f:
            f.write(f"\n[{timestamp}] {message}")
        print(message)

    log(">>> ROUTE TRIGGERED: Save Card")

    try:
        db = get_db()
        data = request.json
        member_id = data.get('member_id')
        image_data = data.get('image_data') 

        if not member_id or not image_data:
            log(">>> ERROR: Missing member_id or image_data")
            return jsonify({'success': False, 'message': 'Missing data'}), 400

        log(f">>> Processing Member ID: {member_id}")

        # --- STEP1: DECODE BASE64 ---
        try:
            if "," in image_data:
                base64_string = image_data.split(",")[1]
            else:
                base64_string = image_data
            
            image_bytes = base64.b64decode(base64_string)
            log(f">>> Decoded Image Size: {len(image_bytes)} bytes")
        except Exception as decode_err:
            log(f">>> DECODING ERROR: {decode_err}")
            return jsonify({'success': False, 'message': 'Invalid Image Data'}), 400

        # --- STEP2: UPLOAD TO SUPABASE STORAGE (Using Temp File) ---
        bucket_name = "public_id_cards" 
        
        # --- UPDATE: STATIC FILENAME (Overwrite instead of Duplicate) ---
        filename = f"guardian_ids/{member_id}.png"
        log(f">>> Target Path: {bucket_name}/{filename} (Mode: OVERWRITE)")
        
        try:
            # A. Create a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                tmp_file.write(image_bytes)
                temp_path = tmp_file.name
            
            log(f">>> Created Temp File: {temp_path}")

            # B. Prepare options
            options = {
                "content-type": "image/png",
                "upsert": "true"  # <--- NAG-IISA LANG ANG FILE PER MEMBER
            }

            # C. Upload using File Path (String)
            upload_response = supabase.storage.from_(bucket_name).upload(
                path=filename, 
                file=temp_path,  # <-- String path, not io.BytesIO
                file_options=options
            )
            
            log(f">>> Upload Response: {upload_response}")

            # D. Delete temporary file after upload (Cleanup)
            try:
                os.remove(temp_path)
                log(f">>> Deleted Temp File: {temp_path}")
            except:
                pass # Hindi critical kung di ma-delete temp file

            log(">>> UPLOAD SEEMS SUCCESSFUL")

        except Exception as upload_err:
            # Clean up temp file if error occurs
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.remove(temp_path)
                
            error_msg = str(upload_err)
            log(f">>> UPLOAD EXCEPTION: {error_msg}")
            
            if "Bucket not found" in error_msg:
                return jsonify({'success': False, 'message': 'Bucket "public_id_cards" does not exist.'}), 500
            elif "Permission denied" in error_msg:
                return jsonify({'success': False, 'message': 'Storage Permission Denied. Check Service Key.'}), 500
                
            return jsonify({'success': False, 'message': f"Upload Failed: {error_msg}"}), 500

        # --- STEP3: GET PUBLIC URL ---
        try:
            image_url_data = supabase.storage.from_(bucket_name).get_public_url(filename)
            log(f">>> Public URL: {image_url_data}")
        except Exception as url_err:
            log(f">>> URL ERROR: {url_err}")
            # Fallback manual URL construction
            image_url_data = f"{SUPAB_URL}/storage/v1/object/public/{bucket_name}/{filename}"

        # --- STEP4: SAVE URL TO DATABASE ---
        try:
            payload = {
                'generated_card_image': image_url_data, 
                'generated_at': datetime.now().isoformat()
            }
            db.from_('members').update(payload).eq('id', member_id).execute()
            log(">>> DATABASE UPDATE SUCCESS")
        except Exception as db_err:
            log(f">>> DATABASE ERROR: {db_err}")
            return jsonify({'success': False, 'message': f"DB Error: {str(db_err)}"}), 500

        return jsonify({'success': True, 'message': 'ID Card saved successfully.', 'url': image_url_data})

    except Exception as e:
        log(f">>> FATAL ERROR (Outer Loop): {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

## ==============================
# UPDATED: BATCH DELETE CARDS (Case Sensitive Fix)
# ==============================
@app.route('/delete_cards_batch', methods=['POST'])
def delete_cards_batch():
    """
    Deletes generated IDs for a list of members.
    FIX: Handles both .png and .PNG to catch Case Sensitive issues.
    """
    try:
        db = get_db()
        data = request.json
        member_ids = data.get('member_ids')

        if not member_ids:
            return jsonify({'success': False, 'message': 'No members selected'}), 400

        print(f">>> BATCH DELETE INITIATED for {len(member_ids)} members.")

        # --- STEP1: GATHER FILES TO DELETE ---
        files_to_remove = set() 

        # A. KUNIN YUNG NAKASULAT SA DATABASE (Old Files)
        print(">>> Checking Database for Files...")
        get_members = db.from_('members').select('id', 'generated_card_image') \
            .in_('id', member_ids).execute()
        
        if get_members.data:
            for record in get_members.data:
                url = record.get('generated_card_image')
                if url:
                    try:
                        if '/public_id_cards/' in url:
                            filename = url.split(f'/public_id_cards/')[-1]
                            files_to_remove.add(filename)
                            print(f"   -> Found in DB: {filename}")
                    except Exception as e:
                        print(f"   -> Error splitting URL: {e}")

        # B. DAGDAGIN ANG STATIC FILENAMES (Case Sensitive!)
        # Buburahin natin BOTH: lower case AND upper case extensions.
        # Para siguradong mapatay kahit anong klaseng extension.
        print(">>> Adding Standard Filenames (.png & .PNG)...")
        for mid in member_ids:
            lower_case = f"guardian_ids/{mid}.png"
            upper_case = f"guardian_ids/{mid}.PNG"
            
            files_to_remove.add(lower_case)
            files_to_remove.add(upper_case)
            
            print(f"   -> Adding: {lower_case} & {upper_case}")

        # Convert set to list
        final_list = list(files_to_remove)
        
        print(f">>> TOTAL COMMANDS PREPARED: {len(final_list)}")
        print(f">>> SENDING COMMANDS TO SUPABASE: {final_list}")

        # --- STEP2: EXECUTE DELETE ---
        if final_list:
            try:
                response = supabase.storage.from_('public_id_cards').remove(final_list)
                print(">>> DELETE COMMAND SENT SUCCESSFULLY.")
                print(">>> CHECK SUPABASE DASHBOARD NOW.")
            except Exception as e:
                print(f">>> STORAGE DELETE ERROR: {e}")
                print(">>> BUT WE WILL STILL CLEAR DATABASE.")
        else:
            print(">>> No files found to delete.")

        # --- STEP3: CLEAR DATABASE ---
        payload = {
            'generated_card_image': None,
            'generated_at': None
        }
        db.from_('members').update(payload).in_('id', member_ids).execute()

        return jsonify({
            'success': True, 
            'message': f'Delete commands sent for {len(member_ids)} members.'
        }), 200

    except Exception as e:
        print(f">>> BATCH DELETE GENERAL ERROR: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==============================
# NEW: BUCKET ONLY LIST (Lolo's Rule + SUPER RESCUE MODE)
# ==============================
@app.route('/api/storage/list-all', methods=['GET'])
def list_bucket_only():
    """
    Lahat ng nasa bucket, ilalabas.
    Hindi na tayo magho-hibernate ng file.
    
    === LATEST FIX: AUTO RESCUE MODE ===
    Kung mawala yung folder, hindi na tayo babagsak.
    Mag-a-attempt ito mag-Upload ng fake file para ma-recreate ang folder.
    """
    try:
        bucket_name = "public_id_cards"
        folder_path = "guardian_ids"

        # 1. LIST ALL FILES
        try:
            files_response = supabase.storage.from_(bucket_name).list(path=folder_path)
        except Exception as list_err:
            # NAG ERROR, BAKIT? KASI WALANG FOLDER.
            print(f">>> ERROR: Folder '{folder_path}' might be missing.")
            print(f">>> ATTEMPTING AUTO-RESCUE...")
            
            try:
                # Trick: Upload an empty string or dummy file to create folder
                # Note: Some Supabase versions allow creating folders via upload of 'folder/.empty'
                rescue_path = f"{folder_path}/.empty"
                
                # Create dummy content
                with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
                    tmp.write(b"folder_rescue")
                    tmp_path = tmp.name
                
                supabase.storage.from_(bucket_name).upload(
                    path=rescue_path, 
                    file=tmp_path,
                    file_options={"upsert": "true"}
                )
                os.remove(tmp_path)
                
                print(">>> RESCUE SUCCESS! Folder recreated.")
                # Try listing again
                files_response = supabase.storage.from_(bucket_name).list(path=folder_path)
            except Exception as rescue_err:
                print(f">>> RESCUE FAILED: {rescue_err}")
                # Pag talagang di makabuhay, return empty list nalang para di bumagsak UI
                return jsonify([]), 200
        
        # 2. PREPARE DATA (Lagyan ng URL para madaling i-display)
        result = []
        for f in files_response:
            # Iwasan yung .empty file na nilagay natin
            if f['name'] != '.empty':
                result.append({
                    'filename': f['name'],
                    'url': f"{SUPAB_URL}/storage/v1/object/public/{bucket_name}/{folder_path}/{f['name']}"
                })

        # 3. RETURN LIST (Sort by Filename para maayos)
        # Reverse (Descending) para yung pinaka-bago naka-sa taas
        return jsonify(sorted(result, key=lambda x: x['filename'], reverse=True)), 200

    except Exception as e:
        print(f">>> Error listing bucket: {e}")
        # Pag error, ibalik na lang empty list para di bumagsak yung app ni Lolo
        return jsonify([]), 200

# ============================================================
# 🆕 NEW ROUTE: DELETE ALL FILES IN BUCKET (The Missing Link)
# ============================================================
@app.route('/api/storage/delete-all', methods=['DELETE'])
def delete_all_bucket_files():
    """
    Ito ang tatawagin ng 'Burn' button.
    Burahin lahat ng files sa 'guardian_ids' folder.
    """
    try:
        bucket_name = "public_id_cards"
        folder_path = "guardian_ids"

        # 1. LIST MUNA ANG LAHAT NG FILENAMES
        # Kailangan muna nating malaman ang mga pangalan para ipasa sa remove function
        files_response = supabase.storage.from_(bucket_name).list(path=folder_path)
        
        filenames_to_delete = [f['name'] for f in files_response]

        # 2. CHECK KUNG MAY LAMAN
        if not filenames_to_delete:
            print(">>> Bucket is already empty.")
            return jsonify({'success': True, 'message': 'Bucket is already empty.'}), 200

        # 3. DELETE
        try:
            # Ipalitan lang natin ang simple filename sa "folder/filename" format
            # Supabase remove function ay kumakain ng list ng paths
            full_paths = [f"{folder_path}/{name}" for name in filenames_to_delete]
            
            print(f">>> BURNING {len(full_paths)} FILES...")
            supabase.storage.from_(bucket_name).remove(full_paths)
            
            return jsonify({'success': True, 'message': f'Deleted {len(full_paths)} files from bucket.'}), 200
            
        except Exception as e:
            print(f">>> Error deleting files: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500

    except Exception as e:
        print(f">>> General Error in delete-all: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ============================================================
# 🆕 NEW ROUTE: DOWNLOAD ZIP (For Celphone)
# ============================================================
@app.route('/api/storage/download-zip', methods=['POST'])
def download_zip_files():
    """
    I-Zip lahat ng selected files para sa easy download.
    """
    try:
        db = get_db()
        data = request.json
        filenames = data.get('filenames') # Expecting list: ["2.png", "16.png", etc.]

        if not filenames:
            return jsonify({'success': False, 'message': 'No files selected'}), 400

        print(f">>> ZIPPING {len(filenames)} files...")

        # 1. Gumawa ng ZIP sa Memory (BytesIO)
        memory_file = io.BytesIO()
        
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fname in filenames:
                # Full path in bucket
                file_path = f"guardian_ids/{fname}"
                
                try:
                    # 2. Download file from Supabase to Memory
                    # Note: .download() returns raw bytes
                    file_data = supabase.storage.from_('public_id_cards').download(file_path)
                    
                    # 3. Isulat sa Zip
                    zf.writestr(fname, file_data)
                    print(f"   -> Zipped: {fname}")
                except Exception as e:
                    print(f"   -> Failed to zip {fname}: {e}")

        # 4. Ibalik ang pointer sa simula ng Zip file
        memory_file.seek(0)

        # 5. Ibalik sa Browser as Download
        return send_file(
            memory_file, 
            mimetype='application/zip',
            as_attachment=True,
            download_name='All_ID_Cards.zip'
        )

    except Exception as e:
        print(f">>> ZIP ERROR: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ============================================================
# 🆕 NEW ROUTE: MAKE SIGNATURE PAGE (Standalone)
# ============================================================
@app.route('/make_signature')
def make_signature_route():
    """Tumutugon sa ✍️ button sa base.html."""
    return render_template('make_signature.html')

@app.route('/upload', methods=['POST'])
def upload_signature_standalone():
    if request.data is None or len(request.data) == 0:
        return jsonify({'error': 'No image data received'}), 400
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f'signature_{timestamp}.png'
    path = os.path.join(SIGN_DIR, secure_filename(filename))
    with open(path, 'wb') as f:
        f.write(request.data)
    return jsonify({'message': 'Signature uploaded', 'path': filename})

@app.route('/signature', methods=['DELETE'])
def delete_signature_standalone():
    path = last_signature_path()
    if not path:
        return jsonify({'message': 'No signature to delete'}), 404
    try:
        os.remove(path)
        return jsonify({'message': f'Deleted {os.path.basename(path)}'})
    except Exception as e:
        print(f"Error deleting signature: {e}")
        return jsonify({'message': 'Delete failed'}), 500

# ==============================
# NEW ROUTE: SAVE COMPANY SIGNATURE (Standalone Page) - UPDATED FOR UPSERT
# ==============================
@app.route('/save_company_signature', methods=['POST'])
def save_company_signature():
    """
    Saves signature directly to 'signaturetable'.
    LOGIC: Kung may existing na pangalan -> Update (Overwrite).
           Kung wala pang pangalan -> Insert (New Record).
    """
    try:
        db = get_db()
        data = request.json
        
        name = data.get('name')
        signature_data = data.get('signature')
        
        if not name or not signature_data:
            return jsonify({'success': False, 'message': 'Paki-lagay ng Pangalan at Pirma'}), 400
            
        # 1. CHECK KUNG MAY EXISTING NA BA (Carbon Copy Logic)
        # Tinitignan natin kung may record na sa table na kapareho ng 'name'
        response = db.from_('signaturetable').select('*').eq('name', name).execute()
        
        if response.data:
            # 2. UPDATE: May existing na sa pangalan na 'to
            # I-uupdate lang yung signature field, hindi na gumagawa ng bagong row
            db.from_('signaturetable').update({'signature': signature_data}).eq('name', name).execute()
            print(f">>> UPDATED SIGNATURE FOR: {name}")
            return jsonify({'success': True, 'message': f'Updated signature for {name}!'}), 200
            
        else:
            # 3. INSERT: Walang nahanap na pangalan, so gagawa ng bago
            payload = {
                'name': name,
                'signature': signature_data
            }
            db.from_('signaturetable').insert(payload).execute()
            print(f">>> INSERTED NEW SIGNATURE FOR: {name}")
            return jsonify({'success': True, 'message': f'Saved new signature for {name}!'}), 200
            
    except Exception as e:
        print(f"Error saving company signature: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==============================
# 🆕 ROUTE: GET SIGNATURE TABLE (For Company Signature Page ONLY) - FIXED
# ==============================
@app.route('/get_signaturetable', methods=['GET'])
def get_signature_table():
    """
    Fetches list from 'signaturetable'.
    Used for listing.
    FIXED: Field name updated to 'name' (lowercase)
    """
    try:
        db = get_db()
        
        # Fetch all records
        # FIXED: Changed 'NAME' to 'name'
        response = db.from_('signaturetable').select('*').order('name', desc=True).execute()
        return jsonify(response.data), 200
        
    except Exception as e:
        print(f"Error fetching signaturetable: {e}")
        return jsonify([]), 500

# ==============================
# 🆕 ROUTE: SAVE SIGNATURE TO SIGNATURE TABLE (For Company Signature Page ONLY) - FIXED
# ==============================
@app.route('/save_signaturetable', methods=['POST'])
def save_signature_table():
    """
    Saves signature directly to 'signaturetable'.
    Used exclusively for 'Company Signature' page.
    FIXED: Field name updated to 'name' (lowercase)
    """
    try:
        db = get_db()
        data = request.json
        
        name = data.get('name')
        signature_data = data.get('signature')
        
        if not name or not signature_data:
            return jsonify({'success': False, 'message': 'Paki-lagay ng Pangalan at Pirma'}), 400
            
        # INSERT INTO SIGNATURE TABLE
        # FIXED: Using 'name' (lowercase) to match DB
        db.from_('signaturetable').insert({
            'name': name,
            'man_signature': signature_data
        }).execute()
        
        return jsonify({'success': True, 'message': f'Saved to SignatureTable!'}), 200
        
    except Exception as e:
        print(f"Error saving to signaturetable: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==============================
# 🆕 NEW ROUTE: GET SIGNATURE BY NAME
# ==============================
@app.route('/get_signature_by_name', methods=['GET'])
def get_signature_by_name():
    """
    Fetches a specific signature based on the Name.
    Used by the 'Load (DB)' button.
    """
    try:
        db = get_db()
        name = request.args.get('name') # Kunin ang name galing sa URL
        
        if not name:
            return jsonify({'success': False, 'message': 'No name provided'}), 400
            
        # Hanapin ang record sa signaturetable na match yung name
        # Ginamit ko 'ilike' (case insensitive search) para mas user friendly
        response = db.from_('signaturetable').select('*').ilike('name', name).execute()
        
        if response.data and len(response.data) > 0:
            # Kunin ang first match
            record = response.data[0]
            # Siguraduhin na nakuha yung field na 'signature'
            sig_data = record.get('signature')
            
            if sig_data:
                return jsonify({
                    'success': True, 
                    'name': record.get('name'),
                    'signature': sig_data
                })
            else:
                return jsonify({'success': False, 'message': 'Signature data missing in DB'}), 404
        else:
            return jsonify({'success': False, 'message': 'Name not found'}), 404
            
    except Exception as e:
        print(f"Error fetching by name: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==============================
# Run App
# ==============================
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
