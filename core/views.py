import re
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ExamForm, ExamQuestionForm, QuestionForm

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


COMPLETED_ATTEMPT_STATUSES = [
    ExamAttempt.Status.SUBMITTED,
    ExamAttempt.Status.EXPIRED,
]


def _profile_context(request):
    full_name = request.user.full_name or request.user.email
    initials = "".join(part[:1] for part in full_name.split()[:2]).upper()
    return {
        "profile_name": full_name,
        "profile_initials": initials or "П",
        "profile_role": request.user.get_role_display(),
    }


def _student_required(user):
    if not user.is_student_role:
        raise PermissionDenied("Раздел доступен только студентам.")


def _teacher_required(user):
    if not (user.is_teacher_role or user.is_admin_role):
        raise PermissionDenied("Раздел доступен только преподавателям.")


def _teacher_exam_queryset(user):
    queryset = Exam.objects.select_related("subject", "subject__teacher")
    if user.is_admin_role or user.is_superuser:
        return queryset
    return queryset.filter(subject__teacher=user)


def _teacher_subject_queryset(user):
    if user.is_admin_role or user.is_superuser:
        return Subject.objects.all()
    return Subject.objects.filter(teacher=user)


def _student_subject_ids(student):
    return SubjectEnrollment.objects.filter(student=student).values_list(
        "subject_id",
        flat=True,
    )


def _available_state(exam, now=None):
    now = now or timezone.now()
    if exam.available_from and exam.available_from > now:
        return "not_started"
    if exam.available_to and exam.available_to < now:
        return "ended"
    return "available"


def _format_minutes(seconds):
    return max(seconds // 60, 1)


def _score_percent(score_total, score_max):
    if not score_max:
        return 0
    return round((score_total / score_max) * 100)


def _attempt_duration_minutes(attempt):
    if not attempt.end_at:
        return None
    duration = attempt.end_at - attempt.start_at
    return max(round(duration.total_seconds() / 60), 1)


def _normalize_text(value):
    normalized = (value or "").strip().lower().replace("ё", "е")
    normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def _remaining_seconds(attempt):
    elapsed = (timezone.now() - attempt.start_at).total_seconds()
    return max(attempt.time_limit_sec - int(elapsed), 0)


def _is_attempt_expired(attempt):
    return _remaining_seconds(attempt) <= 0


def _expire_stale_attempts(attempts):
    for attempt in attempts:
        if attempt.status == ExamAttempt.Status.IN_PROGRESS and _is_attempt_expired(attempt):
            _expire_attempt(attempt)
            attempt.refresh_from_db()


def _student_exams(student):
    subject_ids = list(_student_subject_ids(student))
    attempts = ExamAttempt.objects.filter(student=student).order_by("-start_at")
    _expire_stale_attempts(attempts)
    attempts_prefetch = Prefetch("attempts", queryset=attempts, to_attr="student_attempts")

    return (
        Exam.objects.filter(subject_id__in=subject_ids, is_published=True)
        .select_related("subject", "subject__teacher")
        .annotate(question_count=Count("exam_questions", distinct=True))
        .prefetch_related(attempts_prefetch)
        .order_by("available_to", "title")
    )


def _exam_row(exam):
    now = timezone.now()
    attempts = list(getattr(exam, "student_attempts", []))
    completed_attempts = [
        attempt for attempt in attempts if attempt.status in COMPLETED_ATTEMPT_STATUSES
    ]
    in_progress = next(
        (
            attempt
            for attempt in attempts
            if attempt.status == ExamAttempt.Status.IN_PROGRESS
        ),
        None,
    )
    latest_completed = completed_attempts[0] if completed_attempts else None
    attempts_used = len(
        [
            attempt
            for attempt in attempts
            if attempt.status != ExamAttempt.Status.CANCELLED
        ]
    )
    attempts_left = max(exam.attempts_limit - attempts_used, 0)
    availability = _available_state(exam, now)

    if latest_completed and attempts_left == 0:
        status_label = (
            "Время истекло"
            if latest_completed.status == ExamAttempt.Status.EXPIRED
            else "Сдан"
        )
        status_class = (
            "warning"
            if latest_completed.status == ExamAttempt.Status.EXPIRED
            else "success"
        )
        action_label = "Открыть"
        action_url = "attempt_results"
        action_attempt = latest_completed
        can_start = False
    elif in_progress:
        status_label = "В процессе"
        status_class = "warning"
        action_label = "Продолжить"
        action_url = "exam_taking"
        action_attempt = in_progress
        can_start = False
    elif availability == "not_started":
        status_label = "Не начат"
        status_class = ""
        action_label = "Недоступен"
        action_url = ""
        action_attempt = None
        can_start = False
    elif availability == "ended":
        status_label = "Завершён"
        status_class = "danger"
        action_label = "Недоступен"
        action_url = ""
        action_attempt = None
        can_start = False
    elif attempts_left <= 0:
        status_label = "Попытки исчерпаны"
        status_class = "danger"
        action_label = "Открыть"
        action_url = "attempt_results" if latest_completed else ""
        action_attempt = latest_completed
        can_start = False
    else:
        status_label = "Доступен"
        status_class = "info"
        action_label = "Начать"
        action_url = "start_exam"
        action_attempt = None
        can_start = True

    return {
        "exam": exam,
        "status_label": status_label,
        "status_class": status_class,
        "attempts_used": attempts_used,
        "attempts_left": attempts_left,
        "latest_completed": latest_completed,
        "in_progress": in_progress,
        "action_label": action_label,
        "action_url": action_url,
        "action_attempt": action_attempt,
        "can_start": can_start,
        "is_available": availability == "available",
        "availability": availability,
        "time_limit_min": _format_minutes(exam.time_limit_sec),
        "teacher": exam.subject.teacher,
    }


def _get_student_attempt(student, attempt_id):
    return get_object_or_404(
        ExamAttempt.objects.select_related("exam", "exam__subject"),
        attempt_id=attempt_id,
        student=student,
    )


def _exam_questions(exam):
    return (
        ExamQuestion.objects.filter(exam=exam)
        .select_related("question")
        .prefetch_related(
            "question__options",
            "question__correct_choice_keys",
            "question__correct_text_keys",
        )
        .order_by("question_order")
    )


def _attempt_questions(attempt):
    return _exam_questions(attempt.exam)


def _save_attempt_answers(request, attempt):
    existing = {
        answer.question_id: answer
        for answer in AttemptAnswer.objects.filter(attempt=attempt)
    }

    for exam_question in _attempt_questions(attempt):
        question = exam_question.question
        selected_option = None
        answer_text = ""

        if question.q_type == Question.Type.SINGLE_CHOICE:
            option_id = request.POST.get(f"choice_{question.question_id}")
            if option_id:
                selected_option = QuestionOption.objects.filter(
                    option_id=option_id,
                    question=question,
                ).first()
        else:
            answer_text = request.POST.get(f"text_{question.question_id}", "")

        has_answer = bool(selected_option or answer_text.strip())
        answer = existing.get(question.question_id)

        if not has_answer and not answer:
            continue

        if not answer:
            answer = AttemptAnswer(attempt=attempt, question=question)

        answer.selected_option = selected_option
        answer.answer_text = answer_text
        answer.answered_at = timezone.now()
        answer.full_clean()
        answer.save()


def _answer_score(question, answer, points, choice_keys, text_keys):
    if not answer:
        return Decimal("0")

    if question.q_type == Question.Type.SINGLE_CHOICE:
        correct_options = choice_keys.get(question.question_id, set())
        if answer.selected_option_id in correct_options:
            return points
        return Decimal("0")

    accepted_answers = text_keys.get(question.question_id, set())
    if _normalize_text(answer.answer_text) in accepted_answers:
        return points
    return Decimal("0")


def _grade_attempt(attempt, status=ExamAttempt.Status.SUBMITTED):
    if attempt.status in COMPLETED_ATTEMPT_STATUSES:
        return

    exam_questions = list(_attempt_questions(attempt))
    answers = {
        answer.question_id: answer
        for answer in AttemptAnswer.objects.filter(attempt=attempt).select_related(
            "selected_option",
            "question",
        )
    }
    choice_keys = {}
    for key in CorrectChoiceKey.objects.filter(
        question_id__in=[item.question_id for item in exam_questions]
    ):
        choice_keys.setdefault(key.question_id, set()).add(key.option_id)
    text_keys = {}
    for key in CorrectTextKey.objects.filter(
        question_id__in=[item.question_id for item in exam_questions]
    ):
        text_keys.setdefault(key.question_id, set()).add(_normalize_text(key.accepted_answer))

    score_total = Decimal("0")
    score_max = Decimal("0")

    for exam_question in exam_questions:
        points = exam_question.points
        question = exam_question.question
        answer = answers.get(question.question_id)
        score_max += points

        if not answer:
            continue

        awarded = _answer_score(question, answer, points, choice_keys, text_keys)

        answer.score_awarded = awarded
        answer.save(update_fields=["score_awarded"])
        score_total += awarded

    attempt.score_total = score_total
    attempt.score_max = score_max
    attempt.status = status
    attempt.end_at = timezone.now()
    attempt.save(update_fields=["score_total", "score_max", "status", "end_at"])


def _expire_attempt(attempt):
    _grade_attempt(attempt, status=ExamAttempt.Status.EXPIRED)


@login_required
def home(request):
    user = request.user

    if user.is_superuser or user.is_admin_role:
        return redirect("admin:index")
    if user.is_teacher_role:
        return redirect("teacher_dashboard")
    if user.is_student_role:
        return redirect("student_dashboard")

    raise PermissionDenied("Для пользователя не назначена роль.")


@login_required
def student_dashboard(request):
    _student_required(request.user)

    rows = [_exam_row(exam) for exam in _student_exams(request.user)]
    completed_attempts = ExamAttempt.objects.filter(
        student=request.user,
        status__in=COMPLETED_ATTEMPT_STATUSES,
    ).select_related("exam", "exam__subject")
    total_score = sum((attempt.score_total for attempt in completed_attempts), Decimal("0"))
    total_max = sum((attempt.score_max for attempt in completed_attempts), Decimal("0"))
    nearest_exam = next((row for row in rows if row["is_available"] and row["attempts_left"]), None)
    latest_result = completed_attempts.order_by("-end_at", "-start_at").first()

    context = {
        **_profile_context(request),
        "rows": rows,
        "nearest_exam": nearest_exam,
        "latest_result": latest_result,
        "subject_count": SubjectEnrollment.objects.filter(student=request.user).count(),
        "available_count": sum(1 for row in rows if row["is_available"] and row["attempts_left"]),
        "submitted_count": completed_attempts.count(),
        "average_percent": _score_percent(total_score, total_max),
    }
    return render(request, "core/student_dashboard.html", context)


@login_required
def exam_selection(request):
    _student_required(request.user)

    context = {
        **_profile_context(request),
        "rows": [_exam_row(exam) for exam in _student_exams(request.user)],
    }
    return render(request, "core/exam_selection.html", context)


@login_required
def start_exam(request, exam_id):
    _student_required(request.user)
    if request.method != "POST":
        return redirect("exam_selection")

    exam = get_object_or_404(
        Exam.objects.annotate(question_count=Count("exam_questions", distinct=True)),
        exam_id=exam_id,
        is_published=True,
        subject_id__in=_student_subject_ids(request.user),
    )
    if _available_state(exam) != "available":
        messages.error(request, "Экзамен сейчас недоступен.")
        return redirect("exam_selection")
    if not exam.question_count:
        messages.error(request, "В экзамене пока нет вопросов.")
        return redirect("exam_selection")

    in_progress = ExamAttempt.objects.filter(
        exam=exam,
        student=request.user,
        status=ExamAttempt.Status.IN_PROGRESS,
    ).first()
    if in_progress:
        return redirect("exam_taking", attempt_id=in_progress.attempt_id)

    attempts_used = ExamAttempt.objects.filter(exam=exam, student=request.user).exclude(
        status=ExamAttempt.Status.CANCELLED
    ).count()
    if attempts_used >= exam.attempts_limit:
        messages.error(request, "Лимит попыток по этому экзамену исчерпан.")
        return redirect("exam_selection")

    score_max = (
        ExamQuestion.objects.filter(exam=exam)
        .values_list("points", flat=True)
    )
    attempt = ExamAttempt.objects.create(
        exam=exam,
        student=request.user,
        time_limit_sec=exam.time_limit_sec,
        score_max=sum(score_max, Decimal("0")),
    )
    return redirect("exam_taking", attempt_id=attempt.attempt_id)


@login_required
def exam_taking(request, attempt_id):
    _student_required(request.user)
    attempt = _get_student_attempt(request.user, attempt_id)
    if attempt.status in COMPLETED_ATTEMPT_STATUSES:
        return redirect("attempt_results", attempt_id=attempt.attempt_id)

    if request.method == "POST":
        _save_attempt_answers(request, attempt)
        if request.POST.get("action") == "submit":
            if _is_attempt_expired(attempt):
                _expire_attempt(attempt)
            else:
                _grade_attempt(attempt)
            return redirect("attempt_results", attempt_id=attempt.attempt_id)
        if _is_attempt_expired(attempt):
            _expire_attempt(attempt)
            messages.warning(request, "Время экзамена истекло. Попытка завершена автоматически.")
            return redirect("attempt_results", attempt_id=attempt.attempt_id)
        messages.success(request, "Ответы сохранены.")
        return redirect("exam_taking", attempt_id=attempt.attempt_id)

    if _is_attempt_expired(attempt):
        _expire_attempt(attempt)
        messages.warning(request, "Время экзамена истекло. Попытка завершена автоматически.")
        return redirect("attempt_results", attempt_id=attempt.attempt_id)

    answers = {
        answer.question_id: answer
        for answer in AttemptAnswer.objects.filter(attempt=attempt)
    }
    questions = []
    answered_count = 0
    for exam_question in _attempt_questions(attempt):
        answer = answers.get(exam_question.question_id)
        answered = bool(answer and (answer.selected_option_id or answer.answer_text))
        if answered:
            answered_count += 1
        questions.append(
            {
                "exam_question": exam_question,
                "answer": answer,
                "answered": answered,
            }
        )

    total_questions = len(questions)
    remaining_seconds = _remaining_seconds(attempt)
    progress = 0 if not total_questions else round(answered_count / total_questions * 100)

    context = {
        **_profile_context(request),
        "attempt": attempt,
        "questions": questions,
        "answered_count": answered_count,
        "total_questions": total_questions,
        "remaining_minutes": remaining_seconds // 60,
        "remaining_seconds": remaining_seconds % 60,
        "remaining_total_seconds": remaining_seconds,
        "progress": progress,
    }
    return render(request, "core/exam_taking.html", context)


@login_required
def results(request):
    _student_required(request.user)
    attempts = list(
        ExamAttempt.objects.filter(
            student=request.user,
            status__in=COMPLETED_ATTEMPT_STATUSES,
        )
        .select_related("exam", "exam__subject", "exam__subject__teacher")
        .order_by("-end_at", "-start_at")
    )
    result_rows = [
        {
            "attempt": attempt,
            "score_percent": _score_percent(attempt.score_total, attempt.score_max),
            "duration_minutes": _attempt_duration_minutes(attempt),
        }
        for attempt in attempts
    ]

    context = {
        **_profile_context(request),
        "result_rows": result_rows,
    }
    return render(request, "core/result_list.html", context)


@login_required
def attempt_results(request, attempt_id):
    _student_required(request.user)
    attempt = _get_student_attempt(request.user, attempt_id)
    if attempt.status == ExamAttempt.Status.IN_PROGRESS and _is_attempt_expired(attempt):
        _expire_attempt(attempt)
        attempt.refresh_from_db()

    if attempt.status not in COMPLETED_ATTEMPT_STATUSES:
        return redirect("exam_taking", attempt_id=attempt.attempt_id)

    answers = {
        answer.question_id: answer
        for answer in AttemptAnswer.objects.filter(attempt=attempt).select_related(
            "question",
            "selected_option",
        )
    }
    question_results = []
    for exam_question in _attempt_questions(attempt):
        question_results.append(
            {
                "exam_question": exam_question,
                "answer": answers.get(exam_question.question_id),
                "is_correct": bool(
                    answers.get(exam_question.question_id)
                    and answers[exam_question.question_id].score_awarded
                    == exam_question.points
                ),
            }
        )

    context = {
        **_profile_context(request),
        "attempt": attempt,
        "question_results": question_results,
        "score_percent": _score_percent(attempt.score_total, attempt.score_max),
        "time_limit_min": _format_minutes(attempt.time_limit_sec),
    }
    return render(request, "core/results.html", context)


@login_required
def teacher_dashboard(request):
    _teacher_required(request.user)

    teacher_exams = _teacher_exam_queryset(request.user).annotate(
        question_count=Count("exam_questions", distinct=True)
    ).order_by("subject__title", "title")
    attempts = (
        ExamAttempt.objects.filter(exam__in=teacher_exams)
        .select_related("exam", "exam__subject", "student")
        .order_by("-start_at")
    )
    completed_attempts = attempts.filter(
        status__in=COMPLETED_ATTEMPT_STATUSES
    )
    total_score = sum((attempt.score_total for attempt in completed_attempts), Decimal("0"))
    total_max = sum((attempt.score_max for attempt in completed_attempts), Decimal("0"))

    exam_rows = []
    for exam in teacher_exams:
        exam_attempts = [attempt for attempt in attempts if attempt.exam_id == exam.exam_id]
        completed = [
            attempt
            for attempt in exam_attempts
            if attempt.status in COMPLETED_ATTEMPT_STATUSES
        ]
        total_exam_score = sum((attempt.score_total for attempt in completed), Decimal("0"))
        total_exam_max = sum((attempt.score_max for attempt in completed), Decimal("0"))
        exam_rows.append(
            {
                "exam": exam,
                "attempt_count": len(exam_attempts),
                "completed_count": len(completed),
                "average_percent": _score_percent(total_exam_score, total_exam_max),
                "time_limit_min": _format_minutes(exam.time_limit_sec),
            }
        )

    context = {
        **_profile_context(request),
        "exam_rows": exam_rows,
        "latest_attempts": attempts[:5],
        "subject_count": teacher_exams.values("subject_id").distinct().count(),
        "exam_count": teacher_exams.count(),
        "attempt_count": attempts.count(),
        "average_percent": _score_percent(total_score, total_max),
    }
    return render(request, "core/teacher_dashboard.html", context)


@login_required
def teacher_exam_detail(request, exam_id):
    _teacher_required(request.user)
    exam = get_object_or_404(
        _teacher_exam_queryset(request.user).annotate(
            question_count=Count("exam_questions", distinct=True)
        ),
        exam_id=exam_id,
    )
    attempts = list(
        ExamAttempt.objects.filter(exam=exam)
        .select_related("student")
        .order_by("-start_at")
    )
    completed_attempts = [
        attempt
        for attempt in attempts
        if attempt.status in COMPLETED_ATTEMPT_STATUSES
    ]
    total_score = sum((attempt.score_total for attempt in completed_attempts), Decimal("0"))
    total_max = sum((attempt.score_max for attempt in completed_attempts), Decimal("0"))

    attempt_rows = [
        {
            "attempt": attempt,
            "score_percent": _score_percent(attempt.score_total, attempt.score_max),
            "duration_min": _attempt_duration_minutes(attempt),
        }
        for attempt in attempts
    ]

    answer_counts = {}
    awarded_scores = {}
    for answer in AttemptAnswer.objects.filter(attempt__exam=exam):
        answer_counts[answer.question_id] = answer_counts.get(answer.question_id, 0) + 1
        awarded_scores[answer.question_id] = (
            awarded_scores.get(answer.question_id, Decimal("0")) + answer.score_awarded
        )

    question_rows = []
    for exam_question in _exam_questions(exam):
        answer_count = answer_counts.get(exam_question.question_id, 0)
        max_score = exam_question.points * answer_count
        question_rows.append(
            {
                "exam_question": exam_question,
                "answer_count": answer_count,
                "average_percent": _score_percent(
                    awarded_scores.get(exam_question.question_id, Decimal("0")),
                    max_score,
                ),
            }
        )

    context = {
        **_profile_context(request),
        "exam": exam,
        "attempt_rows": attempt_rows,
        "question_rows": question_rows,
        "attempt_count": len(attempts),
        "completed_count": len(completed_attempts),
        "average_percent": _score_percent(total_score, total_max),
        "time_limit_min": _format_minutes(exam.time_limit_sec),
    }
    return render(request, "core/teacher_exam_detail.html", context)


@login_required
def teacher_exam_create(request):
    _teacher_required(request.user)
    form = ExamForm(request.POST or None, teacher=request.user)
    if request.method == "POST" and form.is_valid():
        exam = form.save()
        messages.success(request, "Экзамен создан. Теперь добавьте к нему вопросы.")
        return redirect("teacher_exam_questions", exam_id=exam.exam_id)
    return render(
        request,
        "core/teacher_exam_form.html",
        {**_profile_context(request), "form": form, "exam": None},
    )


@login_required
def teacher_exam_edit(request, exam_id):
    _teacher_required(request.user)
    exam = get_object_or_404(_teacher_exam_queryset(request.user), exam_id=exam_id)
    form = ExamForm(request.POST or None, instance=exam, teacher=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Настройки экзамена сохранены.")
        return redirect("teacher_exam_detail", exam_id=exam.exam_id)
    return render(
        request,
        "core/teacher_exam_form.html",
        {**_profile_context(request), "form": form, "exam": exam},
    )


@login_required
def teacher_exam_delete(request, exam_id):
    _teacher_required(request.user)
    exam = get_object_or_404(_teacher_exam_queryset(request.user), exam_id=exam_id)
    if request.method == "POST":
        if exam.attempts.exists():
            messages.error(request, "Экзамен с попытками студентов удалить нельзя. Снимите его с публикации.")
        else:
            exam.delete()
            messages.success(request, "Экзамен удалён.")
        return redirect("teacher_dashboard")
    return redirect("teacher_exam_edit", exam_id=exam.exam_id)


@login_required
def teacher_exam_questions(request, exam_id):
    _teacher_required(request.user)
    exam = get_object_or_404(
        _teacher_exam_queryset(request.user).select_related("subject"),
        exam_id=exam_id,
    )
    form = ExamQuestionForm(request.POST or None, exam=exam)
    if request.method == "POST" and form.is_valid():
        exam_question = form.save(commit=False)
        exam_question.exam = exam
        exam_question.full_clean()
        exam_question.save()
        messages.success(request, "Вопрос добавлен в экзамен.")
        return redirect("teacher_exam_questions", exam_id=exam.exam_id)

    attached_questions = _exam_questions(exam)
    return render(
        request,
        "core/teacher_exam_questions.html",
        {
            **_profile_context(request),
            "exam": exam,
            "form": form,
            "attached_questions": attached_questions,
        },
    )


@login_required
def teacher_exam_question_remove(request, exam_id, exam_question_id):
    _teacher_required(request.user)
    exam = get_object_or_404(_teacher_exam_queryset(request.user), exam_id=exam_id)
    exam_question = get_object_or_404(
        ExamQuestion,
        exam=exam,
        exam_question_id=exam_question_id,
    )
    if request.method == "POST":
        exam_question.delete()
        messages.success(request, "Вопрос удалён из экзамена.")
    return redirect("teacher_exam_questions", exam_id=exam.exam_id)


@login_required
def teacher_question_list(request):
    _teacher_required(request.user)
    questions = (
        Question.objects.filter(subject__in=_teacher_subject_queryset(request.user))
        .select_related("subject")
        .annotate(exam_count=Count("exam_questions", distinct=True))
        .order_by("subject__title", "question_text")
    )
    return render(
        request,
        "core/teacher_question_list.html",
        {**_profile_context(request), "questions": questions},
    )


@login_required
def teacher_question_create(request):
    _teacher_required(request.user)
    form = QuestionForm(request.POST or None, teacher=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Вопрос добавлен в банк вопросов.")
        return redirect("teacher_question_list")
    return render(
        request,
        "core/teacher_question_form.html",
        {**_profile_context(request), "form": form, "question": None},
    )


@login_required
def teacher_question_edit(request, question_id):
    _teacher_required(request.user)
    question = get_object_or_404(
        Question.objects.filter(subject__in=_teacher_subject_queryset(request.user)),
        question_id=question_id,
    )
    form = QuestionForm(request.POST or None, instance=question, teacher=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Вопрос сохранён.")
        return redirect("teacher_question_list")
    return render(
        request,
        "core/teacher_question_form.html",
        {**_profile_context(request), "form": form, "question": question},
    )


@login_required
def teacher_student_list(request):
    _teacher_required(request.user)
    subjects = _teacher_subject_queryset(request.user)
    students = list(
        User.objects.filter(role=User.Role.STUDENT)
        .filter(Q(enrollments__subject__in=subjects) | Q(exam_attempts__exam__subject__in=subjects))
        .distinct()
        .order_by("full_name", "email")
    )
    completed_attempts = list(
        ExamAttempt.objects.filter(
            student__in=students,
            exam__subject__in=subjects,
            status__in=COMPLETED_ATTEMPT_STATUSES,
        ).select_related("student")
    )
    rows = []
    for student in students:
        attempts = [attempt for attempt in completed_attempts if attempt.student_id == student.user_id]
        score_total = sum((attempt.score_total for attempt in attempts), Decimal("0"))
        score_max = sum((attempt.score_max for attempt in attempts), Decimal("0"))
        rows.append(
            {
                "student": student,
                "completed_count": len(attempts),
                "average_percent": _score_percent(score_total, score_max),
            }
        )
    return render(
        request,
        "core/teacher_student_list.html",
        {**_profile_context(request), "student_rows": rows},
    )


@login_required
def teacher_student_detail(request, student_id):
    _teacher_required(request.user)
    subjects = _teacher_subject_queryset(request.user)
    student = get_object_or_404(
        User.objects.filter(role=User.Role.STUDENT)
        .filter(Q(enrollments__subject__in=subjects) | Q(exam_attempts__exam__subject__in=subjects))
        .distinct(),
        user_id=student_id,
    )
    attempts = list(
        ExamAttempt.objects.filter(
            student=student,
            exam__subject__in=subjects,
            status__in=COMPLETED_ATTEMPT_STATUSES,
        )
        .select_related("exam", "exam__subject")
        .order_by("-end_at", "-start_at")
    )
    result_rows = [
        {
            "attempt": attempt,
            "score_percent": _score_percent(attempt.score_total, attempt.score_max),
            "duration_minutes": _attempt_duration_minutes(attempt),
        }
        for attempt in attempts
    ]
    total_score = sum((attempt.score_total for attempt in attempts), Decimal("0"))
    total_max = sum((attempt.score_max for attempt in attempts), Decimal("0"))
    return render(
        request,
        "core/teacher_student_detail.html",
        {
            **_profile_context(request),
            "student": student,
            "result_rows": result_rows,
            "average_percent": _score_percent(total_score, total_max),
        },
    )
