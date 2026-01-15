# ==============================
# Imports & Environment Setup
# ==============================
import os
import re
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify
from dotenv import load_dotenv
from supabase import create_client, Client

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
# 🆕 AUTO CLEANUP SCANNER (13H INTERVAL)
# ==============================
@app.before_request
def cleanup_old_cards_scanner():
    """
    Automatic Scanner.
    1. Check if 13 hours passed since last cleanup.
    2. If Yes: Delete cards older than 24 hours.
    3. If No: Skip.
    """
    # Huwag scan sa static files (css, js) para mabilis
    if request.path.startswith('/static'):
        return

    try:
        db = get_db()

        # 1. KUNIN ANG LAST CLEANUP TIME SA 'idgenerate' TABLE
        response = db.from_('idgenerate').select('last_card_cleanup').limit(1).execute()
        
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
            # Fresh pa ang scan, huwag gumulo sa system.
            return 

        print(f">>> SCANNING OLD CARDS... Last scan was {time_since_last_cleanup} ago.")

        # 4. DELETE LOGIC: DELETE ANG > 24 HOURS
        # Yung '2 hours pa lang' ay hindi dito mapupunta.
        expiry_time = now - timedelta(hours=24)

        delete_response = db.from_('members').update({
            'generated_card_image': None,
            'generated_at': None
        }).lt('generated_at', expiry_time.isoformat()).execute()
        
        print(f">>> CLEANED UP CARDS OLDER THAN: {expiry_time}")

        # 5. UPDATE LAST CLEANUP TIME (Reset Clock ng Scanner)
        db.from_('idgenerate').update({
            'last_card_cleanup': now.isoformat()
        }).is_not('idnumber', None).execute()

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
# LAYOUT EDITOR LOGIC
# ==============================
@app.route('/save_layout', methods=['POST'])
def save_layout():
    try:
        payload = request.json
        db = get_db()
        # FIXED: db.table to db.from_
        response = db.from_('layouts').select("*").limit(1).execute()
        existing_data = response.data
        
        if existing_data and len(existing_data) > 0:
            record_id = existing_data[0]['id']
            # FIXED: db.table to db.from_
            db.from_('layouts').update({"config_json": payload}).eq('id', record_id).execute()
            print(f"Updated Layout ID: {record_id}")
        else:
            # FIXED: db.table to db.from_
            db.from_('layouts').insert({"config_json": payload}).execute()
            print("Inserted New Layout")

        return jsonify({"status": "success", "message": "Layout saved successfully!"}), 200

    except Exception as e:
        print(f"Error saving layout: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/load_layout', methods=['GET'])
def load_layout():
    try:
        db = get_db()
        # FIXED: db.table to db.from_
        response = db.from_('layouts').select("*").order('updated_at', desc=True).limit(1).execute()
        data = response.data
        if not data:
            return jsonify({"status": "error", "message": "No saved layout found."}), 404
        return jsonify({"status": "success", "data": data[0]['config_json']}), 200

    except Exception as e:
        print(f"Error loading layout: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==============================
# ADMIN FORMS ROUTES (ACTIVE - Connected to Supabase)
# ==============================

@app.route('/get_admin_forms', methods=['GET'])
def get_admin_forms():
    """Fetches all forms from admin_forms table."""
    try:
        db = get_db()
        # FIXED: db.table to db.from_
        response = db.from_('admin_forms').select("*").order('created_at', desc=True).execute()
        
        if response.data:
            return jsonify(response.data), 200
        
        # Fallback kung walang laman
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

        # FIXED: db.table to db.from_
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
        # FIXED: db.table to db.from_
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
        # FIXED: db.table to db.from_ (To prevent future errors)
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
        designation = data.get('designation')  # ADDED: Designation field
        man_signature = data.get('man_signature') 
        text_signature = data.get('text_signature', '') 

        if not name_officer or not man_signature:
            return jsonify({'success': False, 'message': 'Name and Signature are required'}), 400

        payload = {
            'name_officer': name_officer,
            'designation': designation,  # ADDED: Designation field
            'man_signature': man_signature,
            'text_signature': text_signature
        }

        # FIXED: db.table to db.from_
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
        # FIXED: db.table to db.from_
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
        designation = data.get('designation')  # ADDED: Designation field
        man_signature = data.get('man_signature')
        text_signature = data.get('text_signature', '')

        if not name_officer or not man_signature:
            return jsonify({'success': False, 'message': 'Name and Signature are required'}), 400

        payload = {
            'name_officer': name_officer,
            'designation': designation,  # ADDED: Designation field
            'man_signature': man_signature,
            'text_signature': text_signature
        }

        # FIXED: db.table to db.from_
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
        # FIXED: db.table to db.from_
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
    """Fetches latest ID format."""
    try:
        db = get_db()
        # FIXED: db.table to db.from_ (Making consistent)
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

        # FIXED: db.table to db.from_
        check_response = db.from_('idgenerate').select('id').order('id', desc=True).limit(1).execute()
        if check_response.data:
            record_id = check_response.data[0].get('id')
            # FIXED: db.table to db.from_
            db.from_('idgenerate').update({"idnumber": id_value}).eq('id', record_id).execute()
        else:
            # FIXED: db.table to db.from_
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
    return render_template('view_phone.html')

# ==============================
# NEW: SAVE CARD IMAGE ROUTE (FOR TIME BOMB FEATURE)
# ==============================
@app.route('/save_card_image', methods=['POST'])
def save_card_image():
    """
    I-save yung generated ID card image sa member.
    Siya ang magtatakbo pagkatapos mag-merge sa Laptop.
    """
    try:
        db = get_db()
        data = request.json
        member_id = data.get('member_id')
        image_data = data.get('image_data') # Base64 string

        if not member_id or not image_data:
            return jsonify({'success': False, 'message': 'Missing data'}), 400

        payload = {
            'generated_card_image': image_data,
            'generated_at': datetime.now().isoformat() # Save timestamp NOW
        }

        db.from_('members').update(payload).eq('id', member_id).execute()

        return jsonify({'success': True, 'message': 'ID Card saved to database.'})
    except Exception as e:
        print(f"Save Card Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==============================
# Run App
# ==============================
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
