
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from accounts.roles import ROLE_GROUP_NAMES, ROLE_PERMISSIONS


class Command(BaseCommand):
    help = "Create role groups and synchronize their permissions."

    def handle(self, *args, **options):
        promoted_superusers = 0
        synced_users = 0

        with transaction.atomic():

            # Create each role group and assign its permissions.
            for role, group_name in ROLE_GROUP_NAMES.items():
                group, _ = Group.objects.get_or_create(
                    name=group_name
                )

                permissions = []

                for permission_path in ROLE_PERMISSIONS[role]:
                    app_label, codename = permission_path.split(".", 1)

                    try:
                        permission = Permission.objects.get(
                            content_type__app_label=app_label,
                            codename=codename,
                        )
                    except Permission.DoesNotExist:
                        raise CommandError(
                            f"Permission '{permission_path}' does not exist. "
                            "Check your migrations and accounts/roles.py."
                        )

                    permissions.append(permission)

                group.permissions.set(permissions)

                self.stdout.write(
                    f"Configured group: {group_name}"
                )

            # Synchronize every existing user.
            for user in User.objects.all().iterator():

                # Existing superusers must have the Administrator role.
                if (
                    user.is_superuser
                    and user.role != User.Role.ADMINISTRATOR
                ):
                    user.role = User.Role.ADMINISTRATOR
                    user.save(update_fields=["role"])
                    promoted_superusers += 1
                else:
                    user.sync_role_group()

                synced_users += 1

        self.stdout.write(
            self.style.SUCCESS(
                "\nRole setup completed successfully!\n"
                f"Groups configured: {len(ROLE_GROUP_NAMES)}\n"
                f"Users synchronized: {synced_users}\n"
                f"Superusers promoted: {promoted_superusers}"
            )
        )
