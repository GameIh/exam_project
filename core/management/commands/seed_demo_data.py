from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (
    AttemptAnswer,
    CorrectChoiceKey,
    CorrectTextKey,
    Exam,
    ExamAttempt,
    ExamQuestion,
    Question,
    QuestionOption,
    Subject,
    SubjectEnrollment,
    User,
)


class Command(BaseCommand):
    help = "Пересоздаёт демонстрационные данные для маршрута студента."

    @transaction.atomic
    def handle(self, *args, **options):
        self._clear_exam_data()
        users = self._users()
        subjects = self._subjects(users)
        self._enrollments(users, subjects)
        exams = self._exams(subjects)
        questions = self._questions(subjects)
        self._exam_questions(exams, questions)
        self._attempts(users, exams, questions)
        self.stdout.write(self.style.SUCCESS("Демонстрационные данные созданы."))

    def _clear_exam_data(self):
        AttemptAnswer.objects.all().delete()
        ExamAttempt.objects.all().delete()
        CorrectChoiceKey.objects.all().delete()
        CorrectTextKey.objects.all().delete()
        QuestionOption.objects.all().delete()
        ExamQuestion.objects.all().delete()
        Question.objects.all().delete()
        Exam.objects.all().delete()
        SubjectEnrollment.objects.all().delete()
        Subject.objects.all().delete()

    def _users(self):
        data = {
            "admin": {
                "email": "admin@example.com",
                "full_name": "Администратор",
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
            "teacher": {
                "email": "teacher@example.com",
                "full_name": "Ирина Белова",
                "role": User.Role.TEACHER,
                "is_staff": True,
                "is_superuser": False,
            },
            "web_teacher": {
                "email": "web.teacher@example.com",
                "full_name": "Ольга Соколова",
                "role": User.Role.TEACHER,
                "is_staff": True,
                "is_superuser": False,
            },
            "algo_teacher": {
                "email": "algo.teacher@example.com",
                "full_name": "Максим Орлов",
                "role": User.Role.TEACHER,
                "is_staff": True,
                "is_superuser": False,
            },
            "student": {
                "email": "student@example.com",
                "full_name": "Дмитрий Ковалёв",
                "role": User.Role.STUDENT,
                "is_staff": False,
                "is_superuser": False,
            },
            "student_anna": {
                "email": "anna.student@example.com",
                "full_name": "Анна Смирнова",
                "role": User.Role.STUDENT,
                "is_staff": False,
                "is_superuser": False,
            },
            "student_maxim": {
                "email": "maxim.student@example.com",
                "full_name": "Максим Петров",
                "role": User.Role.STUDENT,
                "is_staff": False,
                "is_superuser": False,
            },
        }
        users = {}
        for key, values in data.items():
            user, _ = User.objects.get_or_create(email=values["email"])
            user.full_name = values["full_name"]
            user.role = values["role"]
            user.is_staff = values["is_staff"]
            user.is_superuser = values["is_superuser"]
            user.is_active = True
            user.set_password("demo12345")
            user.save()
            users[key] = user
        return users

    def _subjects(self, users):
        return {
            "db": Subject.objects.create(
                title="Базы данных",
                description="Проектирование реляционных баз данных и SQL.",
                teacher=users["teacher"],
            ),
            "web": Subject.objects.create(
                title="Веб-разработка",
                description="HTML, CSS, серверные шаблоны и веб-приложения.",
                teacher=users["web_teacher"],
            ),
            "algo": Subject.objects.create(
                title="Алгоритмы",
                description="Алгоритмы, структуры данных, сложность и поиск.",
                teacher=users["algo_teacher"],
            ),
        }

    def _enrollments(self, users, subjects):
        student = users["student"]
        for subject in subjects.values():
            SubjectEnrollment.objects.create(subject=subject, student=student)
        for key in ("student_anna", "student_maxim"):
            SubjectEnrollment.objects.create(subject=subjects["db"], student=users[key])

    def _exams(self, subjects):
        now = timezone.now()
        return {
            "db_final": Exam.objects.create(
                subject=subjects["db"],
                title="Итоговый экзамен",
                description="Проверка знаний по таблицам, связям, индексам, представлениям и SQL-запросам.",
                time_limit_sec=60 * 60,
                attempts_limit=2,
                randomize_questions=False,
                show_answers_after=True,
                available_from=now - timezone.timedelta(days=3),
                available_to=now + timezone.timedelta(days=20),
                is_published=True,
            ),
            "web_mid": Exam.objects.create(
                subject=subjects["web"],
                title="Промежуточный контроль",
                description="HTML, CSS, REST API, формы, шаблоны и архитектура веб-приложений.",
                time_limit_sec=50 * 60,
                attempts_limit=1,
                randomize_questions=False,
                show_answers_after=True,
                available_from=now - timezone.timedelta(days=1),
                available_to=now + timezone.timedelta(days=15),
                is_published=True,
            ),
            "algo_module": Exam.objects.create(
                subject=subjects["algo"],
                title="Модуль 2",
                description="Вопросы по сложности алгоритмов, деревьям, сортировкам и поиску.",
                time_limit_sec=45 * 60,
                attempts_limit=1,
                randomize_questions=False,
                show_answers_after=True,
                available_from=now + timezone.timedelta(days=2),
                available_to=now + timezone.timedelta(days=25),
                is_published=True,
            ),
        }

    def _single_choice_question(self, subject, text, options, correct_index, explanation):
        question = Question.objects.create(
            subject=subject,
            q_type=Question.Type.SINGLE_CHOICE,
            question_text=text,
            explanation=explanation,
            difficulty=1,
            is_active=True,
        )
        created_options = [
            QuestionOption.objects.create(question=question, option_text=option)
            for option in options
        ]
        CorrectChoiceKey.objects.create(
            question=question,
            option=created_options[correct_index],
        )
        return question

    def _text_question(self, subject, text, answers, explanation):
        question = Question.objects.create(
            subject=subject,
            q_type=Question.Type.TEXT,
            question_text=text,
            explanation=explanation,
            difficulty=2,
            is_active=True,
        )
        for answer in answers:
            CorrectTextKey.objects.create(question=question, accepted_answer=answer)
        return question

    def _questions(self, subjects):
        return {
            "db_relation": self._single_choice_question(
                subjects["db"],
                "Какой тип связи реализуется внешним ключом teacher_id в таблице subjects?",
                [
                    "Один преподаватель — много предметов",
                    "Один предмет — много преподавателей",
                    "Многие ко многим",
                    "Связь отсутствует",
                ],
                0,
                "Один преподаватель может вести несколько предметов.",
            ),
            "db_attempts": self._single_choice_question(
                subjects["db"],
                "Что хранится в таблице exam_attempts?",
                [
                    "Только правильные ответы",
                    "Попытки сдачи: статус, время начала и окончания, баллы и лимит времени",
                    "Только список предметов студента",
                    "Логи авторизации пользователей",
                ],
                1,
                "Таблица хранит историю сдачи экзамена студентом.",
            ),
            "db_view": self._text_question(
                subjects["db"],
                "Кратко поясните назначение представления v_attempt_results.",
                [
                    "представление объединяет попытки экзамены предметы и студентов",
                    "объединяет попытки экзамены предметы и студентов",
                ],
                "Представление удобно для просмотра итогов попыток с данными экзамена и студента.",
            ),
            "db_primary_key": self._single_choice_question(
                subjects["db"],
                "Для чего используется первичный ключ в таблице?",
                [
                    "Для уникальной идентификации записи",
                    "Для хранения пароля пользователя",
                    "Для сортировки таблицы по алфавиту",
                    "Для удаления повторяющихся столбцов",
                ],
                0,
                "Первичный ключ однозначно определяет каждую строку таблицы.",
            ),
            "db_index": self._single_choice_question(
                subjects["db"],
                "Какое назначение чаще всего имеет индекс в базе данных?",
                [
                    "Ускорение поиска и фильтрации данных",
                    "Автоматическое шифрование таблицы",
                    "Создание резервной копии",
                    "Запрет любых изменений в таблице",
                ],
                0,
                "Индекс ускоряет чтение данных, но может замедлять операции записи.",
            ),
            "db_foreign_key": self._single_choice_question(
                subjects["db"],
                "Что обеспечивает внешний ключ?",
                [
                    "Связь и ссылочную целостность между таблицами",
                    "Хранение HTML-шаблонов",
                    "Автоматическую публикацию экзамена",
                    "Сжатие текстовых полей",
                ],
                0,
                "Внешний ключ не даёт сослаться на несуществующую запись.",
            ),
            "db_normalization": self._text_question(
                subjects["db"],
                "Кратко объясните цель нормализации данных.",
                [
                    "уменьшение избыточности и устранение аномалий",
                    "снижение избыточности данных и устранение аномалий",
                ],
                "Нормализация помогает уменьшить дублирование и избежать ошибок обновления.",
            ),
            "db_join": self._single_choice_question(
                subjects["db"],
                "Какой JOIN вернёт только совпадающие строки из двух таблиц?",
                ["LEFT JOIN", "RIGHT JOIN", "INNER JOIN", "FULL JOIN"],
                2,
                "INNER JOIN оставляет только строки, у которых есть соответствие в обеих таблицах.",
            ),
            "db_transaction": self._single_choice_question(
                subjects["db"],
                "Что означает свойство атомарности транзакции?",
                [
                    "Операции выполняются полностью или не выполняются вовсе",
                    "Запрос всегда выполняется быстрее индекса",
                    "Таблица не может иметь внешний ключ",
                    "Данные автоматически сортируются",
                ],
                0,
                "Атомарность защищает данные от частично выполненных изменений.",
            ),
            "db_unique": self._single_choice_question(
                subjects["db"],
                "Какое ограничение запрещает повторение значения в столбце?",
                ["NOT NULL", "CHECK", "UNIQUE", "DEFAULT"],
                2,
                "UNIQUE гарантирует уникальность значения в столбце или наборе столбцов.",
            ),
            "web_templates": self._single_choice_question(
                subjects["web"],
                "Что делает Django-шаблон?",
                [
                    "Создаёт таблицы в базе данных",
                    "Формирует HTML-страницу на основе данных из view",
                    "Запускает Docker-контейнер",
                    "Шифрует пароль пользователя",
                ],
                1,
                "Шаблон получает контекст из view и формирует HTML.",
            ),
            "web_csrf": self._single_choice_question(
                subjects["web"],
                "Для чего нужен CSRF-токен в форме?",
                [
                    "Для защиты POST-запросов от подделки",
                    "Для ускорения загрузки CSS",
                    "Для сортировки вопросов",
                    "Для создания пользователя",
                ],
                0,
                "CSRF-токен помогает убедиться, что форма отправлена с доверенной страницы.",
            ),
            "web_url": self._single_choice_question(
                subjects["web"],
                "За что отвечает файл urls.py в Django-проекте?",
                [
                    "За сопоставление URL-адресов с view-функциями",
                    "За хранение статических изображений",
                    "За настройку цветов интерфейса",
                    "За создание Docker-контейнера",
                ],
                0,
                "urls.py связывает адрес запроса с обработчиком.",
            ),
            "web_view": self._text_question(
                subjects["web"],
                "Что обычно делает view-функция в Django?",
                [
                    "получает запрос подготавливает данные и возвращает ответ",
                    "обрабатывает запрос подготавливает данные и возвращает ответ",
                ],
                "View получает request, выполняет логику и возвращает HTTP-ответ.",
            ),
            "web_static": self._single_choice_question(
                subjects["web"],
                "К чему относятся CSS-файлы в Django-приложении?",
                ["К миграциям", "К статическим файлам", "К моделям", "К сессиям"],
                1,
                "CSS, JavaScript и изображения обычно подключаются как static files.",
            ),
            "web_post": self._single_choice_question(
                subjects["web"],
                "Какой HTTP-метод обычно используют для отправки формы с изменением данных?",
                ["GET", "POST", "HEAD", "OPTIONS"],
                1,
                "POST применяют для действий, которые изменяют состояние приложения.",
            ),
            "web_auth": self._single_choice_question(
                subjects["web"],
                "Какой декоратор удобно использовать для защиты view от неавторизованных пользователей?",
                ["login_required", "csrf_exempt", "staticmethod", "property"],
                0,
                "login_required перенаправляет гостя на страницу входа.",
            ),
            "web_orm": self._single_choice_question(
                subjects["web"],
                "Что делает Django ORM?",
                [
                    "Позволяет работать с таблицами через Python-модели",
                    "Рисует HTML без шаблонов",
                    "Запускает браузерные тесты",
                    "Заменяет CSS-фреймворк",
                ],
                0,
                "ORM преобразует операции с моделями в SQL-запросы.",
            ),
            "algo_complexity": self._single_choice_question(
                subjects["algo"],
                "Какая сложность у бинарного поиска в отсортированном массиве?",
                ["O(n)", "O(log n)", "O(n log n)", "O(1)"],
                1,
                "Бинарный поиск делит область поиска пополам на каждом шаге.",
            ),
            "algo_stack": self._single_choice_question(
                subjects["algo"],
                "Какой принцип работы у стека?",
                ["FIFO", "LIFO", "Random", "Round-robin"],
                1,
                "Стек работает по принципу last in, first out.",
            ),
            "algo_queue": self._single_choice_question(
                subjects["algo"],
                "Какой принцип работы у очереди?",
                ["FIFO", "LIFO", "DFS", "Hashing"],
                0,
                "Очередь обслуживает элементы в порядке поступления.",
            ),
            "algo_tree": self._single_choice_question(
                subjects["algo"],
                "Как называется элемент дерева без потомков?",
                ["Корень", "Лист", "Ребро", "Индекс"],
                1,
                "Листовой узел не имеет дочерних элементов.",
            ),
            "algo_sort": self._single_choice_question(
                subjects["algo"],
                "Какая средняя сложность быстрой сортировки?",
                ["O(n)", "O(n log n)", "O(n²)", "O(log n)"],
                1,
                "В среднем quicksort работает за O(n log n).",
            ),
            "algo_hash": self._text_question(
                subjects["algo"],
                "Для чего используют хеш-таблицу?",
                [
                    "для быстрого поиска по ключу",
                    "быстрый поиск по ключу",
                ],
                "Хеш-таблица позволяет быстро находить значение по ключу.",
            ),
        }

    def _exam_questions(self, exams, questions):
        data = [
            (exams["db_final"], questions["db_relation"], Decimal("2.00"), 1),
            (exams["db_final"], questions["db_attempts"], Decimal("1.00"), 2),
            (exams["db_final"], questions["db_view"], Decimal("3.00"), 3),
            (exams["db_final"], questions["db_primary_key"], Decimal("1.00"), 4),
            (exams["db_final"], questions["db_index"], Decimal("1.00"), 5),
            (exams["db_final"], questions["db_foreign_key"], Decimal("1.00"), 6),
            (exams["db_final"], questions["db_normalization"], Decimal("2.00"), 7),
            (exams["db_final"], questions["db_join"], Decimal("1.00"), 8),
            (exams["db_final"], questions["db_transaction"], Decimal("2.00"), 9),
            (exams["db_final"], questions["db_unique"], Decimal("1.00"), 10),
            (exams["web_mid"], questions["web_templates"], Decimal("2.00"), 1),
            (exams["web_mid"], questions["web_csrf"], Decimal("2.00"), 2),
            (exams["web_mid"], questions["web_url"], Decimal("1.00"), 3),
            (exams["web_mid"], questions["web_view"], Decimal("3.00"), 4),
            (exams["web_mid"], questions["web_static"], Decimal("1.00"), 5),
            (exams["web_mid"], questions["web_post"], Decimal("1.00"), 6),
            (exams["web_mid"], questions["web_auth"], Decimal("1.00"), 7),
            (exams["web_mid"], questions["web_orm"], Decimal("2.00"), 8),
            (exams["algo_module"], questions["algo_complexity"], Decimal("1.00"), 1),
            (exams["algo_module"], questions["algo_stack"], Decimal("1.00"), 2),
            (exams["algo_module"], questions["algo_queue"], Decimal("1.00"), 3),
            (exams["algo_module"], questions["algo_tree"], Decimal("1.00"), 4),
            (exams["algo_module"], questions["algo_sort"], Decimal("2.00"), 5),
            (exams["algo_module"], questions["algo_hash"], Decimal("2.00"), 6),
        ]
        for exam, question, points, order in data:
            ExamQuestion.objects.create(
                exam=exam,
                question=question,
                points=points,
                question_order=order,
            )

    def _attempts(self, users, exams, questions):
        student = users["student"]
        def exam_points(exam):
            return sum(
                ExamQuestion.objects.filter(exam=exam).values_list("points", flat=True),
                Decimal("0"),
            )

        def correct_option(question):
            return question.correct_choice_keys.first().option

        def wrong_option(question):
            correct_id = correct_option(question).option_id
            return question.options.exclude(option_id=correct_id).first()

        db_attempt = ExamAttempt.objects.create(
            exam=exams["db_final"],
            student=student,
            status=ExamAttempt.Status.SUBMITTED,
            start_at=timezone.now() - timezone.timedelta(days=1, hours=1),
            end_at=timezone.now() - timezone.timedelta(days=1),
            time_limit_sec=exams["db_final"].time_limit_sec,
            score_total=Decimal("0.00"),
            score_max=exam_points(exams["db_final"]),
        )
        db_answers = [
            ("db_relation", True, ""),
            ("db_attempts", True, ""),
            ("db_view", True, "Представление объединяет попытки экзамены предметы и студентов"),
            ("db_primary_key", True, ""),
            ("db_index", False, ""),
            ("db_foreign_key", True, ""),
            ("db_normalization", False, "Это просто ускорение запросов"),
            ("db_join", True, ""),
            ("db_transaction", True, ""),
            ("db_unique", True, ""),
        ]
        score_total = Decimal("0.00")
        for key, is_correct, text_answer in db_answers:
            question = questions[key]
            points = ExamQuestion.objects.get(exam=exams["db_final"], question=question).points
            if question.q_type == Question.Type.SINGLE_CHOICE:
                option = correct_option(question) if is_correct else wrong_option(question)
                awarded = points if is_correct else Decimal("0.00")
                AttemptAnswer.objects.create(
                    attempt=db_attempt,
                    question=question,
                    selected_option=option,
                    score_awarded=awarded,
                )
            else:
                awarded = points if is_correct else Decimal("0.00")
                AttemptAnswer.objects.create(
                    attempt=db_attempt,
                    question=question,
                    answer_text=text_answer,
                    score_awarded=awarded,
                )
            score_total += awarded
        db_attempt.score_total = score_total
        db_attempt.save(update_fields=["score_total"])

        for key, score, days_ago in (
            ("student_anna", Decimal("13.00"), 2),
            ("student_maxim", Decimal("9.00"), 3),
        ):
            ExamAttempt.objects.create(
                exam=exams["db_final"],
                student=users[key],
                status=ExamAttempt.Status.SUBMITTED,
                start_at=timezone.now() - timezone.timedelta(days=days_ago, minutes=48),
                end_at=timezone.now() - timezone.timedelta(days=days_ago),
                time_limit_sec=exams["db_final"].time_limit_sec,
                score_total=score,
                score_max=exam_points(exams["db_final"]),
            )

        web_attempt = ExamAttempt.objects.create(
            exam=exams["web_mid"],
            student=student,
            status=ExamAttempt.Status.IN_PROGRESS,
            start_at=timezone.now() - timezone.timedelta(minutes=8),
            time_limit_sec=exams["web_mid"].time_limit_sec,
            score_total=Decimal("0.00"),
            score_max=exam_points(exams["web_mid"]),
        )
        for key, option_index in [
            ("web_templates", 1),
            ("web_csrf", 0),
            ("web_url", 0),
        ]:
            question = questions[key]
            AttemptAnswer.objects.create(
                attempt=web_attempt,
                question=question,
                selected_option=question.options.all()[option_index],
                score_awarded=Decimal("0.00"),
            )
