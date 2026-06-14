from django.core.management.base import BaseCommand

from core.models import User


class Command(BaseCommand):
    help = "Создаёт тестовых пользователей для проверки авторизации."

    def handle(self, *args, **options):
        users = [
            {
                "email": "admin@example.com",
                "full_name": "Администратор",
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
            {
                "email": "teacher@example.com",
                "full_name": "Ирина Белова",
                "role": User.Role.TEACHER,
                "is_staff": True,
                "is_superuser": False,
            },
            {
                "email": "student@example.com",
                "full_name": "Дмитрий Ковалёв",
                "role": User.Role.STUDENT,
                "is_staff": False,
                "is_superuser": False,
            },
        ]

        for data in users:
            user, _ = User.objects.get_or_create(email=data["email"])
            user.full_name = data["full_name"]
            user.role = data["role"]
            user.is_staff = data["is_staff"]
            user.is_superuser = data["is_superuser"]
            user.is_active = True
            user.set_password("demo12345")
            user.save()

        self.stdout.write(self.style.SUCCESS("Тестовые пользователи созданы."))
