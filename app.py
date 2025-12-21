# --- Load environment variables safely
from dotenv import load_dotenv
import os
from supabase import create_client, Client
from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import datetime, timedelta

# Load .env file
load_dotenv()

SUPAB_URL = os.getenv("SUPAB_URL")
SUPAB_SERVICE_KEY = os.getenv("SUPAB_SERVICE_KEY")

if not SUPAB_URL or not SUPAB_SERVICE_KEY:
    raise ValueError("SUPAB_URL and SUPAB_SERVICE_KEY must be set")

# --- Supabase client
supabase: Client = create_client(SUPAB_URL, SUPAB_SERVICE_KEY)

# --- Database helper
def get_db():
    return supabase

# --- Flask app
app = Flask(__name__)

# --- Routes ---
@app.route('/')
def home():
    return render_template('placeholder_members.html')

@app.route('/members')
def members_redirect():
    return redirect(url_for('home'))

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
            members = response.data
        else:
            response = db.from_('members').select('*').order('name', desc=False).execute()
            members = response.data
        return jsonify(members)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/search_members', methods=['GET', 'POST'])
def search_members():
    search_term = request.form.get('search_term', '').strip() if request.method == 'POST' else request.args.get('search_term', '').strip()
    search_type = request.form.get('search_type', 'all') if request.method == 'POST' else request.args.get('search_type', 'all')
    
    if not search_term:
        return redirect(url_for('search_form'))
    try:
        db = get_db()
        query = db.from_('members').select('*')
        if search_type == 'name':
            query = query.ilike('name', f'%{search_term}%')
        elif search_type == 'chapter':
            query = query.ilike('chapter', f'%{search_term}%')
        elif search_type == 'designation':
            query = query.ilike('designation', f'%{search_term}%')
        elif search_type == 'contact':
            query = query.ilike('contact_no', f'%{search_term}%')
        else:
            query = query.or_(
                f"name.ilike.%{search_term}%,chapter.ilike.%{search_term}%,designation.ilike.%{search_term}%,contact_no.ilike.%{search_term}%,blood_type.ilike.%{search_term}%,home_address.ilike.%{search_term}%"
            )
        response = query.order('name', desc=False).execute()
        members = response.data
        return render_template('search_results.html', 
                               members=members, 
                               search_term=search_term,
                               search_type=search_type,
                               total_results=len(members))
    except Exception as e:
        return f"Search error: {str(e)}", 500

@app.route('/add_member', methods=['GET', 'POST'])
def add_member():
    if request.method == 'POST':
        form_data = {
            'name': request.form['name'],
            'designation': request.form['designation'],
            'chapter': request.form['chapter'],
            'birthdate': request.form['birthdate'],
            'blood_type': request.form['blood_type'],
            'contact_no': request.form['contact_no'],
            'home_address': request.form['home_address'],
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
            return redirect(url_for('list_members'))
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

@app.route('/contact')
def contact():
    return "<h1>Contact Page</h1><p>This is a placeholder for contact information.</p>"

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/login')
def login():
    return "<h1>Login Page</h1><p>This is a placeholder for a login page.</p>"

@app.route('/edit_member/<int:member_id>')
def edit_member(member_id):
    return f"Edit member with ID: {member_id}"

@app.route('/delete_member/<int:member_id>')
def delete_member(member_id):
    return f"Delete member with ID: {member_id}"

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

# --- Run the app
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
