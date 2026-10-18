from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from .clubs import choose_club
from .forms import EmailLoginForm, RegistrationForm
from .models import Invitation, User


class LoginView(auth_views.LoginView):
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        choose_club(self.request, form.person)
        return response


def admin_login(request):
    """The admin uses the normal login, which also asks for the club."""
    if request.user.is_authenticated:
        # Logged in, but no admin in the chosen club; redirecting to the login would loop.
        raise PermissionDenied
    query = request.GET.urlencode()
    return redirect(f"{reverse('login')}?{query}" if query else reverse("login"))


@login_required
@require_POST
def switch_club(request):
    person = next((p for p in request.user.club_persons if str(p.club_id) == request.POST.get("club")), None)
    if person is None:
        raise PermissionDenied
    choose_club(request, person)
    messages.success(request, f"Du arbeitest jetzt im Verein {person.club}.")
    return redirect("record")


@method_decorator(ratelimit(key="ip", rate="5/h", method="POST", block=False), name="post")
class PasswordResetView(auth_views.PasswordResetView):
    success_url = reverse_lazy("password_reset_done")

    def form_valid(self, form):
        # Generic response: when the limit is exceeded, nothing is sent, silently.
        if getattr(self.request, "limited", False):
            return redirect(self.success_url)
        return super().form_valid(form)


def register(request, token: str):
    """Registration via invitation link: the person sets a password, the login is linked.

    If the email already has a login (from another club), that login is used.
    """
    invitation = Invitation.find_valid(token)
    if invitation is None:
        raise Http404("Einladung ungültig oder abgelaufen.")
    person = invitation.person
    user = (
        person.user
        or User.objects.filter(email__iexact=person.email).first()
        or User(email=person.email)
    )

    form = RegistrationForm(request.POST or None, user=user)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user.is_active = True
            user.set_password(form.cleaned_data["password1"])
            user.save()
            if person.user_id != user.pk:
                person.user = user
                person.save(update_fields=["user"])
            invitation.used_at = timezone.now()
            invitation.save(update_fields=["used_at"])
        login(request, user, backend="accounts.backends.EmailBackend")
        choose_club(request, person)
        messages.success(request, "Willkommen! Dein Konto ist eingerichtet.")
        return redirect("record")
    return render(request, "accounts/register.html", {"form": form, "person": person})
