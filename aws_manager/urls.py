from django.urls import path
from . import views
from . import stream

urlpatterns = [
    path('', views.index, name='index'),
    path('create_resource/', views.create_resource, name='create_resource'),
    path('destroy_resource/', views.destroy_resource, name='destroy_resource'),
    path('stream_output/', stream.stream_output, name='stream_output'),
]
