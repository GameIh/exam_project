"""
URL configuration for exam_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from core import views

urlpatterns = [
    path("", views.home, name="home"),
    path("student/", views.student_dashboard, name="student_dashboard"),
    path("exams/", views.exam_selection, name="exam_selection"),
    path("exams/<int:exam_id>/start/", views.start_exam, name="start_exam"),
    path("attempts/<int:attempt_id>/", views.exam_taking, name="exam_taking"),
    path("attempts/<int:attempt_id>/results/", views.attempt_results, name="attempt_results"),
    path("results/", views.results, name="results"),
    path("teacher/", views.teacher_dashboard, name="teacher_dashboard"),
    path("teacher/exams/new/", views.teacher_exam_create, name="teacher_exam_create"),
    path("teacher/exams/<int:exam_id>/", views.teacher_exam_detail, name="teacher_exam_detail"),
    path("teacher/exams/<int:exam_id>/edit/", views.teacher_exam_edit, name="teacher_exam_edit"),
    path("teacher/exams/<int:exam_id>/delete/", views.teacher_exam_delete, name="teacher_exam_delete"),
    path("teacher/exams/<int:exam_id>/questions/", views.teacher_exam_questions, name="teacher_exam_questions"),
    path("teacher/exams/<int:exam_id>/questions/<int:exam_question_id>/remove/", views.teacher_exam_question_remove, name="teacher_exam_question_remove"),
    path("teacher/questions/", views.teacher_question_list, name="teacher_question_list"),
    path("teacher/questions/new/", views.teacher_question_create, name="teacher_question_create"),
    path("teacher/questions/<int:question_id>/edit/", views.teacher_question_edit, name="teacher_question_edit"),
    path("teacher/students/", views.teacher_student_list, name="teacher_student_list"),
    path("teacher/students/<int:student_id>/", views.teacher_student_detail, name="teacher_student_detail"),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path('admin/', admin.site.urls),
]
