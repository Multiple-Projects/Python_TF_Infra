from django.urls import path
from . import views
from . import stream

urlpatterns = [
    path('', views.index, name='index'),
    path('create_resource/', views.create_resource, name='create_resource'),
    path('destroy_resource/', views.destroy_resource, name='destroy_resource'),
    path('get_terminal_output/', views.get_terminal_output, name='get_terminal_output'),
    path('confirm_resource/', views.confirm_resource, name='confirm_resource'),
    path('cancel_operation/', views.cancel_operation, name='cancel_operation'),
    path('reset_resource/', views.reset_resource, name='reset_resource'),
]
