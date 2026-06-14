from django import forms
from django.db import transaction

from .models import (
    CorrectChoiceKey,
    CorrectTextKey,
    Exam,
    ExamQuestion,
    Question,
    QuestionOption,
    Subject,
)


class ExamForm(forms.ModelForm):
    duration_minutes = forms.IntegerField(
        label="Продолжительность, минут",
        min_value=1,
        max_value=1440,
    )

    class Meta:
        model = Exam
        fields = (
            "subject",
            "title",
            "description",
            "duration_minutes",
            "attempts_limit",
            "available_from",
            "available_to",
            "randomize_questions",
            "show_answers_after",
            "is_published",
        )
        labels = {
            "subject": "Предмет",
            "title": "Название",
            "description": "Описание",
            "attempts_limit": "Количество попыток",
            "available_from": "Доступен с",
            "available_to": "Доступен до",
            "randomize_questions": "Перемешивать вопросы",
            "show_answers_after": "Показывать разбор после сдачи",
            "is_published": "Опубликовать экзамен",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "available_from": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
            "available_to": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
        }

    def __init__(self, *args, teacher, **kwargs):
        super().__init__(*args, **kwargs)
        subjects = Subject.objects.all() if teacher.is_admin_role or teacher.is_superuser else Subject.objects.filter(teacher=teacher)
        self.fields["subject"].queryset = subjects.order_by("title")
        self.fields["available_from"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["available_to"].input_formats = ["%Y-%m-%dT%H:%M"]
        if self.instance.pk:
            self.fields["duration_minutes"].initial = max(self.instance.time_limit_sec // 60, 1)

    def clean(self):
        cleaned = super().clean()
        available_from = cleaned.get("available_from")
        available_to = cleaned.get("available_to")
        if available_from and available_to and available_to <= available_from:
            self.add_error("available_to", "Дата окончания должна быть позже даты начала.")
        return cleaned

    def save(self, commit=True):
        exam = super().save(commit=False)
        exam.time_limit_sec = self.cleaned_data["duration_minutes"] * 60
        if commit:
            exam.save()
        return exam


class QuestionForm(forms.ModelForm):
    options_text = forms.CharField(
        label="Варианты ответа",
        required=False,
        help_text="Для вопроса с выбором: один вариант на строку.",
        widget=forms.Textarea(attrs={"rows": 5}),
    )
    correct_answer = forms.CharField(
        label="Правильный вариант",
        required=False,
        help_text="Введите один из вариантов точно так же, как в списке выше.",
    )
    accepted_answers = forms.CharField(
        label="Допустимые текстовые ответы",
        required=False,
        help_text="Для текстового вопроса: один допустимый ответ на строку.",
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    class Meta:
        model = Question
        fields = (
            "subject",
            "q_type",
            "question_text",
            "explanation",
            "difficulty",
            "is_active",
        )
        labels = {
            "subject": "Предмет",
            "q_type": "Тип вопроса",
            "question_text": "Текст вопроса",
            "explanation": "Пояснение после ответа",
            "difficulty": "Сложность",
            "is_active": "Вопрос активен",
        }
        widgets = {
            "question_text": forms.Textarea(attrs={"rows": 4}),
            "explanation": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, teacher, **kwargs):
        super().__init__(*args, **kwargs)
        subjects = Subject.objects.all() if teacher.is_admin_role or teacher.is_superuser else Subject.objects.filter(teacher=teacher)
        self.fields["subject"].queryset = subjects.order_by("title")
        if self.instance.pk:
            options = list(self.instance.options.order_by("option_id"))
            self.fields["options_text"].initial = "\n".join(option.option_text for option in options)
            correct_key = self.instance.correct_choice_keys.select_related("option").first()
            if correct_key:
                self.fields["correct_answer"].initial = correct_key.option.option_text
            self.fields["accepted_answers"].initial = "\n".join(
                self.instance.correct_text_keys.values_list("accepted_answer", flat=True)
            )

    def clean(self):
        cleaned = super().clean()
        q_type = cleaned.get("q_type")
        options = [line.strip() for line in cleaned.get("options_text", "").splitlines() if line.strip()]
        correct_answer = cleaned.get("correct_answer", "").strip()
        accepted_answers = [
            line.strip()
            for line in cleaned.get("accepted_answers", "").splitlines()
            if line.strip()
        ]

        if q_type == Question.Type.SINGLE_CHOICE:
            if len(options) < 2:
                self.add_error("options_text", "Добавьте минимум два варианта ответа.")
            if not correct_answer:
                self.add_error("correct_answer", "Укажите правильный вариант.")
            elif correct_answer.casefold() not in {option.casefold() for option in options}:
                self.add_error("correct_answer", "Правильный ответ должен совпадать с одним из вариантов.")
        elif q_type == Question.Type.TEXT and not accepted_answers:
            self.add_error("accepted_answers", "Добавьте минимум один допустимый ответ.")

        cleaned["parsed_options"] = options
        cleaned["parsed_answers"] = accepted_answers
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        question = super().save(commit=commit)
        if not commit:
            return question

        question.options.all().delete()
        question.correct_text_keys.all().delete()

        if question.q_type == Question.Type.SINGLE_CHOICE:
            correct_answer = self.cleaned_data["correct_answer"].strip().casefold()
            for text in self.cleaned_data["parsed_options"]:
                option = QuestionOption.objects.create(question=question, option_text=text)
                if text.casefold() == correct_answer:
                    CorrectChoiceKey.objects.create(question=question, option=option)
        else:
            for answer in self.cleaned_data["parsed_answers"]:
                CorrectTextKey.objects.create(question=question, accepted_answer=answer)
        return question


class ExamQuestionForm(forms.ModelForm):
    class Meta:
        model = ExamQuestion
        fields = ("question", "points", "question_order")
        labels = {
            "question": "Вопрос",
            "points": "Баллы",
            "question_order": "Порядок",
        }

    def __init__(self, *args, exam, **kwargs):
        super().__init__(*args, **kwargs)
        attached_ids = exam.exam_questions.values_list("question_id", flat=True)
        self.fields["question"].queryset = Question.objects.filter(
            subject=exam.subject,
            is_active=True,
        ).exclude(question_id__in=attached_ids).order_by("question_text")
        self.instance.exam = exam
