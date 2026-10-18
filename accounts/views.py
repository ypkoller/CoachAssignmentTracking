from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit

from .forms import EmailLoginForm, RegistrationForm
from .models import Invitation, User


class LoginView(auth_views.LoginView):
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True


@method_decorator(ratelimit(key="ip", rate="5/h", method="POST", block=False), name="post")
class PasswordResetView(auth_views.PasswordResetView):
    success_url = reverse_lazy("password_reset_done")

    def form_valid(self, form):
        # Generic response: when the limit is exceeded, nothing is sent, silently.
        if getattr(self.request, "limited", False):
            return redirect(self.success_url)
        return super().form_valid(form)


def register(request, token: str):
    """Registration via invitation link: the person sets a password, the login is linked."""
    invitation = Invitation.find_valid(token)
    if invitation is None:
        raise Http404("Einladung ungültig oder abgelaufen.")
    person = invitation.person
    user = User.objects.filter(person=person).first() or User(email=person.email, person=person)

    form = RegistrationForm(request.POST or None, user=user)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user.email = person.email
            user.is_active = True
            user.set_password(form.cleaned_data["password1"])
            user.save()
            invitation.used_at = timezone.now()
            invitation.save(update_fields=["used_at"])
        login(request, user, backend="accounts.backends.EmailBackend")
        messages.success(request, "Willkommen! Dein Konto ist eingerichtet.")
        return redirect("record")
    return render(request, "accounts/register.html", {"form": form, "person": person})
