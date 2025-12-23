# -----------------------------
# Imports & Environment Setup
# -----------------------------
import os
import re
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, jsonify
from dotenv import load_dotenv
from supabase import create_client, Client

# -----------------------------
# Load Environment Variables
# -----------------------------
load_dotenv()
SUPAB_URL = os.getenv("SUPAB_URL")
SUPAB_SERVICE_KEY = os.getenv("SUPAB_SERVICE_KEY")

if not SUPAB_URL or not SUPAB_SERVICE_KEY:
    raise ValueError("SUPAB_URL and SUPAB_SERVICE_KEY must be set")

# -----------------------------
# Flask App Initialization
# -----------------------------
app = Flask(__name__)

# -----------------------------
# Supabase Client
# -----------------------------
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

# -----------------------------
# Routes - Home & Navigation
# -----------------------------
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

# -----------------------------
# Routes - Search Form (HTML)
# -----------------------------
@app.route("/search")
def search_form():
    return render_template("search_form.html")

# -----------------------------
# Bridge Route para sa HTML form action
# -----------------------------
@app.route("/search-members", methods=["POST"])
def search_members():
    """
    Temporary bridge para gumana ang:
    action="{{ url_for('search_members') }}" sa HTML
    """
    return api_members()

# -----------------------------
# Routes - API Members (Search Logic)
# -----------------------------
@app.route('/api/members', methods=["GET", "POST"])
def api_members():
    try:
        db = get_db()
        raw_search = request.form.get("search_term") or request.args.get("q", "")
        search_type = request.form.get("search_type") or request.args.get("search_type") or "all"
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
                or_logic = f"name.ilike.%{search_term}%"  # default fallback

            response = db.from_('members').select('*').or_(or_logic).order('name', desc=False).execute()
        else:
            response = db.from_('members').select('*').order('name', desc=False).execute()

        members = response.data if response.data else []

        # Highlight sa backend
        def highlight(text):
            if not text: return ""
            regex = re.compile(re.escape(search_term), re.IGNORECASE)
            return regex.sub(lambda m: f'<span class="highlight">{m.group(0)}</span>', text)

        # I-highlight lahat ng fields
        for m in members:
            m['name'] = highlight(m.get('name', ''))
            m['chapter'] = highlight(m.get('chapter', ''))
            m['designation'] = highlight(m.get('designation', ''))
            m['contact_no'] = highlight(m.get('contact_no', ''))
            m['blood_type'] = highlight(m.get('blood_type', ''))
            m['home_address'] = highlight(m.get('home_address', ''))

        return render_template(
            "search_results.html",
            members=members,
            search_term=search_term,
            search_type=search_type,
            results_count=len(members)
        )

    except Exception as e:
        return f"Error loading members: {str(e)}", 500

# -----------------------------
# Routes - ID Generator
# -----------------------------
@app.route('/save-id-base', methods=['POST'])
def save_id_base():
    try:
        db = get_db()
        data = request.json

        word_part = data.get('word', '').strip()
        num_part = data.get('number', '').strip()
        full_format = f"{word_part}-{num_part}"

        db.table('IdGenerate').insert({"idNumber": full_format}).execute()

        return jsonify({"status": "success", "format": full_format})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/get-next-id')
def get_next_id():
    try:
        db = get_db()

        last_member = db.table('members') \
            .select('idnumb') \
            .order('id', desc=True) \
            .limit(1).execute()

        source_id = ""
        if last_member.data and last_member.data[0].get('idnumb'):
            source_id = last_member.data[0]['idnumb']
        else:
            base_id = db.table('IdGenerate') \
                .select('idNumber') \
                .order('id', desc=True) \
                .limit(1).execute()
            if base_id.data:
                source_id = base_id.data[0]['idNumber']

        if not source_id:
            return jsonify({"status": "error", "message": "No base ID found"})

        match = re.match(r"([a-zA-Z]+)-(\d+)", source_id)
        if match:
            word, num_str = match.groups()
            next_num = int(num_str) + 1
            new_id = f"{word}-{str(next_num).zfill(len(num_str))}"
            return jsonify({"status": "success", "next_id": new_id})

        return jsonify({"status": "error", "message": "Invalid ID format"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# -----------------------------
# Routes - Add Member
# -----------------------------
@app.route('/add_member', methods=['GET', 'POST'])
def add_member():
    if request.method == 'POST':
        form_data = {
            'idnumb': request.form.get('id_no'),
            'name': request.form.get('name'),
            'designation': request.form.get('designation', ''),
            'chapter': request.form.get('chapter', ''),
            'birthdate': request.form.get('birthdate'),
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
            return redirect(url_for('home'))
        except Exception as e:
            return f"Error adding member: {str(e)}", 500

    return render_template('add_member_form.html')

# -----------------------------
# Display ID
# -----------------------------
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

# -----------------------------
# Health Check
# -----------------------------
@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

# -----------------------------
# Run App
# -----------------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
