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
# NEW ROUTE: ADMIN MENU (Password Protected)
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
            error = "Incorrect password! Try 'admin123'"

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
                <input type="password" name="password" placeholder="Enter Password" required autofocus>
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
# Routes - Search Form (HTML Fallback)
# ==============================
@app.route("/search")
def search_form():
    return render_template("search_form.html")

# ==============================
# Bridge Route para sa HTML form action
# ==============================
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
            # Render template w/o highlights if empty
            return render_template("search_results.html", members=members, total_results=len(members))

        # Construct Supabase OR Logic
        or_logic = ""
        
        if search_type == "all":
            # --- FIX: NADAGDAG NA ANG PSEUDO NAME ---
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
            # Search both real name and pseudo name
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
# API: Get All Members (JSON)
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

# ==============================
# API: Live Autocomplete Search
# ==============================
@app.route('/api/members/search', methods=["GET"])
def api_members_search():
    """
    Live search endpoint (Name OR Pseudo Name OR Chapter).
    Used by Add Member Form 'check existing' logic.
    """
    try:
        db = get_db()
        q = request.args.get('q', '').strip()
        
        if not q:
            return jsonify([])
            
        # --- FIX: NADAGDAG NA ANG PSEUDO NAME ---
        or_logic = f"name.ilike.%{q}%,pseudo_name.ilike.%{q}%,chapter.ilike.%{q}%"
        # ------------------------------------------------
        response = db.from_('members').select('*').or_(or_logic).limit(20).execute()
        
        return jsonify(response.data)
    except Exception as e:
        print(f"Autocomplete Error: {e}")
        return jsonify([]), 500

# ==============================
# API: Filter by Date (For Print/Mobile)
# ==============================
@app.route('/api/members/by-date', methods=["GET"])
def api_members_by_date():
    """Filter members by date_of_membership."""
    try:
        db = get_db()
        selected_date = request.args.get('date')
        
        if not selected_date:
            return jsonify([]), 400

        response = db.from_('members') \
                    .select('*') \
                    .eq('date_of_membership', selected_date) \
                    .order('name', desc=False) \
                    .execute()

        return jsonify(response.data)

    except Exception as e:
        print(f"Filter Date Error: {e}")
        return jsonify([]), 500

# ==============================
# ID Generator Logic (Settings)
# ==============================

@app.route('/get_current_id')
def get_current_id():
    """Fetches latest ID format."""
    try:
        db = get_db()
        response = db.table('idgenerate').select('*').order('id', desc=True).limit(1).execute()
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

        check_response = db.table('idgenerate').select('id').order('id', desc=True).limit(1).execute()
        
        if check_response.data:
            record_id = check_response.data[0].get('id')
            db.table('idgenerate').update({"idnumber": id_value}).eq('id', record_id).execute()
            action_type = "Updated"
        else:
            db.table('idgenerate').insert({"idnumber": id_value}).execute()
            action_type = "Saved"

        return jsonify({'success': True, 'message': f'ID {action_type} successfully!', 'id': id_value})
    except Exception as e:
        print(f"Error saving ID: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==============================
# ADD / UPDATE MEMBER LOGIC
# ==============================
@app.route('/add_member', methods=['GET', 'POST'])
def add_member():
    """
    Handles creating new members AND updating existing ones.
    Includes Camera Action (Base64) and Pseudo Name.
    """
    if request.method == 'POST':
        try:
            db = get_db()
            
            # Determine Action: Add or Update?
            form_action = request.form.get('form_action') 
            record_id = request.form.get('member_id')
            
            # Collect Data
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
                # Camera: Base64 String
                'photo_data': request.form.get('photo_data'), 
                # ID Extras
                'qr_code': request.form.get('qr_code'),
                'signature': request.form.get('signature'),
                # --- FIX: PSEUDO NAME ---
                'pseudo_name': request.form.get('pseudo_name'),
                # -----------------------
                
                # Auto Dates
                'issued_date': datetime.now().strftime('%Y-%m-%d'),
                'valid_until': (datetime.now() + timedelta(days=365*3)).strftime('%Y-%m-%d')
            }

            # --- SMART UPDATE LOGIC ---
            if form_action == 'update' and record_id:
                # If updating, check if photo_data is provided.
                # If user didn't take a new photo, photo_data might be empty string.
                # If it is empty, do NOT update the photo field (keep old one).
                # NOTE: This logic assumes photo_data comes as empty string if not retaken.
                # If your JS sends the OLD base64, this check isn't needed.
                # If your JS sends "", then we need to remove 'photo_data' from form_data.
                
                new_photo = request.form.get('photo_data')
                if not new_photo or new_photo == "data:,": 
                    # Remove photo key from update dict to preserve existing photo in DB
                    form_data.pop('photo_data', None)

                # Execute Update
                db.from_('members').update(form_data).eq('id', record_id).execute()
                print(f"Updated Member ID: {record_id}")
            else:
                # Insert New
                db.from_('members').insert(form_data).execute()
                print("Added New Member")
            
            return redirect(url_for('home'))

        except Exception as e:
            print(f"Add/Update Error: {e}")
            return f"Error processing member: {str(e)}", 500

    return render_template('add_member_form.html')

# ==============================
# ID PDF Generator Redirect
# ==============================
@app.route('/display_id/<int:member_id>')
def display_id(member_id):
    # Redirects to the master PDF generator page
    return redirect(url_for('id_pdf_generator'))

@app.route('/id_pdf_generator')
def id_pdf_generator():
    """Render the ID Card Generator Layout Page."""
    return render_template('id_pdf_generator.html')

# ==============================
# DELETE MEMBER
# ==============================
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
# Health Check
# ==============================
@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

# ==============================
# Run App
# ==============================
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
