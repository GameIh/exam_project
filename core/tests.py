from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
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


class StudentExamFlowTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            email="teacher@test.local",
            password="pass12345",
            full_name="Преподаватель",
            role=User.Role.TEACHER,
            is_staff=True,
        )
        self.student = User.objects.create_user(
            email="student@test.local",
            password="pass12345",
            full_name="Студент",
            role=User.Role.STUDENT,
        )
        self.subject = Subject.objects.create(
            title="Базы данных",
            teacher=self.teacher,
        )
        SubjectEnrollment.objects.create(subject=self.subject, student=self.student)
        self.exam = Exam.objects.create(
            subject=self.subject,
            title="Итоговый экзамен",
            time_limit_sec=3600,
            attempts_limit=2,
            is_published=True,
            available_from=timezone.now() - timezone.timedelta(days=1),
            available_to=timezone.now() + timezone.timedelta(days=1),
        )
        self.choice_question = Question.objects.create(
            subject=self.subject,
            q_type=Question.Type.SINGLE_CHOICE,
            question_text="Что хранится в exam_attempts?",
        )
        self.wrong_option = QuestionOption.objects.create(
            question=self.choice_question,
            option_text="Только правильные ответы",
        )
        self.correct_option = QuestionOption.objects.create(
            question=self.choice_question,
            option_text="Попытки сдачи экзамена",
        )
        CorrectChoiceKey.objects.create(
            question=self.choice_question,
            option=self.correct_option,
        )
        self.text_question = Question.objects.create(
            subject=self.subject,
            q_type=Question.Type.TEXT,
            question_text="Назначение представления результатов",
        )
        CorrectTextKey.objects.create(
            question=self.text_question,
            accepted_answer="объединяет попытки экзамены предметы и студентов",
        )
        ExamQuestion.objects.create(
            exam=self.exam,
            question=self.choice_question,
            points=Decimal("2.00"),
            question_order=1,
        )
        ExamQuestion.objects.create(
            exam=self.exam,
            question=self.text_question,
            points=Decimal("3.00"),
            question_order=2,
        )

    def test_student_answers_are_graded(self):
        self.client.login(username="student@test.local", password="pass12345")
        response = self.client.post(reverse("start_exam", args=[self.exam.exam_id]))
        self.assertEqual(response.status_code, 302)

        attempt = ExamAttempt.objects.get(student=self.student, exam=self.exam)
        response = self.client.post(
            reverse("exam_taking", args=[attempt.attempt_id]),
            {
                f"choice_{self.choice_question.question_id}": str(self.correct_option.option_id),
                f"text_{self.text_question.question_id}": "Объединяет попытки, экзамены, предметы и студентов!",
                "action": "submit",
            },
        )

        self.assertRedirects(
            response,
            reverse("attempt_results", args=[attempt.attempt_id]),
            fetch_redirect_response=False,
        )
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, ExamAttempt.Status.SUBMITTED)
        self.assertEqual(attempt.score_total, Decimal("5.00"))
        self.assertEqual(attempt.score_max, Decimal("5.00"))
        self.assertEqual(AttemptAnswer.objects.filter(attempt=attempt).count(), 2)

    def test_expired_attempt_is_closed_on_server(self):
        self.client.login(username="student@test.local", password="pass12345")
        attempt = ExamAttempt.objects.create(
            exam=self.exam,
            student=self.student,
            status=ExamAttempt.Status.IN_PROGRESS,
            start_at=timezone.now() - timezone.timedelta(minutes=2),
            time_limit_sec=60,
        )

        response = self.client.get(reverse("exam_taking", args=[attempt.attempt_id]))

        self.assertRedirects(
            response,
            reverse("attempt_results", args=[attempt.attempt_id]),
            fetch_redirect_response=False,
        )
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, ExamAttempt.Status.EXPIRED)
        self.assertEqual(attempt.score_max, Decimal("5.00"))

    def test_student_cannot_start_exam_before_available_window(self):
        self.client.login(username="student@test.local", password="pass12345")
        self.exam.available_from = timezone.now() + timezone.timedelta(days=1)
        self.exam.save(update_fields=["available_from"])

        response = self.client.post(reverse("start_exam", args=[self.exam.exam_id]))

        self.assertRedirects(response, reverse("exam_selection"))
        self.assertFalse(
            ExamAttempt.objects.filter(student=self.student, exam=self.exam).exists()
        )

    def test_student_cannot_start_exam_without_questions(self):
        self.client.login(username="student@test.local", password="pass12345")
        empty_exam = Exam.objects.create(
            subject=self.subject,
            title="Пустой экзамен",
            time_limit_sec=1800,
            attempts_limit=1,
            is_published=True,
            available_from=timezone.now() - timezone.timedelta(days=1),
            available_to=timezone.now() + timezone.timedelta(days=1),
        )

        response = self.client.post(reverse("start_exam", args=[empty_exam.exam_id]))

        self.assertRedirects(response, reverse("exam_selection"))
        self.assertFalse(
            ExamAttempt.objects.filter(student=self.student, exam=empty_exam).exists()
        )

    def test_attempt_limit_is_enforced(self):
        self.client.login(username="student@test.local", password="pass12345")
        self.exam.attempts_limit = 1
        self.exam.save(update_fields=["attempts_limit"])
        ExamAttempt.objects.create(
            exam=self.exam,
            student=self.student,
            status=ExamAttempt.Status.SUBMITTED,
            time_limit_sec=3600,
            score_total=Decimal("5.00"),
            score_max=Decimal("5.00"),
            end_at=timezone.now(),
        )

        response = self.client.post(reverse("start_exam", args=[self.exam.exam_id]))

        self.assertRedirects(response, reverse("exam_selection"))
        self.assertEqual(ExamAttempt.objects.filter(student=self.student, exam=self.exam).count(), 1)

    def test_student_cannot_open_another_student_result(self):
        other_student = User.objects.create_user(
            email="other.student@test.local",
            password="pass12345",
            full_name="Другой студент",
            role=User.Role.STUDENT,
        )
        attempt = ExamAttempt.objects.create(
            exam=self.exam,
            student=other_student,
            status=ExamAttempt.Status.SUBMITTED,
            time_limit_sec=3600,
            score_total=Decimal("5.00"),
            score_max=Decimal("5.00"),
            end_at=timezone.now(),
        )
        self.client.login(username="student@test.local", password="pass12345")

        response = self.client.get(reverse("attempt_results", args=[attempt.attempt_id]))

        self.assertEqual(response.status_code, 404)

    def test_results_page_lists_all_completed_attempts(self):
        older_attempt = ExamAttempt.objects.create(
            exam=self.exam,
            student=self.student,
            status=ExamAttempt.Status.SUBMITTED,
            time_limit_sec=3600,
            score_total=Decimal("3.00"),
            score_max=Decimal("5.00"),
            end_at=timezone.now() - timezone.timedelta(hours=1),
        )
        latest_attempt = ExamAttempt.objects.create(
            exam=self.exam,
            student=self.student,
            status=ExamAttempt.Status.EXPIRED,
            time_limit_sec=3600,
            score_total=Decimal("2.00"),
            score_max=Decimal("5.00"),
            end_at=timezone.now(),
        )
        self.client.login(username="student@test.local", password="pass12345")

        response = self.client.get(reverse("results"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/result_list.html")
        self.assertContains(response, reverse("attempt_results", args=[older_attempt.attempt_id]))
        self.assertContains(response, reverse("attempt_results", args=[latest_attempt.attempt_id]))
        self.assertEqual(
            [row["attempt"] for row in response.context["result_rows"]],
            [latest_attempt, older_attempt],
        )


class TeacherDashboardTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            email="teacher@test.local",
            password="pass12345",
            full_name="Преподаватель",
            role=User.Role.TEACHER,
            is_staff=True,
        )
        self.other_teacher = User.objects.create_user(
            email="other.teacher@test.local",
            password="pass12345",
            full_name="Другой преподаватель",
            role=User.Role.TEACHER,
            is_staff=True,
        )
        self.student = User.objects.create_user(
            email="student@test.local",
            password="pass12345",
            full_name="Студент",
            role=User.Role.STUDENT,
        )
        self.subject = Subject.objects.create(title="Базы данных", teacher=self.teacher)
        self.other_subject = Subject.objects.create(
            title="Веб-разработка",
            teacher=self.other_teacher,
        )
        self.exam = Exam.objects.create(
            subject=self.subject,
            title="Итоговый экзамен",
            time_limit_sec=3600,
            attempts_limit=1,
            is_published=True,
        )
        self.other_exam = Exam.objects.create(
            subject=self.other_subject,
            title="Чужой экзамен",
            time_limit_sec=3600,
            attempts_limit=1,
            is_published=True,
        )
        self.question = Question.objects.create(
            subject=self.subject,
            q_type=Question.Type.SINGLE_CHOICE,
            question_text="Вопрос по базам данных",
        )
        ExamQuestion.objects.create(
            exam=self.exam,
            question=self.question,
            points=Decimal("1.00"),
            question_order=1,
        )
        ExamAttempt.objects.create(
            exam=self.exam,
            student=self.student,
            status=ExamAttempt.Status.SUBMITTED,
            time_limit_sec=3600,
            score_total=Decimal("1.00"),
            score_max=Decimal("1.00"),
            end_at=timezone.now(),
        )

    def test_teacher_sees_dashboard_and_own_exam_detail(self):
        self.client.login(username="teacher@test.local", password="pass12345")

        dashboard = self.client.get(reverse("teacher_dashboard"))
        detail = self.client.get(reverse("teacher_exam_detail", args=[self.exam.exam_id]))

        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Итоговый экзамен")
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Результаты студентов")
        self.assertContains(detail, "Студент")
        self.assertNotContains(dashboard, "Админ-панель")

    def test_teacher_cannot_open_another_teacher_exam(self):
        self.client.login(username="teacher@test.local", password="pass12345")

        response = self.client.get(
            reverse("teacher_exam_detail", args=[self.other_exam.exam_id])
        )

        self.assertEqual(response.status_code, 404)

    def test_student_cannot_open_teacher_dashboard(self):
        self.client.login(username="student@test.local", password="pass12345")

        response = self.client.get(reverse("teacher_dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_teacher_can_create_exam_only_for_own_subject(self):
        self.client.login(username="teacher@test.local", password="pass12345")

        response = self.client.post(
            reverse("teacher_exam_create"),
            {
                "subject": self.subject.subject_id,
                "title": "Новый экзамен",
                "description": "Проверка",
                "duration_minutes": 45,
                "attempts_limit": 2,
                "show_answers_after": "on",
            },
        )

        exam = Exam.objects.get(title="Новый экзамен")
        self.assertRedirects(
            response,
            reverse("teacher_exam_questions", args=[exam.exam_id]),
            fetch_redirect_response=False,
        )
        self.assertEqual(exam.subject, self.subject)
        self.assertEqual(exam.time_limit_sec, 2700)

        foreign_response = self.client.post(
            reverse("teacher_exam_create"),
            {
                "subject": self.other_subject.subject_id,
                "title": "Чужой предмет",
                "duration_minutes": 30,
                "attempts_limit": 1,
            },
        )
        self.assertEqual(foreign_response.status_code, 200)
        self.assertFalse(Exam.objects.filter(title="Чужой предмет").exists())

    def test_teacher_can_create_question_with_answer_key(self):
        self.client.login(username="teacher@test.local", password="pass12345")

        response = self.client.post(
            reverse("teacher_question_create"),
            {
                "subject": self.subject.subject_id,
                "q_type": Question.Type.SINGLE_CHOICE,
                "question_text": "Новый тестовый вопрос",
                "difficulty": 1,
                "is_active": "on",
                "options_text": "Первый\nВторой\nТретий",
                "correct_answer": "Второй",
                "accepted_answers": "",
            },
        )

        self.assertRedirects(response, reverse("teacher_question_list"))
        question = Question.objects.get(question_text="Новый тестовый вопрос")
        self.assertEqual(question.options.count(), 3)
        self.assertEqual(
            question.correct_choice_keys.get().option.option_text,
            "Второй",
        )

    def test_question_bank_groups_and_filters_questions(self):
        second_subject = Subject.objects.create(
            title="Информационные системы",
            teacher=self.teacher,
        )
        Question.objects.create(
            subject=second_subject,
            q_type=Question.Type.TEXT,
            question_text="Архитектура информационной системы",
            is_active=False,
        )
        self.client.login(username="teacher@test.local", password="pass12345")

        grouped = self.client.get(reverse("teacher_question_list"))
        filtered = self.client.get(
            reverse("teacher_question_list"),
            {"q": "Архитектура", "type": Question.Type.TEXT, "status": "inactive"},
        )

        self.assertEqual(grouped.status_code, 200)
        self.assertEqual(len(grouped.context["question_groups"]), 2)
        self.assertContains(grouped, "Базы данных")
        self.assertContains(grouped, "Информационные системы")
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.context["filtered_count"], 1)
        self.assertTrue(filtered.context["filters_active"])
        self.assertContains(filtered, "Архитектура информационной системы")
        self.assertNotContains(filtered, "Вопрос по базам данных")

    def test_teacher_selects_student_and_sees_results(self):
        self.client.login(username="teacher@test.local", password="pass12345")

        student_list = self.client.get(reverse("teacher_student_list"))
        detail = self.client.get(
            reverse("teacher_student_detail", args=[self.student.user_id])
        )

        self.assertEqual(student_list.status_code, 200)
        self.assertContains(student_list, self.student.full_name)
        self.assertContains(
            student_list,
            reverse("teacher_student_detail", args=[self.student.user_id]),
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Итоговый экзамен")
        self.assertContains(detail, "100%")

    def test_teacher_cannot_open_unrelated_student(self):
        unrelated_student = User.objects.create_user(
            email="unrelated@test.local",
            password="pass12345",
            full_name="Чужой студент",
            role=User.Role.STUDENT,
        )
        SubjectEnrollment.objects.create(
            subject=self.other_subject,
            student=unrelated_student,
        )
        self.client.login(username="teacher@test.local", password="pass12345")

        response = self.client.get(
            reverse("teacher_student_detail", args=[unrelated_student.user_id])
        )

        self.assertEqual(response.status_code, 404)


class DemoDataTests(TestCase):
    def test_seed_creates_rich_data_without_active_attempts(self):
        call_command("seed_demo_data", verbosity=0)

        self.assertEqual(User.objects.count(), 9)
        self.assertEqual(Subject.objects.count(), 6)
        self.assertEqual(SubjectEnrollment.objects.count(), 30)
        self.assertEqual(Exam.objects.count(), 7)
        self.assertEqual(Question.objects.count(), 44)
        self.assertEqual(ExamAttempt.objects.count(), 12)
        self.assertFalse(
            ExamAttempt.objects.filter(status=ExamAttempt.Status.IN_PROGRESS).exists()
        )
