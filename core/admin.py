from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

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


class RoleFilteredAdminMixin:
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "teacher":
            kwargs["queryset"] = User.objects.filter(role=User.Role.TEACHER)
        elif db_field.name == "student":
            kwargs["queryset"] = User.objects.filter(role=User.Role.STUDENT)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = (
        "email",
        "full_name",
        "role",
        "is_active",
        "is_staff",
        "created_at",
    )
    list_filter = ("role", "is_active", "is_staff", "is_superuser")
    search_fields = ("email", "full_name")
    ordering = ("email",)
    list_editable = ("role", "is_active")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Личные данные", {"fields": ("full_name", "role", "username")}),
        (
            "Права доступа",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Даты", {"fields": ("last_login", "date_joined", "created_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "full_name",
                    "role",
                    "password1",
                    "password2",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )
    readonly_fields = ("last_login", "date_joined", "created_at")

    def save_model(self, request, obj, form, change):
        if obj.role in {User.Role.ADMIN, User.Role.TEACHER}:
            obj.is_staff = True
        if obj.role == User.Role.STUDENT and not obj.is_superuser:
            obj.is_staff = False
        super().save_model(request, obj, form, change)


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 2
    fields = ("option_text",)


class CorrectChoiceKeyInline(admin.TabularInline):
    model = CorrectChoiceKey
    extra = 1
    autocomplete_fields = ("option",)
    fields = ("option",)


class CorrectTextKeyInline(admin.TabularInline):
    model = CorrectTextKey
    extra = 1
    fields = ("accepted_answer",)


@admin.register(Subject)
class SubjectAdmin(RoleFilteredAdminMixin, admin.ModelAdmin):
    list_display = ("title", "teacher", "exam_count", "student_count", "created_at")
    list_filter = ("teacher",)
    search_fields = ("title", "description", "teacher__full_name", "teacher__email")
    autocomplete_fields = ("teacher",)
    readonly_fields = ("created_at",)

    @admin.display(description="Экзаменов")
    def exam_count(self, obj):
        return obj.exams.count()

    @admin.display(description="Студентов")
    def student_count(self, obj):
        return obj.enrollments.count()


@admin.register(SubjectEnrollment)
class SubjectEnrollmentAdmin(RoleFilteredAdminMixin, admin.ModelAdmin):
    list_display = ("subject", "student", "enrolled_at")
    list_filter = ("subject",)
    search_fields = ("subject__title", "student__full_name", "student__email")
    autocomplete_fields = ("subject", "student")
    readonly_fields = ("enrolled_at",)


class ExamQuestionInline(admin.TabularInline):
    model = ExamQuestion
    extra = 1
    autocomplete_fields = ("question",)
    fields = ("question_order", "question", "points")
    ordering = ("question_order",)


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "subject",
        "is_published",
        "question_count",
        "attempts_limit",
        "time_limit_min",
        "available_from",
        "available_to",
    )
    list_filter = ("is_published", "subject", "randomize_questions", "show_answers_after")
    search_fields = ("title", "description", "subject__title")
    autocomplete_fields = ("subject",)
    readonly_fields = ("created_at",)
    inlines = (ExamQuestionInline,)
    actions = ("publish_exams", "unpublish_exams")
    fieldsets = (
        ("Основное", {"fields": ("subject", "title", "description", "is_published")}),
        (
            "Параметры сдачи",
            {
                "fields": (
                    "time_limit_sec",
                    "attempts_limit",
                    "randomize_questions",
                    "show_answers_after",
                )
            },
        ),
        ("Период доступности", {"fields": ("available_from", "available_to")}),
        ("Служебное", {"fields": ("created_at",)}),
    )

    @admin.display(description="Вопросов")
    def question_count(self, obj):
        return obj.exam_questions.count()

    @admin.display(description="Лимит, мин")
    def time_limit_min(self, obj):
        return obj.time_limit_sec // 60

    @admin.action(description="Опубликовать выбранные экзамены")
    def publish_exams(self, request, queryset):
        updated = queryset.update(is_published=True)
        self.message_user(request, f"Опубликовано экзаменов: {updated}.")

    @admin.action(description="Снять выбранные экзамены с публикации")
    def unpublish_exams(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f"Снято с публикации экзаменов: {updated}.")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("short_text", "subject", "q_type", "difficulty", "is_active", "option_count")
    list_filter = ("subject", "q_type", "is_active", "difficulty")
    search_fields = ("question_text", "explanation", "subject__title")
    autocomplete_fields = ("subject",)
    readonly_fields = ("created_at",)
    inlines = (QuestionOptionInline, CorrectChoiceKeyInline, CorrectTextKeyInline)
    actions = ("activate_questions", "deactivate_questions")

    @admin.display(description="Вопрос")
    def short_text(self, obj):
        return obj.question_text[:100]

    @admin.display(description="Вариантов")
    def option_count(self, obj):
        return obj.options.count()

    @admin.action(description="Активировать выбранные вопросы")
    def activate_questions(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Активировано вопросов: {updated}.")

    @admin.action(description="Деактивировать выбранные вопросы")
    def deactivate_questions(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Деактивировано вопросов: {updated}.")


@admin.register(QuestionOption)
class QuestionOptionAdmin(admin.ModelAdmin):
    list_display = ("option_text", "question", "subject")
    list_filter = ("question__subject",)
    search_fields = ("option_text", "question__question_text")
    autocomplete_fields = ("question",)

    @admin.display(description="Предмет")
    def subject(self, obj):
        return obj.question.subject


@admin.register(ExamQuestion)
class ExamQuestionAdmin(admin.ModelAdmin):
    list_display = ("exam", "question", "points", "question_order")
    list_filter = ("exam__subject", "exam")
    search_fields = ("exam__title", "question__question_text")
    autocomplete_fields = ("exam", "question")


@admin.register(CorrectChoiceKey)
class CorrectChoiceKeyAdmin(admin.ModelAdmin):
    list_display = ("question", "option")
    list_filter = ("question__subject",)
    search_fields = ("question__question_text", "option__option_text")
    autocomplete_fields = ("question", "option")


@admin.register(CorrectTextKey)
class CorrectTextKeyAdmin(admin.ModelAdmin):
    list_display = ("question", "accepted_answer")
    list_filter = ("question__subject",)
    search_fields = ("question__question_text", "accepted_answer")
    autocomplete_fields = ("question",)


class AttemptAnswerInline(admin.TabularInline):
    model = AttemptAnswer
    extra = 0
    autocomplete_fields = ("question", "selected_option")
    fields = ("question", "selected_option", "answer_text", "score_awarded", "answered_at")
    readonly_fields = ("answered_at",)


@admin.register(ExamAttempt)
class ExamAttemptAdmin(RoleFilteredAdminMixin, admin.ModelAdmin):
    list_display = (
        "exam",
        "student",
        "status",
        "score_total",
        "score_max",
        "score_percent",
        "start_at",
        "end_at",
    )
    list_filter = ("status", "exam__subject", "exam")
    search_fields = ("exam__title", "student__full_name", "student__email")
    autocomplete_fields = ("exam", "student")
    readonly_fields = ("start_at",)
    inlines = (AttemptAnswerInline,)

    @admin.display(description="Процент")
    def score_percent(self, obj):
        if not obj.score_max:
            return "0%"
        return f"{obj.score_total / obj.score_max:.0%}"


@admin.register(AttemptAnswer)
class AttemptAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "selected_option", "score_awarded", "answered_at")
    list_filter = ("attempt__exam__subject", "attempt__exam")
    search_fields = ("attempt__student__full_name", "question__question_text", "answer_text")
    autocomplete_fields = ("attempt", "question", "selected_option")
    readonly_fields = ("answered_at",)


admin.site.site_header = "Администрирование системы экзаменов"
admin.site.site_title = "Admin | Экзамены"
admin.site.index_title = "Панель управления"
