# Rhodel Fruit and Vegetable Trading
## Internal Requisition and Procurement Management System

A Django-based web application for managing internal item requisitions, inventory availability, purchasing, supplier quotations, purchase orders, delivery receiving, inventory registration, and item issuance.

The system uses PostgreSQL for data storage and role-based access control to manage the responsibilities of different staff members.

## Technologies Used

- Python
- Django
- PostgreSQL
- Psycopg
- Bootstrap
- HTML, CSS, and JavaScript

## User Roles

The system supports six user roles:

1. **Administrator** — Manage user accounts, roles, and departments; access administrative reports.
2. **Employee** — Create requisitions, track requests, and acknowledge received items.
3. **Manager** — Review, approve, or reject requisitions and approve budgets.
4. **Inventory Staff** — Maintain inventory, register accepted items, issue items, and manage assets.
5. **Purchasing Staff** — Manage purchase requests, suppliers, quotations, and purchase orders.
6. **Receiving Staff** — Verify deliveries, record accepted quantities, report discrepancies, and track supplier resolutions.

## System Modules

- User and Department Management
- Internal Requisition Management
- Requisition Approval
- Inventory Availability and Stock Reservation
- Purchase Request Management
- Supplier and Supplier Quotation Management
- Budget Approval
- Purchase Order Management
- Delivery and Receiving
- Delivery Discrepancy and Supplier Resolution
- Inventory Registration
- Asset Management and Item Assignment
- Item Issuance and Employee Acknowledgement
- Reports
- Audit Trail

## Requirements

- Python
- PostgreSQL
- Git
- Visual Studio Code or another code editor

## Installation

### 1. Open the project directory

Open PowerShell in the project folder:

```powershell
cd "C:\Users\Jobert De Guia\RequisitionSystem"
```

### 2. Create a virtual environment

```powershell
py -m venv .venv
```

### 3. Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

### 4. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

If PowerShell activation is unavailable, use the virtual environment's Python executable directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## PostgreSQL Setup

1. Open pgAdmin 4.
2. Connect to your PostgreSQL server.
3. Create a database for the project.
4. Create or select a PostgreSQL user with access to the database.
5. Keep the database name, username, and password available for environment configuration.

## Environment Configuration

The project uses `python-decouple` to read environment settings.

Create a `.env` file in the project root if one does not already exist.

Example:

```env
SECRET_KEY=replace-with-a-secure-secret-key
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

DB_NAME=your_database_name
DB_USER=your_database_user
DB_PASSWORD=your_database_password
DB_HOST=localhost
DB_PORT=5432
```

Replace the example values with your own PostgreSQL configuration.

**Do not commit `.env` or database credentials to Git.**

For production deployment, set `DEBUG=False` and configure appropriate production security settings.

## Database Migration

After configuring PostgreSQL and the environment variables, run:

```powershell
python manage.py migrate
```

To create an administrator account:

```powershell
python manage.py createsuperuser
```

## Run the Development Server

```powershell
python manage.py runserver
```

Open the application in your browser:

http://127.0.0.1:8000/

To stop the development server, press `Ctrl + C` in PowerShell.

## Testing

Run the automated test suite:

```powershell
python manage.py test
```

Check the Django configuration:

```powershell
python manage.py check
```

Check for missing model migrations:

```powershell
python manage.py makemigrations --check --dry-run
```

## Main Business Process

1. An employee submits an internal requisition.
2. A manager reviews and approves or rejects the request.
3. The system checks inventory availability and reserves available stock.
4. Shortages proceed through purchasing and procurement.
5. Purchasing staff manage suppliers, quotations, budget approvals, and purchase orders.
6. Receiving staff verify deliveries and record accepted, damaged, or incorrect items.
7. Accepted quantities proceed to inventory registration.
8. Inventory staff issue items or assign assets.
9. Employees acknowledge received items.
10. The requisition is closed after its required fulfillment process is completed.

## Data Integrity and Security

The system uses database relationships, transaction handling, role-based permissions, and audit logging to support reliable business operations and controlled access.

Users should only perform actions permitted by their assigned role.

## Development Notes

- Use the project's virtual environment when installing packages or running Django commands.
- Use the application workflow to record inventory transactions.
- Do not manually change inventory quantities to simulate completed transactions.
- Run automated tests after making code changes.
- Keep `.env`, passwords, and private database credentials out of public repositories.
