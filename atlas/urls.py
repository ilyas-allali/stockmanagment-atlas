from django.urls import path
from workspace import views

urlpatterns = [
    path('', views.index),
    path('api/auth/<str:action>', views.auth),
    path('api/companies', views.companies),
    path('api/users', views.users),
    path('api/companies/<int:company_id>/<path:action>', views.company_api),
    path('<str:asset>', views.asset),
]
