from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

User = get_user_model()


class RegisterForm(UserCreationForm):
    error_messages = {"password_mismatch": "Parolalar eşleşmiyor."}

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = "3–20 karakter; harf, rakam ve alt çizgi."
        self.fields["username"].widget.attrs.update({"autocomplete": "username", "autocapitalize": "none"})
        self.fields["email"].widget.attrs.update({"autocomplete": "email"})
        self.fields["password1"].label = "Parola"
        self.fields["password1"].help_text = "En az 8 karakter."
        self.fields["password2"].label = "Parola (tekrar)"
        self.fields["password2"].help_text = ""

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class LoginForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Kullanıcı adı veya parola hatalı. Kontrol edip tekrar dene.",
        "inactive": "Bu hesap devre dışı.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Kullanıcı adı"
        self.fields["username"].widget.attrs.update({"autocomplete": "username", "autocapitalize": "none"})
        self.fields["password"].label = "Parola"

    def clean_username(self):
        # Kayıt büyük/küçük harf duyarsız benzersiz olduğundan giriş de öyle olmalı.
        username = self.cleaned_data["username"]
        stored = User.objects.filter(username__iexact=username).values_list("username", flat=True).first()
        return stored or username
