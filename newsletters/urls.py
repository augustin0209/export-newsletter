from django.urls import path
from . import views

urlpatterns = [
    path('', views.newsletter_list, name='newsletter_list'),
    path('create/', views.newsletter_create, name='newsletter_create'),
    path('<int:pk>/', views.newsletter_detail, name='newsletter_detail'),
    path('<int:pk>/edit/', views.newsletter_edit, name='newsletter_edit'),
    path('<int:pk>/send/', views.newsletter_send, name='newsletter_send'),
    path('<int:pk>/delete/', views.newsletter_delete, name='newsletter_delete'),
    path('<int:pk>/duplicate/', views.newsletter_duplicate, name='newsletter_duplicate'),
    path('<int:pk>/preview/', views.newsletter_preview, name='newsletter_preview'),
    
    path('subscribers/', views.subscriber_list, name='subscriber_list'),
    path('subscribers/create/', views.subscriber_create, name='subscriber_create'),
    path('subscribers/import/', views.subscriber_import, name='subscriber_import'),
    path('subscribers/export/', views.subscriber_export, name='subscriber_export'),
    path('subscribers/<int:subscriber_id>/delete/', views.subscriber_delete, name='subscriber_delete'),
    
    path('unsubscribe/<str:token>/', views.unsubscribe, name='unsubscribe'),
] 