from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email обязателен")
        email = self.normalize_email(email)
        extra_fields.setdefault("username", email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Суперпользователь должен иметь is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Суперпользователь должен иметь is_superuser=True")

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Администратор"
        TEACHER = "teacher", "Преподаватель"
        STUDENT = "student", "Студент"

    user_id = models.BigAutoField(primary_key=True)
    username = models.CharField(max_length=150, unique=True, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    full_name = models.TextField()
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "users"
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def is_teacher_role(self):
        return self.role == self.Role.TEACHER

    @property
    def is_student_role(self):
        return self.role == self.Role.STUDENT

    def get_full_name(self):
        return self.full_name

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"


class Subject(models.Model):
    subject_id = models.BigAutoField(primary_key=True)
    title = models.TextField()
    description = models.TextField(blank=True, null=True)
    teacher = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="teaching_subjects",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "subjects"
        verbose_name = "предмет"
        verbose_name_plural = "предметы"
        indexes = [
            models.Index(fields=["teacher"], name="idx_subjects_teacher"),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.teacher_id and self.teacher.role != User.Role.TEACHER:
            raise ValidationError({"teacher": "Предмет можно назначить только преподавателю."})


class SubjectEnrollment(models.Model):
    enrollment_id = models.BigAutoField(primary_key=True)
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    enrolled_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "subject_enrollments"
        verbose_name = "запись на предмет"
        verbose_name_plural = "записи на предметы"
        constraints = [
            models.UniqueConstraint(
                fields=["subject", "student"],
                name="uq_subject_enrollments_subject_student",
            ),
        ]
        indexes = [
            models.Index(fields=["student"], name="idx_enrollments_student"),
        ]

    def __str__(self):
        return f"{self.student} -> {self.subject}"

    def clean(self):
        super().clean()
        if self.student_id and self.student.role != User.Role.STUDENT:
            raise ValidationError({"student": "На предмет можно записать только студента."})


class Exam(models.Model):
    exam_id = models.BigAutoField(primary_key=True)
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="exams",
    )
    title = models.TextField()
    description = models.TextField(blank=True, null=True)
    time_limit_sec = models.PositiveIntegerField()
    attempts_limit = models.PositiveIntegerField(default=1)
    randomize_questions = models.BooleanField(default=False)
    show_answers_after = models.BooleanField(default=True)
    available_from = models.DateTimeField(blank=True, null=True)
    available_to = models.DateTimeField(blank=True, null=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "exams"
        verbose_name = "экзамен"
        verbose_name_plural = "экзамены"
        indexes = [
            models.Index(fields=["subject"], name="idx_exams_subject"),
            models.Index(fields=["is_published"], name="idx_exams_published"),
        ]

    def __str__(self):
        return f"{self.subject}: {self.title}"


class Question(models.Model):
    class Type(models.TextChoices):
        SINGLE_CHOICE = "single_choice", "Один вариант"
        TEXT = "text", "Текстовый ответ"

    question_id = models.BigAutoField(primary_key=True)
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    q_type = models.CharField(max_length=20, choices=Type.choices)
    question_text = models.TextField()
    explanation = models.TextField(blank=True, null=True)
    difficulty = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "question_bank"
        verbose_name = "вопрос"
        verbose_name_plural = "банк вопросов"
        indexes = [
            models.Index(fields=["subject"], name="idx_question_bank_subject"),
        ]

    def __str__(self):
        return self.question_text[:80]


class ExamQuestion(models.Model):
    exam_question_id = models.BigAutoField(primary_key=True)
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="exam_questions",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.PROTECT,
        related_name="exam_questions",
    )
    points = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    question_order = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "exam_questions"
        verbose_name = "вопрос экзамена"
        verbose_name_plural = "вопросы экзамена"
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "question"],
                name="uq_exam_questions_exam_question",
            ),
        ]
        indexes = [
            models.Index(
                fields=["exam", "question_order"],
                name="idx_exam_questions_order",
            ),
        ]
        ordering = ["exam", "question_order"]

    def __str__(self):
        return f"{self.exam}: вопрос {self.question_order}"

    def clean(self):
        super().clean()
        if (
            self.exam_id
            and self.question_id
            and self.exam.subject_id != self.question.subject_id
        ):
            raise ValidationError(
                {"question": "В экзамен можно добавить только вопрос из того же предмета."}
            )


class QuestionOption(models.Model):
    option_id = models.BigAutoField(primary_key=True)
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options",
    )
    option_text = models.TextField()

    class Meta:
        db_table = "question_options"
        verbose_name = "вариант ответа"
        verbose_name_plural = "варианты ответа"
        indexes = [
            models.Index(fields=["question"], name="idx_options_question"),
        ]

    def __str__(self):
        return self.option_text[:80]


class CorrectChoiceKey(models.Model):
    correct_choice_key_id = models.BigAutoField(primary_key=True)
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="correct_choice_keys",
    )
    option = models.ForeignKey(
        QuestionOption,
        on_delete=models.CASCADE,
        related_name="correct_choice_keys",
    )

    class Meta:
        db_table = "correct_choice_keys"
        verbose_name = "ключ тестового ответа"
        verbose_name_plural = "ключи тестовых ответов"
        constraints = [
            models.UniqueConstraint(
                fields=["question", "option"],
                name="uq_correct_choice_keys_question_option",
            ),
        ]

    def __str__(self):
        return f"{self.question} -> {self.option}"

    def clean(self):
        super().clean()
        if (
            self.question_id
            and self.option_id
            and self.question_id != self.option.question_id
        ):
            raise ValidationError(
                {"option": "Правильный вариант должен относиться к выбранному вопросу."}
            )


class CorrectTextKey(models.Model):
    key_id = models.BigAutoField(primary_key=True)
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="correct_text_keys",
    )
    accepted_answer = models.TextField()

    class Meta:
        db_table = "correct_text_keys"
        verbose_name = "ключ текстового ответа"
        verbose_name_plural = "ключи текстовых ответов"

    def __str__(self):
        return self.accepted_answer[:80]


class ExamAttempt(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "В процессе"
        SUBMITTED = "submitted", "Завершена"
        EXPIRED = "expired", "Просрочена"
        CANCELLED = "cancelled", "Отменена"

    attempt_id = models.BigAutoField(primary_key=True)
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="exam_attempts",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
    )
    start_at = models.DateTimeField(default=timezone.now)
    end_at = models.DateTimeField(blank=True, null=True)
    time_limit_sec = models.PositiveIntegerField()
    score_total = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    score_max = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    class Meta:
        db_table = "exam_attempts"
        verbose_name = "попытка экзамена"
        verbose_name_plural = "попытки экзаменов"
        indexes = [
            models.Index(fields=["student", "-start_at"], name="idx_attempts_student"),
            models.Index(fields=["exam", "student"], name="idx_attempts_exam_student"),
        ]

    def __str__(self):
        return f"{self.student} - {self.exam} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        if self.student_id and self.student.role != User.Role.STUDENT:
            raise ValidationError({"student": "Попытку экзамена может иметь только студент."})


class AttemptAnswer(models.Model):
    attempt_answer_id = models.BigAutoField(primary_key=True)
    attempt = models.ForeignKey(
        ExamAttempt,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.PROTECT,
        related_name="attempt_answers",
    )
    selected_option = models.ForeignKey(
        QuestionOption,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="attempt_answers",
    )
    answer_text = models.TextField(blank=True, null=True)
    score_awarded = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    answered_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "attempt_answers"
        verbose_name = "ответ в попытке"
        verbose_name_plural = "ответы в попытках"
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"],
                name="uq_attempt_answers_attempt_question",
            ),
        ]
        indexes = [
            models.Index(fields=["question"], name="idx_attempt_answers_question"),
        ]

    def __str__(self):
        return f"{self.attempt}: {self.question}"

    def clean(self):
        super().clean()
        if (
            self.attempt_id
            and self.question_id
            and not self.attempt.exam.exam_questions.filter(question_id=self.question_id).exists()
        ):
            raise ValidationError(
                {"question": "Ответ можно сохранить только на вопрос из экзамена попытки."}
            )
        if (
            self.question_id
            and self.selected_option_id
            and self.selected_option.question_id != self.question_id
        ):
            raise ValidationError(
                {"selected_option": "Выбранный вариант должен относиться к этому вопросу."}
            )
