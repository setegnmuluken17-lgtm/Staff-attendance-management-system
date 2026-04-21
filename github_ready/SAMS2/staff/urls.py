from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('admin/login/', views.admin_login, name='admin_login'),
    path('register/', views.register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('admin-page/', views.admin_page, name='admin_page'),
    path('admin-page/approve/<int:staff_pk>/', views.approve_staff, name='approve_staff'),
    path('admin-page/leave/<int:leave_pk>/<str:status>/', views.update_leave_request, name='update_leave_request'),
    path('logout/', views.logout_view, name='logout'),
    path('attendance/', views.attendance, name='attendance'),
    path('leave-request/', views.submit_leave_request, name='submit_leave_request'),
    path('daily-report', views.daily_report, name='daily_report'),
    path('monthly-report', views.monthly_report, name='monthly_report'),
    path('export-excel/', views.export_excel, name='export_excel'),
    path('export-pdf/', views.export_pdf, name='export_pdf'),
]
