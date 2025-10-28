# your_app/apps.py

from django.apps import AppConfig


class YourAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'exams'
    
    def ready(self):
        import exams.signals  # Import signals when app is ready
