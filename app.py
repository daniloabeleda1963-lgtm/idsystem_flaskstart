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
    raise ValueError("SUPAB_URL and SUPAB_SERVICE_KEY must be set")

# ==============================
# Flask App Initialization
# ==============================
app = Flask(__name__)

# ==============================
# Supabase Client
# ==============================
supabase: Client = create_client(SUPAB_URL, SUPAB_SERVICE_KEY)

def get_db():
    return supabase

# ================================
# VB6 STYLE REPLACE (SEARCH CLEAN)
# ================================
def vb6_replace(text):
    if not text:
        return ""
    return (
        text.strip()
            .replace("'", "")
            .replace('"', "")
            .replace(";", "")
            .replace("--", "")
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
    return "<h1>Contact Page</h1>"

@app.route('/login')
def login():
    return "<h1>Login Page</h1>"

# ==============================
# Routes - Search Form (HTML)
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
    Ito ay nag-handle kapag nag-submit yung user ng form (Non-JS fallback).
    Pero ngayon, pinapasa natin yung data sa template gamit ang tamang variable name.
    """
    try:
        db = get_db()
        raw_search = request.form.get("search_term")
        search_type = request.form.get("search_type") or "all"
        search_term = vb6_replace(raw_search).lower()

        if search_term:
            # Single-line OR logic compatible sa Supabase
            if search_type == "all":
                or_logic = ",".join([
                    f"name.ilike.%{search_term}%",
                    f"chapter.ilike.%{search_term}%",
                    f"designation.ilike.%{search_term}%",
                    f"contact_no.ilike.%{search_term}%",
                    f"blood_type.ilike.%{search_term}%",
                    f"home_address.ilike.%{search_term}%"
                ])
            elif search_type == "name":
                or_logic = f"name.ilike.%{search_term}%"
            elif search_type == "chapter":
                or_logic = f"chapter.ilike.%{search_term}%"
            elif search_type == "designation":
                or_logic = f"designation.ilike.%{search_term}%"
            elif search_type == "contact":
                or_logic = f"contact_no.ilike.%{search_term}%"
            else:
                or_logic = f"name.ilike.%{search_term}%"

            response = db.from_('members').select('*').or_(or_logic).order('name', desc=False).execute()
        else:
            response = db.from_('members').select('*').order('name', desc=False).execute()

        members = response.data if response.data else []

        # Highlight sa backend (For Server-Side Result Page)
        def highlight(text):
            if not text: return ""
            regex = re.compile(re.escape(search_term), re.IGNORECASE)
            return regex.sub(lambda m: f'<span class="highlight">{m.group(0)}</span>', text)

        for m in members:
            m['name'] = highlight(m.get('name', ''))
            m['chapter'] = highlight(m.get('chapter', ''))
            m['designation'] = highlight(m.get('designation', ''))
            m['contact_no'] = highlight(m.get('contact_no', ''))
            m['blood_type'] = highlight(m.get('blood_type', ''))
            m['home_address'] = highlight(m.get('home_address', ''))

        # FIX: Binago ko 'results_count' to 'total_results' para tugma sa Code 4
        return render_template(
            "search_results.html",
            members=members,
            search_term=search_term,
            search_type=search_type,
            total_results=len(members)
        )

    except Exception as e:
        return f"Error loading members: {str(e)}", 500

# ==============================
# ROUTE: API Members (JSON Only) - Get All
# ==============================
@app.route('/api/members/json', methods=["GET"])
def api_members_json():
    """
    NEW ROUTE: Ito ay purely JSON API para kay Code #3 (Real-time Search).
    Hindi nag-rerender ng HTML. Ibalik lang ang raw data list.
    """
    try:
        db = get_db()
        response = db.from_('members').select('*').order('name', desc=False).execute()
        return jsonify(response.data)
    except Exception as e:
        print(f"Error fetching JSON members: {e}")
        return jsonify([]), 500

# ==============================
# NEW ROUTE: LIVE AUTOCOMPLETE SEARCH (Direct from Supabase)
# ==============================
@app.route('/api/members/search', methods=["GET"])
def api_members_search():
    """
    Ito ay nagha-handle ng live search habang nagta-type sa Add Member Form.
    Hinahanap sa Supabase (Name OR Chapter).
    Limit to 20 results for performance.
    """
    try:
        db = get_db()
        q = request.args.get('q', '')
        
        # Kung empty, return empty array
        if not q:
            return jsonify([])
            
        # Logic: Search Name OR Chapter using Supabase syntax
        or_logic = f"name.ilike.%{q}%,chapter.ilike.%{q}%"
        response = db.from_('members').select('*').or_(or_logic).limit(20).execute()
        
        return jsonify(response.data)
    except Exception as e:
        print(f"Error searching autocomplete: {e}")
        return jsonify([]), 500

# ==============================
# Routes - ID Generator Logic
# ==============================

@app.route('/get_current_id')
def get_current_id():
    """Fetches the latest ID format from 'idgenerate' table."""
    try:
        db = get_db()
        response = db.table('idgenerate').select('*').order('id', desc=True).limit(1).execute()
        if response.data:
            return jsonify({'idnumber': response.data[0].get('idnumber')})
        else:
            return jsonify({'idnumber': ''})
    except Exception as e:
        print(f"Error getting current ID: {e}")
        return jsonify({'idnumber': ''})

@app.route('/save_id_to_db', methods=['POST'])
def save_id_to_db():
    """Saves or Updates the ID format."""
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
        print(f"Error saving/updating ID: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/add_member', methods=['GET', 'POST'])
def add_member():
    """
    Add Member Route - Includes Camera Action (Base64 Photo)
    """
    if request.method == 'POST':
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
            # Camera Action: Base64 string from HTML canvas
            'photo_data': request.form.get('photo_data'), 
            # ADDED: QR Code and Signature fields
            'qr_code': request.form.get('qr_code'),
            'signature': request.form.get('signature'),
            # Dates
            'issued_date': datetime.now().strftime('%Y-%m-%d'),
            'valid_until': (datetime.now() + timedelta(days=365*3)).strftime('%Y-%m-%d')
        }

        try:
            db = get_db()
            db.from_('members').insert(form_data).execute()
            return redirect(url_for('home'))
        except Exception as e:
            return f"Error adding member: {str(e)}", 500

    return render_template('add_member_form.html')

# ==============================
# Display ID
# ==============================
@app.route('/display_id/<int:member_id>')
def display_id(member_id):
    try:
        db = get_db()
        response = db.from_('members').select('*').eq('id', member_id).execute()
        if not response.data:
            return "Member not found", 404
        member = response.data[0]
        return render_template('id_template.html', id_info=member)
    except Exception as e:
        return f"Database error: {str(e)}", 500

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
