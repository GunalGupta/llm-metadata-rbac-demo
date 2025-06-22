# Secure RBAC Query Generation: Proof-of-Concept (PoC)

A proof-of-concept Flask web application that demonstrates secure metadata-driven SQL query generation with Role-Based Access Control (RBAC) using Large Language Models (LLMs) and a mock AWS Data Catalog API.

## 🎯 Overview

This prototype showcases how integrating metadata from a data catalog with user roles enhances security by preventing LLMs from generating queries that access unauthorized data. The application simulates real-world scenarios where different user roles have different levels of data access permissions.

## ✨ Key Features

### 🔐 Role-Based Access Control (RBAC)
- **Basic Role**: Access to public fields only
- **Admin Role**: Access to all fields (public, PII, confidential)
- Real-time field filtering based on role permissions

### 📊 Mock AWS Data Catalog API
- RESTful endpoint simulating AWS Data Catalog: `/metadata/<table_name>`
- Sample tables with realistic data structures:
  - **Users Table**: id (public), name (public), email (PII), salary (confidential)
  - **Orders Table**: order_id (public), user_id (public), amount (public), order_date (public)
- Sensitivity classification: public, PII, confidential

### 🤖 LLM Integration
- OpenAI ```gpt-4o-mini``` integration for natural language to SQL conversion
- Metadata-filtered prompts to ensure secure query generation
- Intelligent rejection of queries requiring unauthorized fields

### 🛡️ Security Features
- Metadata filtering before LLM processing
- Generated query validation using SQL parsing
- Comprehensive audit logging
- Environment-based API key management

### 🖥️ Interactive Web Interface
- User-friendly role and table selection
- Natural language query input
- Real-time query processing and validation
- Live interaction logging and audit trail
- Built-in demo scenarios for presentations

## 🚀 Quick Start

### Prerequisites
- Python 3.7+
- OpenAI API key

### Installation

1. **Clone or download the application files**

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up OpenAI API key:**
   ```bash
   # Option 1: Environment variable (recommended)
   export OPENAI_API_KEY='your-openai-api-key-here'
   
   # Option 2: Create .env file
   echo "OPENAI_API_KEY=your-openai-api-key-here" > .env
   ```

4. **Run the application:**
   ```bash
   python app.py
   ```

5. **Access the demo:**
   Open your browser and navigate to `http://localhost:5000`

## 🎯 Scenarios

Try these scenarios to understande RBAC and security features:

### Scenario 1: Basic User - Public Data Access ✅
- **Role**: Basic
- **Table**: Users
- **Query**: "List all user names"
- **Expected**: Query accepted, generates `SELECT name FROM users`

### Scenario 2: Basic User - Confidential Data Blocked ❌
- **Role**: Basic
- **Table**: Users
- **Query**: "What is the average salary?"
- **Expected**: Query rejected, salary field not accessible

### Scenario 3: Admin User - Full Access ✅
- **Role**: Admin
- **Table**: Users
- **Query**: "What is the average salary?"
- **Expected**: Query accepted, generates `SELECT AVG(salary) FROM users`

### Scenario 4: Basic User - PII Data Blocked ❌
- **Role**: Basic
- **Table**: Users
- **Query**: "List user emails"
- **Expected**: Query rejected, email field (PII) not accessible

### Scenario 5: Admin User - PII Access ✅
- **Role**: Admin
- **Table**: Users
- **Query**: "List user emails"
- **Expected**: Query accepted, generates `SELECT email FROM users`

## 📖 API Endpoints

### Mock Data Catalog API
```
GET /metadata/<table_name>
```
Returns table metadata with field information and sensitivity tags.

**Example Response:**
```json
{
  "fields": [
    {"name": "id", "type": "int", "sensitivity": "public"},
    {"name": "name", "type": "string", "sensitivity": "public"},
    {"name": "email", "type": "string", "sensitivity": "PII"},
    {"name": "salary", "type": "float", "sensitivity": "confidential"}
  ]
}
```

### Query Processing API
```
POST /process_query
Content-Type: application/json

{
  "role": "basic|admin",
  "table": "users|orders",
  "query": "natural language query"
}
```

### Logging APIs
```
GET /get_log          # Retrieve interaction log
POST /clear_log       # Clear interaction log
```

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Interface │    │   Flask App     │    │   OpenAI API    │
│                 │────│                 │────│                 │
│ • Role Selection│    │ • RBAC Logic    │    │ • Query Gen     │
│ • Query Input   │    │ • Metadata API  │    │ • GPT-4o-mini   │
│ • Results View  │    │ • Validation    │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                       ┌─────────────────┐
                       │  Mock Catalog   │
                       │                 │
                       │ • Table Schema  │
                       │ • Sensitivity   │
                       │ • Field Types   │
                       └─────────────────┘
```

## 🔧 Technical Implementation

### RBAC Implementation
```python
ROLE_PERMISSIONS = {
    'basic': ['public'],
    'admin': ['public', 'PII', 'confidential']
}
```

### Security Validation
1. **Metadata Filtering**: Fields filtered by role before LLM processing
2. **Query Parsing**: Generated SQL parsed to extract field references
3. **Permission Check**: Validates all referenced fields against role permissions
4. **Audit Logging**: All interactions logged with timestamps and decisions

### LLM Prompt Engineering
The application uses carefully crafted prompts that:
- Include only role-authorized field schemas
- Explicitly instruct the LLM to reject unauthorized field requests
- Provide clear rejection messages for unauthorized queries

## 📋 Configuration

### Environment Variables
- `OPENAI_API_KEY`: Your OpenAI API key (required)

### Customizing Data Catalog
Modify the `MOCK_CATALOG` dictionary in `app.py` to add new tables or fields:

```python
MOCK_CATALOG = {
    'your_table': {
        'fields': [
            {'name': 'field_name', 'type': 'field_type', 'sensitivity': 'public|PII|confidential'}
        ]
    }
}
```

### Adding New Roles
Extend the `ROLE_PERMISSIONS` dictionary:

```python
ROLE_PERMISSIONS = {
    'basic': ['public'],
    'admin': ['public', 'PII', 'confidential'],
    'analyst': ['public', 'PII']  # New role
}
```

## 🐛 Troubleshooting

### Common Issues

1. **OpenAI API Key Error**
   ```
   Error: OPENAI_API_KEY environment variable not set
   ```
   **Solution**: Set the environment variable or update the code with your API key

2. **SQL Parsing Issues**
   - The application uses both `sqlparse` and regex fallback for field extraction
   - Complex queries might require manual parsing logic updates

3. **Template Not Found Error**
   - Ensure the `templates/` directory exists
   - The application automatically creates the template file

## 📚 Dependencies

- **Flask**: Web framework for the application
- **OpenAI**: LLM integration for query generation
- **sqlparse**: SQL parsing and field extraction
- **python-dotenv**: Environment variable management (optional)

## Key Points
- **Security First**: Metadata filtering prevents unauthorized data exposure
- **Real-time Validation**: Query parsing ensures compliance even if LLM makes mistakes
- **Audit Trail**: Complete logging for compliance and monitoring
- **Role Flexibility**: Easy to extend with new roles and permissions

## 🔗 Additional Resources

- [OpenAI API Documentation](https://platform.openai.com/docs/models)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [AWS Glue Data Catalog](https://docs.aws.amazon.com/glue/latest/dg/catalog-and-crawler.html)
- [SQL Parsing with sqlparse](https://sqlparse.readthedocs.io/)

---

**Note**: This is a demonstration application. For production deployment, implement proper security measures including authentication, authorization, input validation, and secure API key management.
