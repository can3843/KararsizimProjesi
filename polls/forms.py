from django import forms

from .models import Option, Poll

MIN_OPTIONS = 2
MAX_OPTIONS = 5
OPTION_MAX_LENGTH = Option._meta.get_field("text").max_length


class PollForm(forms.ModelForm):
    # Yalnızca seçenek hatalarını taşır; seçenekler `option` adıyla tekrarlanan girdilerden okunur.
    options = forms.Field(required=False)

    class Meta:
        model = Poll
        fields = ("question", "description")
        labels = {"question": "Sorun ne?", "description": "Açıklama (isteğe bağlı)"}
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["question"].help_text = "10–140 karakter."
        self.fields["question"].widget.attrs["autofocus"] = True

    @property
    def option_rows(self):
        values = self.data.getlist("option") if self.is_bound else []
        values = (values + [""] * MAX_OPTIONS)[:MAX_OPTIONS]
        return [{"number": number, "value": value} for number, value in enumerate(values, start=1)]

    def clean(self):
        cleaned_data = super().clean()
        raw = self.data.getlist("option") if self.is_bound else []
        texts = [text.strip() for text in raw if text.strip()]

        if len(texts) < MIN_OPTIONS:
            self.add_error("options", f"En az {MIN_OPTIONS} seçenek gerekli.")
        elif len(texts) > MAX_OPTIONS:
            self.add_error("options", f"En fazla {MAX_OPTIONS} seçenek olabilir.")
        elif any(len(text) > OPTION_MAX_LENGTH for text in texts):
            self.add_error("options", f"Her seçenek en fazla {OPTION_MAX_LENGTH} karakter olabilir.")
        elif len({text.casefold() for text in texts}) != len(texts):
            self.add_error("options", "Aynı seçenek iki kez yazılamaz.")
        else:
            cleaned_data["option_texts"] = texts
        return cleaned_data
