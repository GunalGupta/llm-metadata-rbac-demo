import os
import json
import re
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import sqlparse
from sqlparse.sql import IdentifierList, Identifier
from sqlparse.tokens import Keyword, DML

app = Flask(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY', 'your-api-key-here'))

# Mock data catalog - simulating AWS Data Catalog
MOCK_CATALOG = {
    'users': {
        'fields': [
            {'name': 'id', 'type': 'int', 'sensitivity': 'public'},
            {'name': 'name', 'type': 'string', 'sensitivity': 'public'},
            {'name': 'email', 'type': 'string', 'sensitivity': 'PII'},
            {'name': 'salary', 'type': 'float', 'sensitivity': 'confidential'}
        ]
    },
    'orders': {
        'fields': [
            {'name': 'order_id', 'type': 'int', 'sensitivity': 'public'},
            {'name': 'user_id', 'type': 'int', 'sensitivity': 'public'},
            {'name': 'amount', 'type': 'float', 'sensitivity': 'public'},
            {'name': 'order_date', 'type': 'date', 'sensitivity': 'public'}
        ]
    }
}

# Role definitions for RBAC
ROLE_PERMISSIONS = {
    'basic': ['public'],
    'admin': ['public', 'PII', 'confidential']
}

# Global log for demonstration
query_log = []

def filter_fields_by_role(fields, role):
    """Filter table fields based on user role permissions"""
    allowed_sensitivities = ROLE_PERMISSIONS.get(role, [])
    filtered_fields = []
    
    for field in fields:
        if field['sensitivity'] in allowed_sensitivities:
            filtered_fields.append(field)
    
    return filtered_fields

def extract_fields_from_query(sql_query):
    """Extract field names from SQL query using sqlparse"""
    try:
        parsed = sqlparse.parse(sql_query)[0]
        fields = set()
        
        # Simple field extraction - look for identifiers
        for token in parsed.flatten():
            if token.ttype is None and not token.is_keyword:
                # Clean up the token (remove quotes, whitespace, etc.)
                field_name = str(token).strip().strip('"').strip("'").lower()
                if field_name and not field_name in ['select', 'from', 'where', 'and', 'or', 'avg', 'count', 'sum', 'max', 'min']:
                    # Skip table names and common SQL keywords
                    if '.' not in field_name and field_name not in ['users', 'orders']:
                        fields.add(field_name)
        
        return list(fields)
    except:
        # Fallback to regex if sqlparse fails
        return extract_fields_regex(sql_query)

def extract_fields_regex(sql_query):
    """Fallback method to extract fields using regex"""
    # Simple regex to find potential field names
    fields = set()
    
    # Look for SELECT ... FROM pattern
    select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql_query, re.IGNORECASE | re.DOTALL)
    if select_match:
        select_part = select_match.group(1)
        
        # Split by comma and clean up
        potential_fields = [f.strip() for f in select_part.split(',')]
        
        for field in potential_fields:
            # Remove functions and aliases
            field = re.sub(r'(AVG|COUNT|SUM|MAX|MIN)\s*\(\s*([^)]+)\s*\)', r'\2', field, flags=re.IGNORECASE)
            field = re.sub(r'\s+as\s+\w+', '', field, flags=re.IGNORECASE)
            field = field.strip().lower()
            
            if field and field != '*' and not field.isdigit():
                fields.add(field)
    
    return list(fields)

def validate_query_fields(query_fields, allowed_fields):
    """Check if all query fields are in the allowed fields list"""
    allowed_field_names = [f['name'].lower() for f in allowed_fields]
    unauthorized_fields = []
    
    for field in query_fields:
        if field.lower() not in allowed_field_names:
            unauthorized_fields.append(field)
    
    return len(unauthorized_fields) == 0, unauthorized_fields

def generate_llm_prompt(table_name, filtered_fields, user_query):
    """Generate prompt for the LLM"""
    fields_description = "\n".join([f"- {field['name']}: {field['type']}" for field in filtered_fields])
    
    prompt = f"""You are a helpful assistant that generates SQL queries based on natural language questions.
Given the following table schema, generate a SQL query to answer the user's question.
You must use only the provided fields. If the question requires fields not listed, respond with "Cannot generate query: required fields are not accessible."

Table: {table_name}
Fields:
{fields_description}

User question: {user_query}
Generate the SQL query or the rejection message:"""
    
    return prompt

@app.route('/')
def index():
    """Main page with the demo interface"""
    return render_template('index.html')

@app.route('/metadata/<table_name>')
def get_metadata(table_name):
    """Mock AWS Data Catalog API endpoint"""
    if table_name in MOCK_CATALOG:
        return jsonify(MOCK_CATALOG[table_name])
    else:
        return jsonify({'error': 'Table not found'}), 404

@app.route('/process_query', methods=['POST'])
def process_query():
    """Process the natural language query with RBAC"""
    try:
        data = request.json
        role = data.get('role')
        table_name = data.get('table')
        user_query = data.get('query')
        
        # Get table metadata
        if table_name not in MOCK_CATALOG:
            return jsonify({'error': 'Table not found'}), 404
        
        table_metadata = MOCK_CATALOG[table_name]
        all_fields = table_metadata['fields']
        
        # Filter fields based on role
        filtered_fields = filter_fields_by_role(all_fields, role)
        
        if not filtered_fields:
            return jsonify({
                'role': role,
                'table': table_name,
                'accessible_fields': [],
                'llm_response': 'No accessible fields for this role',
                'decision': 'rejected',
                'reason': 'No fields accessible for this role'
            })
        
        # Generate LLM prompt
        prompt = generate_llm_prompt(table_name, filtered_fields, user_query)
        
        # Call OpenAI API
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a SQL query generator. Follow the instructions exactly."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.1
            )
            
            llm_response = response.choices[0].message.content.strip()
            
        except Exception as e:
            llm_response = f"Error calling LLM: {str(e)}"
        
        # Validate the response
        decision = 'accepted'
        reason = 'Query generated successfully'
        unauthorized_fields = []
        
        if "Cannot generate query" in llm_response:
            decision = 'rejected'
            reason = 'LLM rejected due to inaccessible fields'
        elif llm_response.upper().startswith('SELECT'):
            # Extract fields from the generated query
            query_fields = extract_fields_from_query(llm_response)
            is_valid, unauthorized_fields = validate_query_fields(query_fields, filtered_fields)
            
            if not is_valid:
                decision = 'rejected'
                reason = f'Query contains unauthorized fields: {", ".join(unauthorized_fields)}'
        
        # Log the interaction
        log_entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'role': role,
            'table': table_name,
            'user_query': user_query,
            'llm_response': llm_response,
            'decision': decision,
            'reason': reason
        }
        query_log.append(log_entry)
        
        # Prepare response
        accessible_fields_info = [f"{field['name']} ({field['type']})" for field in filtered_fields]
        
        return jsonify({
            'role': role,
            'table': table_name,
            'accessible_fields': accessible_fields_info,
            'llm_response': llm_response,
            'decision': decision,
            'reason': reason,
            'unauthorized_fields': unauthorized_fields,
            'log_entry': log_entry
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_log')
def get_log():
    """Get the current query log"""
    return jsonify({'log': query_log})

@app.route('/clear_log', methods=['POST'])
def clear_log():
    """Clear the query log"""
    global query_log
    query_log = []
    return jsonify({'message': 'Log cleared'})

# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Secure RBAC Query Generation PoC</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        h1 {
            color: #333;
            text-align: center;
            border-bottom: 3px solid #007bff;
            padding-bottom: 10px;
        }
        h2 {
            color: #007bff;
            margin-top: 30px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
            color: #333;
        }
        select, input, textarea {
            width: 100%;
            padding: 10px;
            border: 2px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
        }
        select:focus, input:focus, textarea:focus {
            border-color: #007bff;
            outline: none;
        }
        textarea {
            height: 80px;
            resize: vertical;
        }
        button {
            background: #007bff;
            color: white;
            padding: 12px 30px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            margin-right: 10px;
        }
        button:hover {
            background: #0056b3;
        }
        .secondary-btn {
            background: #6c757d;
        }
        .secondary-btn:hover {
            background: #545b62;
        }
        .result-section {
            margin-top: 30px;
            padding: 20px;
            border: 2px solid #e9ecef;
            border-radius: 5px;
            background: #f8f9fa;
        }
        .accepted {
            border-color: #28a745;
            background: #d4edda;
        }
        .rejected {
            border-color: #dc3545;
            background: #f8d7da;
        }
        .field-list {
            background: #e7f3ff;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
        }
        .sql-query {
            background: #f1f3f4;
            padding: 15px;
            border-radius: 5px;
            font-family: 'Courier New', monospace;
            margin: 10px 0;
            border-left: 4px solid #007bff;
        }
        .log-section {
            max-height: 400px;
            overflow-y: auto;
            border: 1px solid #ddd;
            padding: 15px;
            background: white;
            border-radius: 5px;
        }
        .log-entry {
            border-bottom: 1px solid #eee;
            padding: 10px 0;
            margin-bottom: 10px;
        }
        .log-entry:last-child {
            border-bottom: none;
        }
        .timestamp {
            color: #6c757d;
            font-size: 12px;
        }
        .status-accepted {
            color: #28a745;
            font-weight: bold;
        }
        .status-rejected {
            color: #dc3545;
            font-weight: bold;
        }
        .demo-scenarios {
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 5px;
            padding: 15px;
            margin: 20px 0;
        }
        .scenario {
            background: white;
            margin: 10px 0;
            padding: 10px;
            border-radius: 5px;
            border-left: 4px solid #007bff;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔐 Secure RBAC Query Generation PoC</h1>
        <p><strong>Demonstration:</strong> Metadata-driven query generation with role-based access control using LLM integration and mock AWS Data Catalog.</p>
        
        <div class="demo-scenarios">
            <h3>🎯 Demo Scenarios to Try:</h3>
            <div class="scenario">
                <strong>Scenario 1:</strong> Role: basic, Table: users, Query: "List all user names" → Should be accepted
            </div>
            <div class="scenario">
                <strong>Scenario 2:</strong> Role: basic, Table: users, Query: "What is the average salary?" → Should be rejected
            </div>
            <div class="scenario">
                <strong>Scenario 3:</strong> Role: admin, Table: users, Query: "What is the average salary?" → Should be accepted
            </div>
            <div class="scenario">
                <strong>Scenario 4:</strong> Role: basic, Table: users, Query: "List user emails" → Should be rejected
            </div>
        </div>

        <form id="queryForm">
            <div class="form-group">
                <label for="role">Select Role:</label>
                <select id="role" name="role" required>
                    <option value="">-- Select Role --</option>
                    <option value="basic">Basic User (Public fields only)</option>
                    <option value="admin">Admin (All fields)</option>
                </select>
            </div>

            <div class="form-group">
                <label for="table">Select Table:</label>
                <select id="table" name="table" required>
                    <option value="">-- Select Table --</option>
                    <option value="users">Users Table</option>
                    <option value="orders">Orders Table</option>
                </select>
            </div>

            <div class="form-group">
                <label for="query">Natural Language Query:</label>
                <textarea id="query" name="query" placeholder="e.g., List all user names, What is the average salary?, Show user emails" required></textarea>
            </div>

            <button type="submit">🚀 Generate Query</button>
            <button type="button" class="secondary-btn" onclick="clearLog()">🗑️ Clear Log</button>
        </form>

        <div id="results"></div>
    </div>

    <div class="container">
        <h2>📊 Real-time Interaction Log</h2>
        <div id="logSection" class="log-section">
            <p>No interactions yet. Submit a query to see the log.</p>
        </div>
    </div>

    <script>
        document.getElementById('queryForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const formData = {
                role: document.getElementById('role').value,
                table: document.getElementById('table').value,
                query: document.getElementById('query').value
            };

            try {
                const response = await fetch('/process_query', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(formData)
                });

                const result = await response.json();
                displayResults(result);
                updateLog();
            } catch (error) {
                console.error('Error:', error);
                document.getElementById('results').innerHTML = `
                    <div class="result-section rejected">
                        <h3>❌ Error</h3>
                        <p>Failed to process query: ${error.message}</p>
                    </div>
                `;
            }
        });

        function displayResults(result) {
            const resultsDiv = document.getElementById('results');
            const statusClass = result.decision === 'accepted' ? 'accepted' : 'rejected';
            const statusIcon = result.decision === 'accepted' ? '✅' : '❌';
            
            resultsDiv.innerHTML = `
                <div class="result-section ${statusClass}">
                    <h3>${statusIcon} Query Processing Result</h3>
                    
                    <div class="field-list">
                        <strong>Role:</strong> ${result.role}<br>
                        <strong>Table:</strong> ${result.table}<br>
                        <strong>Accessible Fields:</strong> ${result.accessible_fields.join(', ') || 'None'}
                    </div>

                    <div class="sql-query">
                        <strong>LLM Response:</strong><br>
                        ${result.llm_response}
                    </div>

                    <p><strong>Decision:</strong> <span class="status-${result.decision}">${result.decision.toUpperCase()}</span></p>
                    <p><strong>Reason:</strong> ${result.reason}</p>
                    
                    ${result.unauthorized_fields && result.unauthorized_fields.length > 0 ? 
                        `<p><strong>Unauthorized Fields Detected:</strong> ${result.unauthorized_fields.join(', ')}</p>` : ''}
                </div>
            `;
        }

        async function updateLog() {
            try {
                const response = await fetch('/get_log');
                const data = await response.json();
                const logSection = document.getElementById('logSection');
                
                if (data.log.length === 0) {
                    logSection.innerHTML = '<p>No interactions yet. Submit a query to see the log.</p>';
                    return;
                }

                const logHTML = data.log.map(entry => `
                    <div class="log-entry">
                        <div class="timestamp">${entry.timestamp}</div>
                        <strong>${entry.role}</strong> @ <strong>${entry.table}</strong>: "${entry.user_query}"<br>
                        <strong>Response:</strong> ${entry.llm_response}<br>
                        <strong>Status:</strong> <span class="status-${entry.decision}">${entry.decision.toUpperCase()}</span> - ${entry.reason}
                    </div>
                `).reverse().join('');

                logSection.innerHTML = logHTML;
            } catch (error) {
                console.error('Error updating log:', error);
            }
        }

        async function clearLog() {
            try {
                await fetch('/clear_log', { method: 'POST' });
                updateLog();
                document.getElementById('results').innerHTML = '';
            } catch (error) {
                console.error('Error clearing log:', error);
            }
        }

        // Load log on page load
        updateLog();
    </script>
</body>
</html>
'''

# Create templates directory and index.html
import os
if not os.path.exists('templates'):
    os.makedirs('templates')

with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write(HTML_TEMPLATE)

if __name__ == '__main__':
    # Check for OpenAI API key
    if not os.getenv('OPENAI_API_KEY'):
        print("⚠️  Warning: OPENAI_API_KEY environment variable not set!")
        print("   Set it with: export OPENAI_API_KEY='your-api-key-here'")
        print("   Or update the code with your API key")
    
    print("🚀 Starting Secure RBAC Query Generation PoC...")
    print("📊 Mock Data Catalog includes:")
    for table, metadata in MOCK_CATALOG.items():
        fields = [f"{field['name']} ({field['sensitivity']})" for field in metadata['fields']]
        print(f"   - {table}: {', '.join(fields)}")
    
    print("\n🔐 Role Permissions:")
    for role, permissions in ROLE_PERMISSIONS.items():
        print(f"   - {role}: {', '.join(permissions)}")
    
    print(f"\n🌐 Access the application at: http://localhost:5000")
    print("📋 Try the demo scenarios listed on the webpage!")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
