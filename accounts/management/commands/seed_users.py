
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Department, User


DEMO_PASSWORD = "ChangeMe123!"


DEMO_USERS = [
    {
        "username": "demo.administrator",
        "first_name": "Demo",
        "last_name": "Administrator",
        "email": "administrator@example.test",
        "employee_id": "DEMO-ADM",
        "role": User.Role.ADMINISTRATOR,
    },
    {
        "username": "demo.employee",
        "first_name": "Demo",
        "last_name": "Employee",
        "email": "employee@example.test",
        "employee_id": "DEMO-EMP",
        "role": User.Role.EMPLOYEE,
    },
    {
        "username": "demo.manager",
        "first_name": "Demo",
        "last_name": "Manager",
        "email": "manager@example.test",
        "employee_id": "DEMO-MGR",
        "role": User.Role.MANAGER,
    },
    {
        "username": "demo.inventory",
        "first_name": "Demo",
        "last_name": "Inventory",
        "email": "inventory@example.test",
        "employee_id": "DEMO-INV",
        "role": User.Role.INVENTORY_STAFF,
    },
    {
        "username": "demo.purchasing",
        "first_name": "Demo",
        "last_name": "Purchasing",
        "email": "purchasing@example.test",
        "employee_id": "DEMO-PUR",
        "role": User.Role.PURCHASING_STAFF,
    },
    {
        "username": "demo.receiving",
        "first_name": "Demo",
        "last_name": "Receiving",
        "email": "receiving@example.test",
        "employee_id": "DEMO-REC",
        "role": User.Role.RECEIVING_STAFF,
    },
]


class Command(BaseCommand):
    help = "Create one demo account for each system role."

    @transaction.atomic
    def handle(self, *args, **options):

        department = Department.objects.filter(
            is_active=True
        ).order_by("name").first()

        if department is None:
            department = Department.objects.create(
                name="General",
                code="GEN",
            )

        created_count = 0
        updated_count = 0

        for data in DEMO_USERS:
            username = data["username"]

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    **data,
                    "department": department,
                    "is_active": True,
                    "is_staff": (
                        data["role"] == User.Role.ADMINISTRATOR
                    ),
                },
            )

            user.first_name = data["first_name"]
            user.last_name = data["last_name"]
            user.email = data["email"]
            user.employee_id = data["employee_id"]
            user.role = data["role"]
            user.department = department
            user.is_active = True
            user.is_staff = (
                user.is_superuser
                or data["role"] == User.Role.ADMINISTRATOR
            )

            user.set_password(DEMO_PASSWORD)
            user.save()

            if created:
                created_count += 1
            else:
                updated_count += 1

            self.stdout.write(
                f"Created/updated: {username} "
                f"({data['role']})"
            )

        self.stdout.write(
            self.style.SUCCESS(
                "\nDemo accounts ready!\n"
                f"Created: {created_count}\n"
                f"Updated: {updated_count}\n"
                f"Password for all demo accounts: {DEMO_PASSWORD}"
            )
        )
