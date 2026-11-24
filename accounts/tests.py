
import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import Department

User = get_user_model()


class AccountsTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.department = Department.objects.create(
            name="Test Department",
            code="TEST",
        )

        call_command(
            "setup_roles",
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

        cls.administrator = cls.make_user(
            "test.admin",
            User.Role.ADMINISTRATOR,
        )

        cls.employee = cls.make_user(
            "test.employee",
            User.Role.EMPLOYEE,
        )

        cls.manager = cls.make_user(
            "test.manager",
            User.Role.MANAGER,
        )
        cls.inventory_staff = cls.make_user(
            "test.inventory",
            User.Role.INVENTORY_STAFF,
        )

        cls.purchasing_staff = cls.make_user(
            "test.purchasing",
            User.Role.PURCHASING_STAFF,
        )

        cls.receiving_staff = cls.make_user(
            "test.receiving",
            User.Role.RECEIVING_STAFF,
        )
        

        cls.superuser = User.objects.create_superuser(
            username="test.superuser",
            email="superuser@example.test",
            password="SafeTestPass123!",
            department=cls.department,
        )

    @classmethod
    def make_user(cls, username, role):
        return User.objects.create_user(
            username=username,
            password="SafeTestPass123!",
            role=role,
            department=cls.department,
            is_staff=(role == User.Role.ADMINISTRATOR),
        )

    # DASHBOARD TESTS

    def test_home_redirects_to_employee_dashboard(self):
        self.client.force_login(self.employee)

        response = self.client.get(reverse("home"))

        self.assertRedirects(
            response,
            reverse("dashboard-employee"),
        )

    def test_dashboard_requires_login(self):
        response = self.client.get(
            reverse("dashboard-employee")
        )

        self.assertEqual(response.status_code, 302)

    def test_employee_cannot_access_manager_dashboard(self):
        self.client.force_login(self.employee)

        response = self.client.get(
            reverse("dashboard-manager")
        )

        self.assertEqual(response.status_code, 403)


    def test_each_role_can_access_own_dashboard(self):
        dashboard_users = [
            (self.administrator, "dashboard-administrator"),
            (self.employee, "dashboard-employee"),
            (self.manager, "dashboard-manager"),
            (self.inventory_staff, "dashboard-inventory"),
            (self.purchasing_staff, "dashboard-purchasing"),
            (self.receiving_staff, "dashboard-receiving"),
        ]

        for user, dashboard_name in dashboard_users:
            with self.subTest(role=user.role):
                self.client.force_login(user)

                response = self.client.get(
                    reverse(dashboard_name)
                )

                self.assertEqual(response.status_code, 200)

    def test_employee_cannot_access_other_role_dashboards(self):
        self.client.force_login(self.employee)

        restricted_dashboards = [
            "dashboard-administrator",
            "dashboard-manager",
            "dashboard-inventory",
            "dashboard-purchasing",
            "dashboard-receiving",
        ]

        for dashboard_name in restricted_dashboards:
            with self.subTest(dashboard=dashboard_name):
                response = self.client.get(
                    reverse(dashboard_name)
                )

                self.assertEqual(response.status_code, 403)


    # ROLE PERMISSION TESTS

    def test_manager_has_approval_permission(self):
        self.assertTrue(
            self.manager.has_perm(
                "requisitions.approve_requisition"
            )
        )

    def test_employee_does_not_have_approval_permission(self):
        self.assertFalse(
            self.employee.has_perm(
                "requisitions.approve_requisition"
            )
        )

    def test_role_change_updates_group_membership(self):
        user = self.make_user(
            "test.rolechange",
            User.Role.EMPLOYEE,
        )

        user.role = User.Role.MANAGER
        user.save(update_fields=["role"])

        user.refresh_from_db()

        self.assertTrue(
            user.groups.filter(name="Manager").exists()
        )

        self.assertFalse(
            user.groups.filter(name="Employee").exists()
        )

    # LOGIN AND LOGOUT TESTS

    def test_logout_only_accepts_post(self):
        self.client.force_login(self.employee)

        get_response = self.client.get(reverse("logout"))

        self.assertEqual(get_response.status_code, 405)

        post_response = self.client.post(reverse("logout"))

        self.assertEqual(post_response.status_code, 302)

        self.assertNotIn(
            "_auth_user_id",
            self.client.session,
        )

    def test_deactivated_user_is_logged_out(self):
        self.client.force_login(self.employee)

        self.employee.is_active = False
        self.employee.save(update_fields=["is_active"])

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 302)

    # USER MANAGEMENT TESTS

    def test_administrator_can_view_user_list(self):
        self.client.force_login(self.administrator)

        response = self.client.get(reverse("user-list"))

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            self.employee.username,
        )

        self.assertNotContains(
            response,
            self.superuser.username,
        )

    def test_employee_cannot_view_user_list(self):
        self.client.force_login(self.employee)

        response = self.client.get(reverse("user-list"))

        self.assertEqual(response.status_code, 403)

    def test_non_superuser_cannot_edit_superuser(self):
        self.client.force_login(self.administrator)

        response = self.client.get(
            reverse(
                "user-update",
                kwargs={"pk": self.superuser.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_administrator_cannot_change_own_role_or_status(self):
        self.client.force_login(self.administrator)

        response = self.client.post(
            reverse(
                "user-update",
                kwargs={"pk": self.administrator.pk},
            ),
            {
                "username": self.administrator.username,
                "first_name": self.administrator.first_name,
                "last_name": self.administrator.last_name,
                "email": self.administrator.email,
                "employee_id": "",
                "phone": "",
                "department": self.department.pk,
                "role": User.Role.EMPLOYEE,
                "is_active": "false",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.administrator.refresh_from_db()

        self.assertEqual(
            self.administrator.role,
            User.Role.ADMINISTRATOR,
        )

        self.assertTrue(self.administrator.is_active)

    def test_administrator_can_create_employee(self):
        self.client.force_login(self.administrator)

        response = self.client.post(
            reverse("user-create"),
            {
                "username": "new.employee",
                "first_name": "New",
                "last_name": "Employee",
                "email": "newemployee@example.test",
                "employee_id": "NEW-001",
                "phone": "",
                "department": self.department.pk,
                "role": User.Role.EMPLOYEE,
                "password1": "SafeTestPass123!",
                "password2": "SafeTestPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)

        new_user = User.objects.get(
            username="new.employee"
        )

        self.assertEqual(
            new_user.role,
            User.Role.EMPLOYEE,
        )

        self.assertTrue(
            new_user.groups.filter(name="Employee").exists()
        )

        self.assertFalse(new_user.is_staff)
