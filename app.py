# -----------------------------
# Imports & Environment Setup
# -----------------------------
from dotenv import load_dotenv
import os
import re # Dagdag para sa ID parsing
from supabase import create_client, Client
from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()
SUPAB_URL = os.getenv("SUPAB_URL")
SUPAB_SERVICE_KEY = os.getenv("SUPAB_SERVICE_KEY")

if not SUPAB_URL or not SUPAB_SERVICE_KEY:
    raise ValueError("SUPAB_URL and SUPAB_SERVICE_KEY must be set")

# -----------------------------
# Supabase Client
# -----------------------------
supabase: Client = create_client(SUPAB_URL, SUPAB_SERVICE_KEY)

def get_db():
    return supabase

# -----------------------------
# Flask App Initialization
# -----------------------------
app = Flask(__name__)

# -----------------------------
# Routes - Home & Navigation
# -----------------------------
@app.route('/')
def home():
    return render_template('placeholder_members.html')

@app.route('/members')
def members_redirect():
    return redirect(url_for('home'))

@app.route('/contact')
def contact():
    return "<h1>Contact Page</h1><p>This is a placeholder for contact information.</p>"

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/login')
def login():
    return "<h1>Login Page</h1><p>This is a placeholder for a login page.</p>"

# -----------------------------
# Routes - Search
# -----------------------------
@app.route("/search")
def search_form():
    return render_template("search_form.html")

@app.route('/api/members')
def api_members():
    try:
        db = get_db()
        search_term = request.args.get('q', '').strip()
        if search_term:
            query = db.from_('members').select('*').or_(
                f"name.ilike.%{search_term}%,chapter.ilike.%{search_term}%,designation.ilike.%{search_term}%,contact_no.ilike.%{search_term}%,blood_type.ilike.%{search_term}%,home_address.ilike.%{search_term}%"
            ).order('name', desc=False)
            response = query.execute()
        else:
            response = db.from_('members').select('*').order('name', desc=False).execute()
        return jsonify(response.data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# -----------------------------
# Routes - ID Generator Logic (DAGDAG)
# -----------------------------
@app.route('/save-id-base', methods=['POST'])
def save_id_base():
    try:
        db = get_db()
        data = request.json
        word_part = data.get('word', '').strip()
        num_part = data.get('number', '').strip()
        
        full_format = f"{word_part}-{num_part}"
        
        # I-save sa IdGenerate table
        db.table('IdGenerate').insert({"idNumber": full_format}).execute()
        return jsonify({"status": "success", "format": full_format})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/get-next-id')
def get_next_id():
    try:
        db = get_db()
        # 1. Check muna ang huling member sa 'members' table base sa 'idnumb'
        last_member = db.table('members').select('idnumb').order('id', desc=True).limit(1).execute()
        
        source_id = ""
        if last_member.data and last_member.data[0].get('idnumb'):
            source_id = last_member.data[0]['idnumb']
        else:
            # 2. Kung walang member, kunin sa IdGenerate table
            base_id = db.table('IdGenerate').select('idNumber').order('id', desc=True).limit(1).execute()
            if base_id.data:
                source_id = base_id.data[0]['idNumber']
        
        if not source_id:
            return jsonify({"status": "error", "message": "No base ID found"})

        # 3. Increment Logic (+1)
        match = re.match(r"([a-zA-Z]+)-(\d+)", source_id)
        if match:
            word = match.group(1)
            num_str = match.group(2)
            next_num = int(num_str) + 1
            new_id = f"{word}-{str(next_num).zfill(len(num_str))}"
            return jsonify({"status": "success", "next_id": new_id})
        
        return jsonify({"status": "error", "message": "Invalid ID format"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# -----------------------------
# Routes - Member Management
# -----------------------------
@app.route('/add_member', methods=['GET', 'POST'])
def add_member():
    if request.method == 'POST':
        form_data = {
            'idnumb': request.form.get('id_no'), # DAGDAG: Field para sa ID increment
            'name': request.form['name'],
            'designation': request.form.get('designation', ''), # Handled for safety
            'chapter': request.form.get('chapter', ''),
            'birthdate': request.form['birthdate'],
            'blood_type': request.form.get('blood_type', ''),
            'contact_no': request.form.get('contact_no', ''),
            'home_address': request.form.get('home_address', ''),
            'height': request.form.get('height'),
            'weight': request.form.get('weight'),
            'emergency_person_address': request.form.get('emergency_person_address'),
            'emergency_contact_no': request.form.get('emergency_contact_no'),
            'photo_data': request.form.get('photo_data'),
            'issued_date': datetime.now().strftime('%Y-%m-%d'),
            'valid_until': (datetime.now() + timedelta(days=365*3)).strftime('%Y-%m-%d')
        }
        try:
            db = get_db()
            db.from_('members').insert(form_data).execute()
            # Redirect back to search or home after success
            return redirect(url_for('home'))
        except Exception as e:
            return f"Error adding member: {str(e)}", 500

    return render_template('add_member_form.html')

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

@app.route('/edit_member/<int:member_id>')
def edit_member(member_id):
    return f"Edit member with ID: {member_id}"

@app.route('/delete_member/<int:member_id>')
def delete_member(member_id):
    return f"Delete member with ID: {member_id}"

# -----------------------------
# Routes - Health Check
# -----------------------------
@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

# -----------------------------
# Run the App
# -----------------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
