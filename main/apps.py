# main/apps.py
from django.apps import AppConfig
from transformers import AutoTokenizer, AutoModel

class MainConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "main"

    _loaded = False  # runserver autoreload 대비

    def ready(self):
        if MainConfig._loaded:
            return
        self.tokenizer = AutoTokenizer.from_pretrained(
            "sentence-transformers/all-MiniLM-L6-v2"
        )
        self.model = AutoModel.from_pretrained(
            "sentence-transformers/all-MiniLM-L6-v2"
        )
        self.model.eval()
        MainConfig._loaded = True
